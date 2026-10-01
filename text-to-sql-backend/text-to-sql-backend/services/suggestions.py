"""Schema-derived starter questions (no LLM call, deterministic)."""

from __future__ import annotations

import re
from typing import List

from services.schema import SchemaContext, TableInfo

_NUMERIC = re.compile(r"INT|NUMERIC|DECIMAL|REAL|FLOAT|DOUBLE|MONEY|NUMBER", re.I)
_DATEISH = re.compile(r"DATE|TIME", re.I)
_DATE_NAME = re.compile(r"(date|_at|_on)$", re.I)
_MEASURE_NAME = re.compile(r"(amount|total|price|revenue|cost|quantity|qty|salary|score|sales|value|count)", re.I)


def _human(name: str) -> str:
    return name.replace("_", " ").strip().lower()


def _date_col(table: TableInfo):
    for c in table.columns:
        if not c.restricted and (_DATEISH.search(c.type) or _DATE_NAME.search(c.name)):
            return c
    return None


def _measure_col(table: TableInfo):
    for c in table.columns:
        if c.restricted or c.primary_key or c.name.lower().endswith("id"):
            continue
        if _NUMERIC.search(c.type) and _MEASURE_NAME.search(c.name):
            return c
    return None


def suggest_questions(schema: SchemaContext, limit: int = 6) -> List[str]:
    tables = [t for t in schema.tables.values() if t.kind == "table" and t.columns]
    tables.sort(key=lambda t: -(t.row_count or 0))
    out: List[str] = []

    def add(q: str) -> None:
        if q not in out:
            out.append(q)

    for t in tables[:3]:
        add(f"How many {_human(t.name)} are there?")
        date_col = _date_col(t)
        measure = _measure_col(t)
        if date_col and measure:
            add(f"What is the monthly trend of {_human(measure.name)} in {_human(t.name)}?")
        elif date_col:
            add(f"Show the 10 most recent {_human(t.name)}.")
        for c in t.columns:
            if c.values and 2 <= len(c.values) <= 8 and not c.restricted:
                add(f"How many {_human(t.name)} are there for each {_human(c.name)}?")
                break

    for t in tables:
        measure = _measure_col(t)
        for fk in t.foreign_keys:
            parent = schema.tables.get(fk.ref_table)
            if parent and measure:
                add(f"Which {_human(parent.name)} have the highest total {_human(measure.name)} in {_human(t.name)}?")
                break
    return out[:limit]
