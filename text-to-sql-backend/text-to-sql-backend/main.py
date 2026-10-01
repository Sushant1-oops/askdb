from config import settings  

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.errors import (
    BadRequestError,
    LLMUnavailableError,
    NotFoundError,
    QueryExecutionError,
)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("askdb")

VERSION = "3.0.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    os.makedirs(settings.data_dir, exist_ok=True)
    logger.info(
        "AskDB API %s | AI %s | judge=%s | max_rows=%s | timeout=%ss",
        VERSION,
        "configured" if settings.llm_configured else "NOT configured (set GROQ_API_KEY)",
        settings.judge_enabled, settings.max_rows, settings.query_timeout_seconds,
    )
    yield


app = FastAPI(
    title="AskDB API",
    description="Natural language to SQL with guardrails, self-repair and an LLM judge. Read-only by design.",
    version=VERSION,
    lifespan=lifespan,
)


if "*" in settings.cors_origins:
    cors = dict(allow_origins=["*"])
elif settings.cors_origins:
    cors = dict(allow_origins=settings.cors_origins)
else:
    cors = dict(allow_origins=[], allow_origin_regex=settings.cors_origin_regex)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Export-Rows", "X-Export-Truncated", "X-Request-ID"],
    **cors,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info("%s %s -> %s in %dms [%s]", request.method, request.url.path, response.status_code,
                (time.perf_counter() - started) * 1000, request_id)
    return response



def _json(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(NotFoundError)
async def _not_found(_: Request, exc: NotFoundError):
    return _json(404, str(exc))


@app.exception_handler(BadRequestError)
async def _bad_request(_: Request, exc: BadRequestError):
    return _json(400, str(exc))


@app.exception_handler(QueryExecutionError)
async def _query_error(_: Request, exc: QueryExecutionError):
    return _json(400, str(exc))


@app.exception_handler(LLMUnavailableError)
async def _llm_unavailable(_: Request, exc: LLMUnavailableError):
    return _json(503, str(exc))


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "-")
    logger.exception("Unhandled error [%s] on %s %s", request_id, request.method, request.url.path)
    return _json(500, f"Something went wrong on the server (ref {request_id}).")



from routers import database, export, query  

app.include_router(database.router, prefix="/api/database", tags=["Database"])
app.include_router(query.router, prefix="/api/query", tags=["Query"])
app.include_router(export.router, prefix="/api/export", tags=["Export"])


@app.get("/", include_in_schema=False)
def root():
    return {"name": "AskDB API", "version": VERSION, "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "version": VERSION,
        "ai_configured": settings.llm_configured,
        "time": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")), reload=settings.debug)
