"""Test doubles: a scripted LLM and a sqlite3-backed DatabaseBackend."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from config import Settings
from services.errors import LLMUnavailableError, QueryExecutionError
from services.llm_client import LLMResponse
from services.schema import ColumnInfo, ForeignKey, SchemaContext, TableInfo
from services.schema_profiler import enrich_schema
from services.sql_runtime import RawResult, configure_sqlite, run_select

Reply = Union[str, Dict[str, Any], Callable[[List[Dict[str, str]]], Union[str, Dict[str, Any]]]]


class FakeLLM:
    """Replies are consumed in order per role ('gen' / 'judge' / 'summary').

    The role is inferred from the system prompt so tests can script each
    component independently.
    """

    configured = True

    def __init__(self, gen: Sequence[Reply] = (), judge: Sequence[Reply] = (), summary: Sequence[Reply] = ()) -> None:
        self.queues = {"gen": list(gen), "judge": list(judge), "summary": list(summary)}
        self.calls: List[Dict[str, Any]] = []

    @staticmethod
    def _role(system: str) -> str:
        if "independent, senior reviewer" in system:
            return "judge"
        if "careful business data analyst" in system:
            return "summary"
        return "gen"

    def complete(self, messages, *, models=None, temperature=0.0, max_tokens=1500, json_mode=False):
        role = self._role(messages[0]["content"])
        self.calls.append({"role": role, "messages": messages, "models": list(models or [])})
        queue = self.queues[role]
        if not queue:
            raise LLMUnavailableError(f"no scripted reply left for {role}")
        reply = queue.pop(0) if len(queue) > 1 or role == "gen" else queue[0]
        if callable(reply):
            reply = reply(messages)
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return LLMResponse(text=text, model=f"fake-{role}")

    def count(self, role: str) -> int:
        return sum(1 for c in self.calls if c["role"] == role)


def gen_ok(sql: str, **extra: Any) -> Dict[str, Any]:
    return {"status": "ok", "sql": sql, "assumptions": [], "confidence": 0.9, "message": "", **extra}


def judge_reply(verdict: str = "pass", score: float = 0.95, issues: Optional[List[str]] = None, **extra: Any):
    return {"verdict": verdict, "score": score, "issues": issues or [], "summary": "ok",
            "criteria": {"schema_fidelity": 1, "question_match": score, "result_plausibility": 1, "safety": 1}, **extra}


class SqliteBackend:
    """DatabaseBackend over a sqlite file; mirrors what DatabaseService does."""

    def __init__(self, path: str, settings: Settings) -> None:
        self.path, self.settings = path, settings
        self.conn = sqlite3.connect(path, check_same_thread=False)
        configure_sqlite(self.conn)
        self._schema: Optional[SchemaContext] = None
        self.queries: List[str] = []

    def get_db_type(self, connection_id: str) -> str:
        return "sqlite"

    def run_query(self, connection_id: str, sql: str, max_rows: int, timeout_seconds: int) -> RawResult:
        self.queries.append(sql)
        return run_select(self.conn, sql, max_rows, timeout_seconds)

    def get_schema(self, connection_id: str, refresh: bool = False) -> SchemaContext:
        if self._schema is None or refresh:
            schema = SchemaContext(database="test", db_type="sqlite")
            names = [r[0] for r in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            for name in names:
                cols = [ColumnInfo(r[1], r[2], not r[3], bool(r[5]))
                        for r in self.conn.execute(f'PRAGMA table_info("{name}")')]
                fks = [ForeignKey([r[3]], r[2], [r[4]]) for r in self.conn.execute(f'PRAGMA foreign_key_list("{name}")')]
                schema.tables[name] = TableInfo(name, "table", cols, fks)
            enrich_schema(schema, lambda q: run_select(self.conn, q, 100, 5), self.settings)
            self._schema = schema
        return self._schema
