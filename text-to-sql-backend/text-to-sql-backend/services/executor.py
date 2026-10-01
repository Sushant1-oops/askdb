"""GuardedExecutor: the single path through which any SQL reaches a database.

    validate (SQLGuard) -> run (read-only session, row cap, timeout) -> redact

The natural-language pipeline, the SQL editor and the export endpoints all go
through ``execute`` so the same policy applies everywhere.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from config import Settings
from services.errors import QueryExecutionError
from services.guardrails import GuardResult, SQLGuard, redact_rows
from services.schema import SchemaContext
from services.sql_runtime import RawResult

logger = logging.getLogger(__name__)


class DatabaseBackend(Protocol):
    """The subset of DatabaseService the query pipeline depends on."""

    def get_db_type(self, connection_id: str) -> str: ...

    def get_schema(self, connection_id: str, refresh: bool = False) -> SchemaContext: ...

    def run_query(self, connection_id: str, sql: str, max_rows: int, timeout_seconds: int) -> RawResult: ...


@dataclass
class ExecOutcome:
    ok: bool
    kind: str = ""  
    sql: str = ""
    message: str = ""
    guard: Optional[GuardResult] = None
    result: Optional[Dict[str, Any]] = None


class GuardedExecutor:
    def __init__(self, db: DatabaseBackend, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def execute(self, connection_id: str, sql: str, *, max_rows: Optional[int] = None) -> ExecOutcome:
        cap = max_rows or self.settings.max_rows
        schema = self.db.get_schema(connection_id)
        db_type = self.db.get_db_type(connection_id)

        guard = SQLGuard(
            schema.table_names(),
            restricted_columns=schema.restricted_columns(),
            dialect=db_type,
            max_rows=cap,
        ).validate(sql)
        if not guard.ok:
            logger.info("guard blocked sql: %s", guard.message)
            return ExecOutcome(ok=False, kind="guard", sql=sql, message=guard.message, guard=guard)

        try:
            raw = self.db.run_query(connection_id, guard.sql, cap, self.settings.query_timeout_seconds)
        except QueryExecutionError as exc:
            return ExecOutcome(ok=False, kind="error", sql=guard.sql, message=str(exc), guard=guard)

        rows, redacted = redact_rows(
            raw.columns, raw.rows, schema.restricted_columns(), self.settings.restricted_column_re
        )
        raw.rows = rows
        raw.redacted_columns = redacted
        return ExecOutcome(ok=True, sql=guard.sql, guard=guard, result=raw.to_dict())
