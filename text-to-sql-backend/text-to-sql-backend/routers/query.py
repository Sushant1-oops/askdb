import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from config import settings
from services.container import db_service, executor, history_store, llm_client, pipeline

router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = ""
    sql: Optional[str] = Field(None, description="SQL the assistant produced for this turn")


class AskRequest(BaseModel):
    connection_id: str
    question: str = Field(..., min_length=1, max_length=5000)
    history: Optional[List[ChatMessage]] = None
    judge: Optional[bool] = Field(None, description="Override the server default for LLM-as-judge")


class SQLRequest(BaseModel):
    connection_id: str
    sql_query: str = Field(..., min_length=1, max_length=50_000)


def _history(body: AskRequest) -> Optional[List[Dict[str, Any]]]:
    return [m.model_dump() for m in body.history][-8:] if body.history else None


@router.post("/natural-language")
def natural_language(body: AskRequest) -> Dict[str, Any]:
    """Question -> guarded, verified SQL + result (used by the SQL editor's AI bar)."""
    db_service.get_connection_info(body.connection_id)  
    return pipeline.run(body.connection_id, body.question, history=_history(body), judge=body.judge, summarize=False)


@router.post("/chat")
def chat(body: AskRequest) -> Dict[str, Any]:
    """Ask AI: same pipeline plus a plain-language answer, chart spec and follow-ups."""
    db_service.get_connection_info(body.connection_id)
    return pipeline.run(body.connection_id, body.question, history=_history(body), judge=body.judge, summarize=True)


@router.post("/sql")
def execute_sql(body: SQLRequest) -> Dict[str, Any]:
    """Run hand-written SQL. Read-only, single statement, row-capped, redacted."""
    db_service.get_connection_info(body.connection_id)
    started = time.perf_counter()
    outcome = executor.execute(body.connection_id, body.sql_query)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if outcome.ok:
        state, message = "success", ""
    elif outcome.kind == "guard":
        security = bool(outcome.guard and outcome.guard.has_security_violation)
        state, message = ("blocked" if security else "failed"), outcome.message
    else:
        state, message = "failed", outcome.message

    result = outcome.result
    history_store.add(
        body.connection_id, source="editor", sql=outcome.sql or body.sql_query, status=state,
        row_count=result["row_count"] if result else None, duration_ms=elapsed_ms,
    )
    return {
        "status": state,
        "message": message,
        "sql": outcome.sql or body.sql_query,
        "result": result,
        "guardrails": outcome.guard.to_dict() if outcome.guard else None,
        "execution_time": round(elapsed_ms / 1000, 2),
    }


@router.get("/history")
def get_history(connection_id: str, limit: int = Query(30, ge=1, le=200)) -> Dict[str, Any]:
    db_service.get_connection_info(connection_id)
    return {"items": history_store.list(connection_id, limit)}


@router.delete("/history")
def clear_history(connection_id: str) -> Dict[str, str]:
    db_service.get_connection_info(connection_id)
    history_store.clear(connection_id)
    return {"status": "cleared"}


@router.get("/model-status")
def model_status(deep: bool = Query(False, description="Also ask the provider which models exist")) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "configured": llm_client.configured,
        "provider": "Groq",
        "model_chain": settings.model_chain,
        "judge_model_chain": settings.judge_model_chain,
        "judge_enabled": settings.judge_enabled,
        "limits": {
            "max_rows": settings.max_rows,
            "query_timeout_seconds": settings.query_timeout_seconds,
            "max_repair_attempts": settings.max_repair_attempts,
        },
    }
    if deep and llm_client.configured:
        try:
            available = set(llm_client.available_models())
            body["chain_status"] = {m: m in available for m in {*settings.model_chain, *settings.judge_model_chain}}
        except Exception as exc:
            body["error"] = str(exc)[:200]
    return body
