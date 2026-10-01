"""Schema linking: choose which tables to show the LLM.

Small databases are sent whole. For large ones we score every table against the
question (table-name, column-name and known-value matches), then pull in
foreign-key neighbours of the best hits so joins remain possible. Deterministic,
dependency-free and fast; no embedding model needed.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set

from services.schema import SchemaContext, TableInfo

_STOPWORDS: Set[str] = {
    "a", "an", "the", "of", "in", "on", "for", "to", "and", "or", "by", "with", "from", "at", "is", "are",
    "was", "were", "be", "me", "my", "our", "show", "list", "give", "get", "find", "what", "which", "who",
    "how", "many", "much", "all", "each", "per", "top", "most", "least", "last", "this", "that", "have",
    "has", "do", "does", "did", "than", "then", "their", "them", "it", "its", "as", "i", "we", "you",
    "please", "tell", "number", "total", "count", "average", "avg", "sum", "between", "over", "under",
}


def _stem(word: str) -> str:
    for suffix in ("ies", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def tokens(text: str) -> Set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)  
    words = re.findall(r"[a-zA-Z0-9]+", spaced.lower())
    return {_stem(w) for w in words if w not in _STOPWORDS and len(w) > 1}


def _score(table: TableInfo, question_tokens: Set[str], question_lower: str) -> float:
    score = 0.0
    name_tokens = tokens(table.name.replace("_", " "))
    score += 3.0 * len(name_tokens & question_tokens)
    for col in table.columns:
        if col.restricted:
            continue
        col_tokens = tokens(col.name.replace("_", " "))
        score += 1.5 * len(col_tokens & question_tokens)
        for value in col.values:
            if len(value) > 2 and value.lower() in question_lower:
                score += 2.0
    return score


def select_tables(
    schema: SchemaContext,
    question: str,
    history_text: str = "",
    *,
    max_tables: int = 12,
) -> List[str]:
    """Return table names to include in the prompt (all of them if the DB is small)."""
    names = schema.table_names()
    if len(names) <= max_tables:
        return names

    text = f"{question} {history_text}".strip()
    q_tokens = tokens(text)
    q_lower = text.lower()
    scores: Dict[str, float] = {n: _score(schema.tables[n], q_tokens, q_lower) for n in names}

    ranked = sorted(names, key=lambda n: (-scores[n], n))
    chosen: List[str] = [n for n in ranked if scores[n] > 0][: max(3, max_tables // 2)]

    
    def neighbours(name: str) -> Iterable[str]:
        table = schema.tables[name]
        for fk in table.foreign_keys:
            if fk.ref_table in schema.tables:
                yield fk.ref_table
        for other in schema.tables.values():
            if any(fk.ref_table == name for fk in other.foreign_keys):
                yield other.name

    for name in list(chosen[:4]):
        for nb in neighbours(name):
            if nb not in chosen and len(chosen) < max_tables:
                chosen.append(nb)

    
    if not chosen:
        chosen = sorted(names, key=lambda n: -(schema.tables[n].row_count or 0))[:max_tables]

    return [n for n in names if n in set(chosen)][:max_tables]
