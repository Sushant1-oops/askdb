"""The text-to-SQL pipeline.

    input guard -> schema link -> generate -> [guard -> execute] -> repair loop
                -> LLM judge -> (one bounded revision) -> pick best -> summarise

Every LLM call is bounded: ``max_repair_attempts`` fixes for guard/execution
failures and ``max_judge_revisions`` rounds of judge-driven regeneration. The
response always carries an ``attempts`` trace so the UI can show exactly what
happened, and a ``status`` the frontend can switch on:

    success        SQL ran; ``result`` is populated
    blocked        rejected by a guardrail (input or SQL policy)
    failed         could not produce SQL that runs
    clarification  the model needs more information / data is not in the schema
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import Settings
from services.errors import LLMUnavailableError
from services.executor import DatabaseBackend, ExecOutcome, GuardedExecutor
from services.guardrails import InputGuard
from services.history import HistoryStore
from services.insight import Summarizer
from services.judge import Judge, JudgeVerdict
from services.llm_client import LLM
from services.schema_linker import select_tables
from services.sql_generator import Generation, SQLGenerator

logger = logging.getLogger(__name__)


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).lower()


@dataclass
class _Candidate:
    sql: str
    outcome: ExecOutcome
    verdict: Optional[JudgeVerdict]
    assumptions: List[str]
    model: str


class QueryPipeline:
    def __init__(
        self,
        *,
        db: DatabaseBackend,
        executor: GuardedExecutor,
        generator: SQLGenerator,
        judge: Judge,
        summarizer: Summarizer,
        history: HistoryStore,
        llm: LLM,
        settings: Settings,
    ) -> None:
        self.db = db
        self.executor = executor
        self.generator = generator
        self.judge = judge
        self.summarizer = summarizer
        self.history = history
        self.llm = llm
        self.settings = settings
        self.input_guard = InputGuard(settings.max_question_chars)

    
    def run(
        self,
        connection_id: str,
        question: str,
        *,
        history: Optional[List[Dict[str, Any]]] = None,
        judge: Optional[bool] = None,
        summarize: bool = False,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        timings: Dict[str, int] = {}
        question = (question or "").strip()

        check = self.input_guard.check(question)
        if not check.ok:
            return self._finish(
                connection_id, started, timings, question=question, status="blocked", message=check.message,
                violations=[{"code": check.code, "message": check.message, "security": True}],
                record=check.code not in ("EMPTY",),
            )

        if not self.llm.configured:
            raise LLMUnavailableError("The AI engine is not configured. Set GROQ_API_KEY in the backend .env file.")

        schema = self.db.get_schema(connection_id)
        db_type = self.db.get_db_type(connection_id)
        history_text = " ".join(str(m.get("content", "")) for m in (history or [])[-4:])
        tables = select_tables(schema, question, history_text)
        judge_on = self.settings.judge_enabled if judge is None else judge

        
        t = time.perf_counter()
        gen = self.generator.generate(question, schema, tables, db_type, history)
        timings["generate_ms"] = int((time.perf_counter() - t) * 1000)

        if gen.status in ("unanswerable", "ambiguous"):
            return self._finish(
                connection_id, started, timings, question=question, status="clarification",
                message=gen.message or "I need a bit more information to answer that.",
                extra={"clarification_type": gen.status, "model_used": gen.model},
            )
        if not gen.ok:
            return self._finish(
                connection_id, started, timings, question=question, status="failed",
                message=gen.message or "The AI could not produce a query for this question.",
                extra={"model_used": gen.model},
            )

        
        sql, stage = gen.sql, "generate"
        assumptions, model_used = gen.assumptions, gen.model
        attempts: List[Dict[str, Any]] = []
        candidates: List[_Candidate] = []
        last_failure: Optional[ExecOutcome] = None
        repairs = judge_rounds = 0
        exec_ms = judge_ms = 0
        schema_ddl = schema.render_ddl(tables, include_samples=self.settings.llm_include_samples)

        while True:
            t = time.perf_counter()
            outcome = self.executor.execute(connection_id, sql)
            exec_ms += int((time.perf_counter() - t) * 1000)
            attempt: Dict[str, Any] = {
                "n": len(attempts) + 1, "stage": stage, "sql": outcome.sql or sql,
                "outcome": "ok" if outcome.ok else ("blocked" if outcome.kind == "guard" else "error"),
                "detail": "" if outcome.ok else outcome.message,
            }
            attempts.append(attempt)

            if outcome.ok and outcome.result is not None:
                verdict: Optional[JudgeVerdict] = None
                if judge_on:
                    t = time.perf_counter()
                    verdict = self.judge.evaluate(
                        question=question, sql=outcome.sql, schema_ddl=schema_ddl,
                        result=outcome.result, assumptions=assumptions, db_type=db_type,
                    )
                    judge_ms += int((time.perf_counter() - t) * 1000)
                    attempt["judge"] = {"verdict": verdict.verdict, "score": verdict.score}
                candidates.append(_Candidate(outcome.sql, outcome, verdict, assumptions, model_used))

                if verdict and verdict.needs_revision(self.settings.judge_min_score)                        and judge_rounds < self.settings.max_judge_revisions:
                    judge_rounds += 1
                    regen = self._safe_repair(
                        question, outcome.sql, "judge", self._judge_feedback(verdict),
                        schema, tables, db_type, history,
                    )
                    if regen and regen.ok and _normalise(regen.sql) != _normalise(outcome.sql):
                        sql, stage = regen.sql, "judge_revision"
                        assumptions = regen.assumptions or assumptions
                        model_used = regen.model or model_used
                        continue
                break

            last_failure = outcome
            if repairs < self.settings.max_repair_attempts:
                repairs += 1
                regen = self._safe_repair(
                    question, sql, "guard" if outcome.kind == "guard" else "execution", outcome.message,
                    schema, tables, db_type, history,
                )
                if regen and regen.ok:
                    sql, stage = regen.sql, "repair"
                    model_used = regen.model or model_used
                    continue
            break

        timings["execute_ms"] = exec_ms
        if judge_on:
            timings["judge_ms"] = judge_ms

        
        if not candidates:
            assert last_failure is not None
            guard = last_failure.guard
            security = bool(guard and guard.has_security_violation)
            if last_failure.kind == "guard":
                message = last_failure.message
                if not security:
                    message = f"I couldn't produce a valid query for this question. {message}"
            else:
                message = f"The database rejected the generated query: {last_failure.message}"
            return self._finish(
                connection_id, started, timings, question=question,
                status="blocked" if security else "failed", message=message, sql=last_failure.sql,
                attempts=attempts, guard=guard.to_dict() if guard else None,
                violations=[v.to_dict() for v in guard.violations] if guard else None,
                extra={"model_used": model_used},
            )

        best = self._pick_best(candidates)
        assert best.outcome.result is not None

        verdict = best.verdict
        low_confidence = bool(verdict and verdict.needs_revision(self.settings.judge_min_score))
        confidence = verdict.score if verdict and not verdict.skipped else gen.confidence
        extra: Dict[str, Any] = {
            "assumptions": best.assumptions,
            "confidence": confidence,
            "low_confidence": low_confidence,
            "model_used": best.model,
            "judge": verdict.to_dict(revisions=judge_rounds) if verdict else {"enabled": False},
        }

        
        if summarize:
            t = time.perf_counter()
            insight = self.summarizer.summarize(question, best.sql, best.outcome.result)
            timings["summary_ms"] = int((time.perf_counter() - t) * 1000)
            extra.update({"answer": insight.answer, "chart": insight.chart, "follow_ups": insight.follow_ups})

        guard = best.outcome.guard
        return self._finish(
            connection_id, started, timings, question=question, status="success", sql=best.sql,
            result=best.outcome.result, attempts=attempts, guard=guard.to_dict() if guard else None,
            extra=extra, verdict=verdict.verdict if verdict else None,
        )

    
    def _safe_repair(
        self, question: str, sql: str, kind: str, problem: str, schema: Any,
        tables: List[str], db_type: str, history: Optional[List[Dict[str, Any]]],
    ) -> Optional[Generation]:
        try:
            return self.generator.repair(question, sql, kind, problem, schema, tables, db_type, history)
        except LLMUnavailableError as exc:
            logger.warning("repair skipped, LLM unavailable: %s", exc)
            return None

    @staticmethod
    def _pick_best(candidates: List[_Candidate]) -> _Candidate:
        """Highest judge score wins; ties go to the later (revised) candidate."""
        def score(item: "tuple[int, _Candidate]") -> "tuple[float, int]":
            verdict = item[1].verdict
            return (verdict.score or 0.0 if verdict else 0.0, item[0])

        judged = [(i, c) for i, c in enumerate(candidates) if c.verdict and not c.verdict.skipped]
        return max(judged, key=score)[1] if judged else candidates[-1]

    @staticmethod
    def _judge_feedback(verdict: JudgeVerdict) -> str:
        parts = [f"- {issue}" for issue in verdict.issues] or ["- The reviewer scored this query low without specifics."]
        if verdict.suggestion:
            parts.append(f"Suggested fix: {verdict.suggestion}")
        if verdict.signals:
            parts.append("Automatic signals: " + " ".join(verdict.signals))
        return "\n".join(parts)

    def _finish(
        self,
        connection_id: str,
        started: float,
        timings: Dict[str, int],
        *,
        question: str,
        status: str,
        message: str = "",
        sql: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        attempts: Optional[List[Dict[str, Any]]] = None,
        guard: Optional[Dict[str, Any]] = None,
        violations: Optional[List[Dict[str, Any]]] = None,
        extra: Optional[Dict[str, Any]] = None,
        verdict: Optional[str] = None,
        record: bool = True,
    ) -> Dict[str, Any]:
        total_ms = int((time.perf_counter() - started) * 1000)
        timings["total_ms"] = total_ms
        guardrails = guard or {"passed": status != "blocked", "violations": [], "warnings": [], "tables": [],
                               "limit_applied": False, "read_only": True}
        if violations:
            guardrails = {**guardrails, "passed": False, "violations": violations}
        body: Dict[str, Any] = {
            "status": status,
            "question": question,
            "message": message,
            "sql": sql,
            "result": result,
            "guardrails": guardrails,
            "attempts": attempts or [],
            "retries": max(0, len(attempts or []) - 1),
            "timings": timings,
            "execution_time": round(total_ms / 1000, 2),
            "assumptions": [],
            "judge": {"enabled": False},
            "model_used": None,
        }
        if extra:
            body.update(extra)
        if record:
            self.history.add(
                connection_id, source="ask", question=question or None, sql=sql, status=status,
                row_count=result.get("row_count") if result else None, duration_ms=total_ms, verdict=verdict,
            )
        return body
