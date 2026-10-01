import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Query, UploadFile, status
from pydantic import BaseModel, Field

from config import settings
from services.container import db_service, history_store, llm_client
from services.errors import BadRequestError, NotFoundError
from services.export_service import safe_name
from services.sample_data import create_sample_db
from services.schema import SchemaContext
from services.suggestions import suggest_questions

logger = logging.getLogger(__name__)
router = APIRouter()


class DatabaseConnection(BaseModel):
    db_type: str = Field(..., description="postgresql, mysql or sqlite")
    database: str = Field("", description="Database name (or file name for SQLite)")
    host: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    file_path: Optional[str] = Field(None, description="SQLite file path on the server")
    ssl: bool = Field(False, description="Require SSL (PostgreSQL)")


@router.post("/connect", status_code=status.HTTP_201_CREATED)
def connect_database(body: DatabaseConnection) -> Dict[str, Any]:
    return db_service.create_connection(
        db_type=body.db_type, database=body.database, host=body.host, port=body.port,
        username=body.username, password=body.password, file_path=body.file_path, ssl=body.ssl,
    )


@router.post("/connect-demo", status_code=status.HTTP_201_CREATED)
def connect_demo() -> Dict[str, Any]:
    """Create (or reuse) the bundled e-commerce SQLite database and connect to it."""
    path = os.path.abspath(os.path.join(settings.data_dir, "demo_ecommerce.db"))
    stale = not os.path.exists(path) or time.time() - os.path.getmtime(path) > 86_400
    if stale:  
        try:
            create_sample_db(path)
        except OSError:  
            if not os.path.exists(path):
                raise
    return db_service.create_connection(db_type="sqlite", database="demo_ecommerce.db", file_path=path)


@router.post("/connect-upload", status_code=status.HTTP_201_CREATED)
def connect_upload(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload a SQLite file and connect to it."""
    original = file.filename or "upload.db"
    if not original.lower().endswith((".db", ".sqlite", ".sqlite3")):
        raise BadRequestError("Upload a .db, .sqlite or .sqlite3 file.")
    folder = os.path.join(settings.data_dir, "uploads")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{uuid.uuid4().hex[:8]}_{safe_name(original, 'upload.db')}")
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with open(path, "wb") as out:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise BadRequestError(f"File is larger than {settings.max_upload_mb} MB.")
                out.write(chunk)
        return db_service.create_connection(db_type="sqlite", database=original, file_path=path)
    except Exception:
        if os.path.exists(path):
            os.remove(path)
        raise


@router.get("/connections")
def list_connections() -> Dict[str, Any]:
    return {"connections": db_service.list_connections()}


@router.get("/connections/{connection_id}")
def get_connection(connection_id: str) -> Dict[str, Any]:
    return db_service.get_connection_info(connection_id)


@router.delete("/connections/{connection_id}")
def disconnect_database(connection_id: str) -> Dict[str, str]:
    result = db_service.close_connection(connection_id)
    history_store.clear(connection_id)
    return result


@router.get("/connections/{connection_id}/overview")
def connection_overview(connection_id: str) -> Dict[str, Any]:
    """Everything the Overview page needs in one round trip."""
    info = db_service.get_connection_info(connection_id)
    schema = db_service.get_schema(connection_id)
    latency = db_service.ping(connection_id)
    largest = sorted(
        (t for t in schema.tables.values() if t.row_count), key=lambda t: -(t.row_count or 0)
    )[:6]
    return {
        "connection": info,
        "status": "online" if latency is not None else "unreachable",
        "latency_ms": latency,
        "stats": schema.to_api()["stats"],
        "largest_tables": [{"name": t.name, "row_count": t.row_count} for t in largest],
        "usage": history_store.stats(connection_id),
        "suggestions": suggest_questions(schema),
        "ai": {
            "configured": llm_client.configured,
            "model": settings.model_chain[0] if settings.model_chain else None,
            "judge_enabled": settings.judge_enabled,
        },
    }


@router.get("/connections/{connection_id}/schema")
def get_database_schema(connection_id: str, refresh: bool = Query(False)) -> Dict[str, Any]:
    return db_service.get_schema(connection_id, refresh=refresh).to_api()


@router.get("/connections/{connection_id}/tables")
def list_tables(connection_id: str) -> Dict[str, Any]:
    schema = db_service.get_schema(connection_id)
    tables = [
        {"name": t.name, "kind": t.kind, "row_count": t.row_count, "column_count": len(t.columns)}
        for t in schema.tables.values()
    ]
    return {"tables": tables, "count": len(tables)}


@router.get("/connections/{connection_id}/tables/{table_name}/schema")
def get_table_schema(connection_id: str, table_name: str) -> Dict[str, Any]:
    table = db_service.get_schema(connection_id).get_table(table_name)
    if table is None:
        raise NotFoundError(f"Table '{table_name}' not found.")
    return SchemaContext.table_to_api(table)


@router.get("/connections/{connection_id}/tables/{table_name}/data")
def get_table_data(
    connection_id: str,
    table_name: str,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    return db_service.get_table_data(connection_id, table_name, limit, offset)
