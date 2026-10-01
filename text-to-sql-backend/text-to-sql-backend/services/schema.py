"""Database schema model.

``SchemaContext`` is the single description of a database used by every other
component: the LLM prompt builder, the SQL guard (allowed tables / restricted
columns), the result redactor and the REST API. It is built once per connection
by ``DatabaseService`` and cached.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

MASK = "[REDACTED]"
_MAX_CELL_CHARS = 40


@dataclass
class ColumnInfo:
    name: str
    type: str = ""
    nullable: bool = True
    primary_key: bool = False
    restricted: bool = False
    
    
    values: List[str] = field(default_factory=list)
    min_value: Optional[str] = None
    max_value: Optional[str] = None


@dataclass
class ForeignKey:
    columns: List[str]
    ref_table: str
    ref_columns: List[str]


@dataclass
class TableInfo:
    name: str
    kind: str = "table"  
    columns: List[ColumnInfo] = field(default_factory=list)
    foreign_keys: List[ForeignKey] = field(default_factory=list)
    sample_rows: List[Dict[str, Any]] = field(default_factory=list)
    row_count: Optional[int] = None

    def column(self, name: str) -> Optional[ColumnInfo]:
        lowered = name.lower()
        for col in self.columns:
            if col.name.lower() == lowered:
                return col
        return None

    @property
    def primary_keys(self) -> List[str]:
        return [c.name for c in self.columns if c.primary_key]


@dataclass
class SchemaContext:
    database: str
    db_type: str
    tables: Dict[str, TableInfo] = field(default_factory=dict)
    built_at: float = field(default_factory=time.time)

    
    def table_names(self) -> List[str]:
        return list(self.tables.keys())

    def restricted_columns(self) -> Set[str]:
        """Lower-cased names of every restricted column across all tables."""
        return {c.name.lower() for t in self.tables.values() for c in t.columns if c.restricted}

    def get_table(self, name: str) -> Optional[TableInfo]:
        if name in self.tables:
            return self.tables[name]
        lowered = name.lower()
        for key, table in self.tables.items():
            if key.lower() == lowered:
                return table
        return None

    @property
    def column_count(self) -> int:
        return sum(len(t.columns) for t in self.tables.values())

    @property
    def total_rows(self) -> int:
        return sum(t.row_count or 0 for t in self.tables.values())

    
    def render_ddl(
        self,
        table_names: Optional[Iterable[str]] = None,
        *,
        include_samples: bool = True,
        sample_rows: int = 2,
    ) -> str:
        """Compact, LLM-friendly DDL for the requested tables.

        Restricted columns are omitted entirely, so the model cannot select
        what it never saw. Values coming from the database are wrapped in
        comments and truncated: they are data, not instructions.
        """
        names = list(table_names) if table_names is not None else self.table_names()
        blocks: List[str] = []
        for name in names:
            table = self.tables.get(name)
            if table is None:
                continue
            visible = [c for c in table.columns if not c.restricted]
            header = f"-- {table.kind.upper()} {table.name}"
            if table.row_count is not None:
                header += f" (~{table.row_count:,} rows)"
            lines = [header, f"CREATE TABLE {table.name} ("]
            entries: List[Tuple[str, str]] = []  
            for col in visible:
                parts = [f"  {col.name} {col.type or 'TEXT'}"]
                if col.primary_key:
                    parts.append("PRIMARY KEY")
                if not col.nullable and not col.primary_key:
                    parts.append("NOT NULL")
                hints: List[str] = []
                if include_samples and col.values:
                    shown = ", ".join(repr(_clip(v)) for v in col.values)
                    hints.append(f"values: {shown}")
                if include_samples and (col.min_value is not None or col.max_value is not None):
                    hints.append(f"range: {_clip(col.min_value)} .. {_clip(col.max_value)}")
                entries.append((" ".join(parts), f"  -- {'; '.join(hints)}" if hints else ""))
            hidden = {c.name for c in table.columns if c.restricted}
            for fk in table.foreign_keys:
                if set(fk.columns) & hidden:
                    continue
                entries.append(
                    (f"  FOREIGN KEY ({', '.join(fk.columns)}) REFERENCES {fk.ref_table}({', '.join(fk.ref_columns)})", "")
                )
            rendered = [
                f"{definition}{',' if idx < len(entries) - 1 else ''}{comment}"
                for idx, (definition, comment) in enumerate(entries)
            ]
            lines.extend(rendered)
            lines.append(");")
            if include_samples and table.sample_rows:
                visible_names = {c.name for c in visible}
                for row in table.sample_rows[:sample_rows]:
                    safe = {k: _clip(v) for k, v in row.items() if k in visible_names}
                    lines.append(f"-- sample: {safe}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    
    def to_api(self) -> Dict[str, Any]:
        """Serialisable form for the frontend (no sample rows)."""
        return {
            "database": self.database,
            "db_type": self.db_type,
            "built_at": self.built_at,
            "stats": {
                "tables": sum(1 for t in self.tables.values() if t.kind == "table"),
                "views": sum(1 for t in self.tables.values() if t.kind == "view"),
                "columns": self.column_count,
                "rows": self.total_rows,
            },
            "tables": [self.table_to_api(t) for t in self.tables.values()],
        }

    @staticmethod
    def table_to_api(table: TableInfo) -> Dict[str, Any]:
        return {
            "name": table.name,
            "kind": table.kind,
            "row_count": table.row_count,
            "primary_keys": table.primary_keys,
            "columns": [
                {
                    "name": c.name,
                    "type": c.type,
                    "nullable": c.nullable,
                    "primary_key": c.primary_key,
                    "restricted": c.restricted,
                }
                for c in table.columns
            ],
            "foreign_keys": [
                {"columns": fk.columns, "ref_table": fk.ref_table, "ref_columns": fk.ref_columns}
                for fk in table.foreign_keys
            ],
        }


def _clip(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value).replace("\n", " ")
    return text if len(text) <= _MAX_CELL_CHARS else text[: _MAX_CELL_CHARS - 1] + "…"
