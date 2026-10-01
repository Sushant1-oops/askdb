import os
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from config import settings
from services.container import db_service, executor, export_service
from services.errors import BadRequestError
from services.export_service import FORMATS

router = APIRouter()


class QueryExportRequest(BaseModel):
    connection_id: str
    sql_query: str = Field(..., min_length=1, max_length=50_000)
    format: str = Field(..., description="csv, excel or pdf")
    filename: Optional[str] = None


class TableExportRequest(BaseModel):
    connection_id: str
    table_name: str
    format: str = Field(..., description="csv, excel or pdf")
    limit: Optional[int] = Field(None, ge=1)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _respond(connection_id: str, sql: str, fmt: str, name: str, limit: Optional[int] = None) -> FileResponse:
    if fmt.lower() not in FORMATS:
        raise BadRequestError("Unsupported export format. Use csv, excel or pdf.")
    cap = min(limit or settings.max_export_rows, settings.max_export_rows)
    outcome = executor.execute(connection_id, sql, max_rows=cap)
    if not outcome.ok or outcome.result is None:
        raise BadRequestError(outcome.message or "The query could not be executed.")
    result = outcome.result
    if not result["rows"]:
        raise BadRequestError("There are no rows to export.")
    path, media_type, filename = export_service.export(result["columns"], result["rows"], fmt, name)
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        background=BackgroundTask(_remove, path),
        headers={"X-Export-Rows": str(result["row_count"]), "X-Export-Truncated": str(bool(result["truncated"])).lower()},
    )


@router.post("/query")
def export_query(body: QueryExportRequest) -> FileResponse:
    db_service.get_connection_info(body.connection_id)
    return _respond(body.connection_id, body.sql_query, body.format, body.filename or "query_results")


@router.post("/table")
def export_table(body: TableExportRequest) -> FileResponse:
    sql = db_service.build_table_select(body.connection_id, body.table_name)
    return _respond(body.connection_id, sql, body.format, body.table_name, body.limit)
