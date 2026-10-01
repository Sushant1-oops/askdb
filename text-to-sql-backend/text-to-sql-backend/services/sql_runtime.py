"""Low-level, driver-agnostic query execution helpers.

Kept free of SQLAlchemy so the exact code path that runs user/LLM SQL can be
unit-tested against the standard-library ``sqlite3`` driver.

Why raw DBAPI cursors instead of ``sqlalchemy.text()``?
  * ``text()`` treats ``:name`` as a bind parameter, so a literal like
    ``'note :urgent'`` in generated SQL is mangled or raises.
  * ``%`` inside ``LIKE '%foo%'`` is a format specifier for psycopg2/pymysql when
    parameters are passed. Calling ``cursor.execute(sql)`` with *no* parameters
    sidesteps both problems.
"""

from __future__ import annotations

import math
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterator, List, Optional
from uuid import UUID

from services.errors import QueryExecutionError, QueryTimeoutError


_JS_SAFE_INT = 2**53


@dataclass
class RawResult:
    columns: List[str]
    rows: List[Dict[str, Any]]
    truncated: bool = False
    elapsed_ms: int = 0
    redacted_columns: List[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": True,
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "execution_ms": self.elapsed_ms,
            "redacted_columns": self.redacted_columns,
        }



def json_safe(value: Any) -> Any:
    """Convert a DB value to something ``json.dumps(allow_nan=False)`` accepts."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value if abs(value) <= _JS_SAFE_INT else str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        as_float = float(value)
        return as_float if math.isfinite(as_float) else str(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return f"<{len(raw)} bytes>" if len(raw) > 32 else "0x" + raw.hex()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return [json_safe(v) for v in sorted(value, key=str)]
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    return str(value)


def dedupe_columns(names: List[str]) -> List[str]:
    """``SELECT a.id, b.id`` yields two ``id`` columns; keep both addressable."""
    seen: Dict[str, int] = {}
    result: List[str] = []
    for raw in names:
        name = str(raw) if raw not in (None, "") else "column"
        count = seen.get(name, 0)
        seen[name] = count + 1
        result.append(name if count == 0 else f"{name}_{count + 1}")
    return result



_local = threading.local()


@contextmanager
def query_deadline(seconds: Optional[float]) -> Iterator[None]:
    """Arm the per-thread deadline consulted by the SQLite progress handler."""
    previous = getattr(_local, "deadline", None)
    _local.deadline = (time.monotonic() + seconds) if seconds else None
    try:
        yield
    finally:
        _local.deadline = previous


def configure_sqlite(dbapi_conn: Any) -> None:
    """Make a SQLite connection read-only and interruptible.

    ``PRAGMA query_only`` rejects every write at the engine level, which is the
    last line of defence behind the SQL guard. SQLite has no statement timeout,
    so a progress handler aborts queries that outlive their deadline.
    """
    dbapi_conn.execute("PRAGMA query_only = ON")

    def _progress() -> int:
        deadline = getattr(_local, "deadline", None)
        return 1 if deadline is not None and time.monotonic() > deadline else 0

    dbapi_conn.set_progress_handler(_progress, 10_000)



_WRAPPER_TAIL = re.compile(r"\n?\[SQL:.*", re.DOTALL)
_BACKGROUND = re.compile(r"\(Background on this error at:.*?\)", re.DOTALL)
_DRIVER_PREFIX = re.compile(r"^\((?:[\w.]+\.)?\w+(?:Error|Exception)\)\s*", re.IGNORECASE)


def clean_db_error(exc: BaseException) -> str:
    """Reduce a driver/SQLAlchemy exception to a single readable line."""
    message = str(exc).strip()
    message = _WRAPPER_TAIL.sub("", message)
    message = _BACKGROUND.sub("", message)
    message = _DRIVER_PREFIX.sub("", message).strip()
    first_lines = [ln.strip() for ln in message.splitlines() if ln.strip()]
    message = " ".join(first_lines[:2]) if first_lines else exc.__class__.__name__
    return message[:400]


def _is_timeout(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "interrupted",  
            "statement timeout",  
            "maximum statement execution time",  
            "max_execution_time",
            "query execution was interrupted",
        )
    )



def run_select(
    dbapi_conn: Any,
    sql: str,
    max_rows: int,
    timeout_seconds: Optional[float] = None,
) -> RawResult:
    """Run one statement on a DBAPI connection and fetch at most ``max_rows`` rows.

    ``max_rows + 1`` rows are requested so we can tell the caller whether the
    result was truncated without loading the whole set.
    """
    started = time.perf_counter()
    cursor = dbapi_conn.cursor()
    try:
        with query_deadline(timeout_seconds):
            cursor.execute(sql)
            if cursor.description is None:
                raise QueryExecutionError("The statement did not return any rows.")
            columns = dedupe_columns([d[0] for d in cursor.description])
            fetched = cursor.fetchmany(max_rows + 1)
    except QueryExecutionError:
        raise
    except Exception as exc:  
        message = clean_db_error(exc)
        if _is_timeout(message):
            raise QueryTimeoutError(
                f"The query took longer than {int(timeout_seconds or 0)}s and was cancelled. "
                "Try filtering the data or selecting fewer columns."
            ) from exc
        raise QueryExecutionError(message) from exc
    finally:
        try:
            cursor.close()
        except Exception:  
            pass

    truncated = len(fetched) > max_rows
    rows = [
        {columns[i]: json_safe(value) for i, value in enumerate(row)}
        for row in fetched[:max_rows]
    ]
    return RawResult(
        columns=columns,
        rows=rows,
        truncated=truncated,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


def quote_identifier(name: str, db_type: str) -> str:
    """Quote a table/column identifier, escaping embedded quote characters."""
    if db_type == "mysql":
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.replace('"', '""') + '"'
