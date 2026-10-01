"""Connection management and schema introspection (SQLAlchemy).

Security posture for every connection:
  * the *session* is read-only (Postgres/MySQL session characteristics, SQLite
    ``query_only``), so even a guard bypass cannot write;
  * a statement timeout is set (Postgres/MySQL server side, SQLite progress handler);
  * SQL is executed through raw DBAPI cursors, see ``sql_runtime``;
  * passwords are used to build the engine and never stored or returned.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import URL, Engine

from config import Settings
from services.errors import BadRequestError, NotFoundError, QueryExecutionError
from services.guardrails import redact_rows
from services.schema import ColumnInfo, ForeignKey, SchemaContext, TableInfo
from services.schema_profiler import enrich_schema
from services.sql_runtime import RawResult, clean_db_error, configure_sqlite, quote_identifier, run_select

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = ("sqlite", "postgresql", "mysql")
MAX_CONNECTIONS = 20
_SQLITE_MAGIC = b"SQLite format 3\x00"


class _Entry:
    def __init__(self, **kw: Any) -> None:
        self.id: str = kw["id"]
        self.db_type: str = kw["db_type"]
        self.database: str = kw["database"]
        self.label: str = kw["label"]
        self.host: Optional[str] = kw.get("host")
        self.port: Optional[int] = kw.get("port")
        self.username: Optional[str] = kw.get("username")
        self.engine: Engine = kw["engine"]
        self.created_at: str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def public(self) -> Dict[str, Any]:
        return {
            "connection_id": self.id,
            "db_type": self.db_type,
            "database": self.database,
            "label": self.label,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "created_at": self.created_at,
            "status": "connected",
        }


class DatabaseService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._entries: Dict[str, _Entry] = {}
        self._schemas: Dict[str, SchemaContext] = {}
        self._schema_locks: Dict[str, threading.Lock] = {}
        self._lock = threading.RLock()

    
    def create_connection(
        self,
        db_type: str,
        database: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        file_path: Optional[str] = None,
        ssl: bool = False,
    ) -> Dict[str, Any]:
        db_type = (db_type or "").strip().lower()
        if db_type in ("postgres", "pg"):
            db_type = "postgresql"
        if db_type not in SUPPORTED_TYPES:
            raise BadRequestError(f"Unsupported database type '{db_type}'. Use one of: {', '.join(SUPPORTED_TYPES)}.")
        with self._lock:
            if len(self._entries) >= MAX_CONNECTIONS:
                raise BadRequestError(f"Connection limit reached ({MAX_CONNECTIONS}). Disconnect one first.")

        if db_type == "sqlite":
            path = self._validate_sqlite_path(file_path or database)
            label = os.path.basename(path)
            engine = self._build_engine(db_type, URL.create("sqlite", database=path))
            database, host, port, username = label, None, None, None
        else:
            if not host or not username:
                raise BadRequestError("Host and username are required.")
            if not database:
                raise BadRequestError("Database name is required.")
            default_port = 5432 if db_type == "postgresql" else 3306
            query = {"sslmode": "require"} if db_type == "postgresql" and (ssl or "neon.tech" in host) else {}
            url = URL.create(
                "postgresql+psycopg2" if db_type == "postgresql" else "mysql+pymysql",
                username=username, password=password or None, host=host, port=port or default_port,
                database=database, query=query,
            )
            engine = self._build_engine(db_type, url)
            label = f"{database}@{host}"

        try:
            with engine.connect() as conn:
                run_select(conn.connection, "SELECT 1", 1, 10)
        except Exception as exc:
            engine.dispose()
            logger.warning("connection test failed for %s: %s", db_type, type(exc).__name__)
            raise BadRequestError(f"Could not connect: {clean_db_error(exc)}") from exc

        entry = _Entry(id=str(uuid.uuid4()), db_type=db_type, database=database, label=label,
                       host=host, port=port, username=username, engine=engine)
        with self._lock:
            self._entries[entry.id] = entry
        try:  
            self.get_schema(entry.id)
        except Exception:  
            logger.exception("schema warm-up failed")
        return entry.public()

    @staticmethod
    def _validate_sqlite_path(raw_path: str) -> str:
        path = os.path.abspath(os.path.expanduser((raw_path or "").strip()))
        if not raw_path or not os.path.isfile(path):
            raise BadRequestError(
                f"SQLite file not found: {path}. Provide the full path to an existing .db/.sqlite file "
                "(relative paths are resolved from the backend's working directory)."
            )
        with open(path, "rb") as fh:
            if fh.read(16) != _SQLITE_MAGIC:
                raise BadRequestError("That file is not a SQLite database.")
        return path

    def _build_engine(self, db_type: str, url: URL) -> Engine:
        timeout = self.settings.query_timeout_seconds
        kwargs: Dict[str, Any] = {"pool_pre_ping": True}
        if db_type == "sqlite":
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs.update(pool_size=5, max_overflow=5, pool_recycle=1800)
            kwargs["connect_args"] = {"connect_timeout": 10}
            if db_type == "mysql":
                kwargs["connect_args"]["read_timeout"] = timeout + 10
        engine = create_engine(url, **kwargs)

        
        
        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_conn: Any, _record: Any) -> None:
            if db_type == "sqlite":
                configure_sqlite(dbapi_conn)
            elif db_type == "postgresql":
                cur = dbapi_conn.cursor()
                cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
                cur.execute(f"SET statement_timeout = {int(timeout * 1000)}")
                cur.close()
                dbapi_conn.commit()
            elif db_type == "mysql":
                cur = dbapi_conn.cursor()
                for stmt in (
                    "SET SESSION TRANSACTION READ ONLY",
                    f"SET SESSION MAX_EXECUTION_TIME = {int(timeout * 1000)}",  
                ):
                    try:
                        cur.execute(stmt)
                    except Exception:
                        logger.info("mysql session option not supported: %s", stmt)
                cur.close()
                dbapi_conn.commit()

        return engine

    def _entry(self, connection_id: str) -> _Entry:
        with self._lock:
            entry = self._entries.get(connection_id)
        if entry is None:
            raise NotFoundError("Connection not found. It may have been closed or the server restarted.")
        return entry

    def get_engine(self, connection_id: str) -> Engine:
        return self._entry(connection_id).engine

    def get_db_type(self, connection_id: str) -> str:
        return self._entry(connection_id).db_type

    def get_connection_info(self, connection_id: str) -> Dict[str, Any]:
        return self._entry(connection_id).public()

    def list_connections(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.public() for e in self._entries.values()]

    def close_connection(self, connection_id: str) -> Dict[str, str]:
        entry = self._entry(connection_id)
        with self._lock:
            self._entries.pop(connection_id, None)
            self._schemas.pop(connection_id, None)
            self._schema_locks.pop(connection_id, None)
        entry.engine.dispose()
        return {"status": "disconnected", "connection_id": connection_id}

    def ping(self, connection_id: str, samples: int = 3) -> Optional[int]:
        """Average round-trip latency in ms, or None if the database is unreachable."""
        engine = self.get_engine(connection_id)
        times: List[float] = []
        try:
            with engine.connect() as conn:
                for _ in range(samples):
                    started = time.perf_counter()
                    run_select(conn.connection, "SELECT 1", 1, 5)
                    times.append((time.perf_counter() - started) * 1000)
        except Exception:
            return None
        return max(1, round(sum(times) / len(times)))

    
    def get_schema(self, connection_id: str, refresh: bool = False) -> SchemaContext:
        entry = self._entry(connection_id)
        with self._lock:
            lock = self._schema_locks.setdefault(connection_id, threading.Lock())
        with lock:  
            cached = self._schemas.get(connection_id)
            fresh = cached is not None and (time.time() - cached.built_at) < self.settings.schema_cache_ttl_seconds
            if cached is not None and fresh and not refresh:
                return cached
            schema = self._introspect(entry)
            with self._lock:
                if connection_id in self._entries:
                    self._schemas[connection_id] = schema
            return schema

    def _introspect(self, entry: _Entry) -> SchemaContext:
        started = time.perf_counter()
        inspector = inspect(entry.engine)
        schema = SchemaContext(database=entry.database, db_type=entry.db_type)
        objects = [(n, "table") for n in inspector.get_table_names()]
        try:
            objects += [(n, "view") for n in inspector.get_view_names()]
        except Exception:  
            logger.info("could not list views for %s", entry.label)

        for name, kind in objects:
            try:
                pk_cols = set(inspector.get_pk_constraint(name).get("constrained_columns") or [])
                columns = []
                for c in inspector.get_columns(name):
                    try:
                        type_name = str(c["type"])
                    except Exception:
                        type_name = ""
                    columns.append(ColumnInfo(
                        name=c["name"], type=type_name, nullable=bool(c.get("nullable", True)),
                        primary_key=c["name"] in pk_cols,
                    ))
                fks = [
                    ForeignKey(list(fk.get("constrained_columns") or []), fk.get("referred_table") or "",
                               list(fk.get("referred_columns") or []))
                    for fk in (inspector.get_foreign_keys(name) if kind == "table" else [])
                    if fk.get("referred_table")
                ]
                schema.tables[name] = TableInfo(name=name, kind=kind, columns=columns, foreign_keys=fks)
            except Exception:
                logger.exception("could not introspect %s", name)

        with entry.engine.connect() as conn:
            raw = conn.connection

            def probe(sql: str) -> RawResult:
                try:
                    return run_select(raw, sql, 100, 5)
                except QueryExecutionError:
                    try:  
                        raw.rollback()
                    except Exception:
                        pass
                    raise

            enrich_schema(schema, probe, self.settings)
        logger.info("introspected %s: %d objects in %.2fs", entry.label, len(schema.tables), time.perf_counter() - started)
        return schema

    
    def run_query(self, connection_id: str, sql: str, max_rows: int, timeout_seconds: int) -> RawResult:
        """Run *already validated* SQL. Callers must go through GuardedExecutor."""
        engine = self.get_engine(connection_id)
        try:
            with engine.connect() as conn:
                raw = conn.connection
                try:
                    return run_select(raw, sql, max_rows, timeout_seconds)
                finally:
                    try:
                        raw.rollback()
                    except Exception:
                        pass
        except QueryExecutionError:
            raise
        except Exception as exc:  
            raise QueryExecutionError(f"Database connection error: {clean_db_error(exc)}") from exc

    
    def build_table_select(self, connection_id: str, table_name: str) -> str:
        schema = self.get_schema(connection_id)
        table = schema.get_table(table_name)
        if table is None:
            raise NotFoundError(f"Table '{table_name}' not found.")
        db_type = self.get_db_type(connection_id)
        sql = f"SELECT * FROM {quote_identifier(table.name, db_type)}"
        if table.primary_keys:
            sql += " ORDER BY " + ", ".join(quote_identifier(c, db_type) for c in table.primary_keys)
        return sql

    def get_table_data(self, connection_id: str, table_name: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        schema = self.get_schema(connection_id)
        table = schema.get_table(table_name)
        if table is None:
            raise NotFoundError(f"Table '{table_name}' not found.")
        limit = max(1, min(int(limit), self.settings.max_rows))
        offset = max(0, int(offset))
        sql = f"{self.build_table_select(connection_id, table.name)} LIMIT {limit} OFFSET {offset}"
        raw = self.run_query(connection_id, sql, limit, self.settings.query_timeout_seconds)
        rows, redacted = redact_rows(raw.columns, raw.rows, schema.restricted_columns(), self.settings.restricted_column_re)
        raw.rows, raw.redacted_columns = rows, redacted

        total = table.row_count
        try:
            db_type = self.get_db_type(connection_id)
            count = self.run_query(
                connection_id, f"SELECT COUNT(*) AS n FROM {quote_identifier(table.name, db_type)}", 1,
                self.settings.query_timeout_seconds,
            )
            total = int(count.rows[0]["n"])
        except Exception:
            pass
        return {**raw.to_dict(), "table": table.name, "total_rows": total, "limit": limit, "offset": offset}
