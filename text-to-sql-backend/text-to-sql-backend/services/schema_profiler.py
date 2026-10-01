"""Enrich a structural schema with data-derived hints for the LLM.

Given a ``SchemaContext`` holding only structure (tables, columns, keys), fill in
row counts, a few sample rows, the distinct values of low-cardinality text
columns, and min/max of date columns. Every probe is a small bounded query and the
whole pass has a time budget, so large databases degrade gracefully (fewer hints)
instead of stalling the connect flow.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, Optional

from config import Settings
from services.errors import QueryExecutionError
from services.schema import SchemaContext, TableInfo
from services.sql_runtime import RawResult, quote_identifier

logger = logging.getLogger(__name__)

RunSQL = Callable[[str], RawResult]

_TEXT_TYPE = re.compile(r"CHAR|TEXT|STRING|ENUM|CLOB|VARCHAR", re.I)
_DATE_TYPE = re.compile(r"DATE|TIME", re.I)
_DATE_NAME = re.compile(r"(date|_at|_on|timestamp)$", re.I)
_FREE_TEXT_NAME = re.compile(r"(email|phone|address|url|uri|name|description|comment|note|body|title|hash)", re.I)
_SAMPLE_WINDOW = 2000


def mark_restricted(schema: SchemaContext, settings: Settings) -> None:
    pattern = settings.restricted_column_re
    for table in schema.tables.values():
        for col in table.columns:
            col.restricted = bool(pattern.search(col.name))


def enrich_schema(schema: SchemaContext, run_sql: RunSQL, settings: Settings) -> SchemaContext:
    mark_restricted(schema, settings)
    deadline = time.monotonic() + settings.profile_budget_seconds
    db_type = schema.db_type

    for table in schema.tables.values():
        if time.monotonic() > deadline:
            logger.info("schema profiling budget exhausted; remaining tables get no hints")
            break
        _profile_table(table, run_sql, db_type, settings, deadline)
    return schema


def _profile_table(table: TableInfo, run_sql: RunSQL, db_type: str, settings: Settings, deadline: float) -> None:
    q = lambda name: quote_identifier(name, db_type)  
    qt = q(table.name)
    visible = [c for c in table.columns if not c.restricted]

    try:
        table.row_count = int(run_sql(f"SELECT COUNT(*) AS n FROM {qt}").rows[0]["n"])
    except (QueryExecutionError, IndexError, KeyError, TypeError, ValueError):
        table.row_count = None

    if not visible:
        return
    select_list = ", ".join(q(c.name) for c in visible)
    try:
        table.sample_rows = run_sql(f"SELECT {select_list} FROM {qt} LIMIT 3").rows
    except QueryExecutionError:
        table.sample_rows = []

    if not table.row_count:
        return

    for col in visible:
        if time.monotonic() > deadline:
            return
        qc = q(col.name)
        is_text = bool(_TEXT_TYPE.search(col.type))
        is_date = bool(_DATE_TYPE.search(col.type)) or (is_text and bool(_DATE_NAME.search(col.name)))
        try:
            if is_text and not is_date and not col.primary_key and not _FREE_TEXT_NAME.search(col.name):
                limit = settings.sample_values_max + 1
                res = run_sql(
                    f"SELECT DISTINCT {qc} AS v FROM (SELECT {qc} FROM {qt} LIMIT {_SAMPLE_WINDOW}) AS s "
                    f"WHERE {qc} IS NOT NULL LIMIT {limit}"
                )
                values = [str(r["v"]) for r in res.rows]
                if 0 < len(values) <= settings.sample_values_max:
                    col.values = sorted(values)
            elif is_date:
                res = run_sql(f"SELECT MIN({qc}) AS lo, MAX({qc}) AS hi FROM {qt}")
                if res.rows and res.rows[0].get("lo") is not None:
                    col.min_value, col.max_value = str(res.rows[0]["lo"]), str(res.rows[0]["hi"])
        except QueryExecutionError:
            continue
