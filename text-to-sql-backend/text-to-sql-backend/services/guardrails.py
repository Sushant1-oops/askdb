"""Guardrails.

Defence in depth for LLM-generated (and user-typed) SQL:

  1. ``InputGuard``  – screens the natural-language question before any LLM call.
  2. ``SQLGuard``    – lexes the SQL (aware of strings, comments, identifiers and
                       per-dialect escaping) and enforces a read-only policy:
                       one statement, SELECT/WITH only, no data-modifying CTEs,
                       no dangerous functions, no system catalogs, only known
                       tables, no restricted columns, a LIMIT always present.
  3. ``redact_rows`` – masks restricted columns in results, whatever the SQL did.
  4. The database session itself is read-only with a statement timeout
     (configured in ``DatabaseService``), so even a guard bypass cannot write.

The guard works on a token stream instead of regexes over raw text, so keywords
inside string literals / comments / quoted identifiers never cause false
positives, and payloads hidden in them never cause false negatives. The SQL that
is executed is *re-assembled from the tokens the guard inspected* (comments
stripped), so what was validated is exactly what runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Pattern, Sequence, Set, Tuple

MAX_SQL_CHARS = 20_000
MASK = "[REDACTED]"



class Token(NamedTuple):
    kind: str  
    text: str


class LexError(ValueError):
    pass


_WORD = re.compile(r"[A-Za-z_\u0080-\uffff][A-Za-z0-9_$\u0080-\uffff]*")
_NUMBER = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def _scan_quoted(sql: str, start: int, quote: str, backslash_escapes: bool) -> int:
    """Return the index just past the closing quote of the literal at ``start``."""
    n = len(sql)
    i = start + 1
    while i < n:
        ch = sql[i]
        if backslash_escapes and ch == "\\":
            i += 2
            continue
        if ch == quote:
            if i + 1 < n and sql[i + 1] == quote:  
                i += 2
                continue
            return i + 1
        i += 1
    raise LexError(f"Unterminated {quote} quoted text")


def _scan_block_comment(sql: str, start: int, nested: bool) -> int:
    n = len(sql)
    depth = 1
    i = start + 2
    while i < n:
        if nested and sql.startswith("/*", i):
            depth += 1
            i += 2
        elif sql.startswith("*/", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    raise LexError("Unterminated /* comment")


def tokenize(sql: str, dialect: str = "sqlite") -> List[Token]:
    """Split SQL into tokens. Raises ``LexError`` on unterminated literals/comments."""
    n = len(sql)
    i = 0
    out: List[Token] = []
    mysql = dialect == "mysql"
    postgres = dialect == "postgresql"

    while i < n:
        ch = sql[i]

        if ch.isspace():
            j = i + 1
            while j < n and sql[j].isspace():
                j += 1
            out.append(Token("ws", sql[i:j]))
            i = j
            continue

        if sql.startswith("--", i) or (mysql and ch == "#"):
            j = sql.find("\n", i)
            j = n if j == -1 else j
            out.append(Token("comment", sql[i:j]))
            i = j
            continue

        if sql.startswith("/*", i):
            j = _scan_block_comment(sql, i, nested=postgres)
            out.append(Token("comment", sql[i:j]))
            i = j
            continue

        if ch == "'":
            e_string = postgres and bool(out) and out[-1].kind == "word" and out[-1].text in ("e", "E")
            j = _scan_quoted(sql, i, "'", backslash_escapes=mysql or e_string)
            out.append(Token("string", sql[i:j]))
            i = j
            continue

        if ch == '"':
            j = _scan_quoted(sql, i, '"', backslash_escapes=mysql)
            out.append(Token("ident", sql[i:j]))
            i = j
            continue

        if ch == "`":
            j = _scan_quoted(sql, i, "`", backslash_escapes=False)
            out.append(Token("ident", sql[i:j]))
            i = j
            continue

        if ch == "$" and postgres:
            prev_is_word = bool(out) and out[-1].kind == "word"
            m = _DOLLAR_TAG.match(sql, i)
            if m and not prev_is_word:
                tag = m.group()
                close = sql.find(tag, m.end())
                if close == -1:
                    raise LexError("Unterminated dollar-quoted string")
                j = close + len(tag)
                out.append(Token("string", sql[i:j]))
                i = j
                continue

        if ch.isdigit() or (ch == "." and i + 1 < n and sql[i + 1].isdigit()):
            m = _NUMBER.match(sql, i)
            assert m is not None
            out.append(Token("number", m.group()))
            i = m.end()
            continue

        m = _WORD.match(sql, i)
        if m:
            out.append(Token("word", m.group()))
            i = m.end()
            continue

        out.append(Token("punct", ch))
        i += 1

    return out


def _ident_name(token: Token) -> str:
    """Lower-cased identifier text without its quoting."""
    text = token.text
    if token.kind == "ident" and len(text) >= 2:
        quote = text[0]
        text = text[1:-1].replace(quote * 2, quote)
    return text.lower()


def first_statement(sql: str, dialect: str = "sqlite") -> str:
    """Cut ``sql`` at the first top-level ';' (used when extracting LLM output)."""
    try:
        tokens = tokenize(sql, dialect)
    except LexError:
        return sql.strip().rstrip(";").strip()
    parts: List[str] = []
    for tok in tokens:
        if tok.kind == "punct" and tok.text == ";":
            break
        parts.append(tok.text)
    return "".join(parts).strip()






FORBIDDEN_KEYWORDS: Set[str] = {
    "insert", "update", "delete", "merge", "replace", "truncate", "into",
    "drop", "alter", "create", "grant", "revoke", "attach", "detach",
    "pragma", "vacuum",
}

KEYWORDS_ALLOWED_AS_FUNCTION: Set[str] = {"insert", "replace", "truncate"}

FORBIDDEN_FUNCTIONS: Set[str] = {
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "pg_terminate_backend", "pg_cancel_backend", "pg_advisory_lock", "lo_import",
    "lo_export", "dblink", "dblink_exec", "set_config", "load_extension",
    "readfile", "writefile", "sleep", "benchmark", "load_file", "sys_exec",
    "sys_eval", "xp_cmdshell",
}

SYSTEM_CATALOGS: Set[str] = {
    "information_schema", "performance_schema", "pg_catalog", "pg_toast",
    "sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema",
    "sqlite_sequence",
}
SYSTEM_SCHEMA_PREFIXES: Tuple[str, ...] = ("pg_", "sqlite_")
SYSTEM_QUALIFIERS: Set[str] = {"mysql", "sys"}  


FROM_FUNCTIONS: Set[str] = {"extract", "trim", "substring", "overlay", "substr"}

_CLAUSE_WORDS: Set[str] = {
    "where", "group", "order", "having", "limit", "offset", "fetch", "union",
    "intersect", "except", "join", "inner", "left", "right", "full", "cross",
    "natural", "on", "using", "window", "for", "returning", "lateral", "straight_join",
}
_ALWAYS_OK_TABLES: Set[str] = {"dual"}


@dataclass
class Violation:
    code: str
    message: str
    
    
    security: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "security": self.security}


@dataclass
class GuardResult:
    ok: bool
    sql: str
    violations: List[Violation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)
    limit_applied: bool = False

    @property
    def has_security_violation(self) -> bool:
        return any(v.security for v in self.violations)

    @property
    def message(self) -> str:
        return "; ".join(v.message for v in self.violations)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.ok,
            "violations": [v.to_dict() for v in self.violations],
            "warnings": self.warnings,
            "tables": self.tables,
            "limit_applied": self.limit_applied,
            "read_only": True,
        }


class SQLGuard:
    """Validate and normalise one SQL statement against a schema."""

    def __init__(
        self,
        tables: Iterable[str],
        *,
        restricted_columns: Iterable[str] = (),
        dialect: str = "sqlite",
        max_rows: int = 1000,
        enforce_limit: bool = True,
    ) -> None:
        self.tables = {t.lower() for t in tables}
        self.restricted = {c.lower() for c in restricted_columns}
        self.dialect = dialect
        self.max_rows = max_rows
        self.enforce_limit = enforce_limit

    
    def validate(self, sql: Optional[str]) -> GuardResult:
        if sql is None or not sql.strip():
            return self._fail("EMPTY", "The query is empty.")
        if len(sql) > MAX_SQL_CHARS:
            return self._fail("TOO_LONG", f"The query is longer than {MAX_SQL_CHARS:,} characters.")

        try:
            tokens = tokenize(sql, self.dialect)
        except LexError as exc:
            return self._fail("UNPARSABLE", f"The query could not be parsed: {exc}.")

        had_comments = any(t.kind == "comment" for t in tokens)
        tokens = self._strip_trailing_semicolons(tokens)
        sig = [t for t in tokens if t.kind not in ("ws", "comment")]
        if not sig:
            return self._fail("EMPTY", "The query is empty.")

        violations: List[Violation] = []
        warnings: List[str] = []
        if had_comments:
            warnings.append("SQL comments were removed before execution.")

        
        if any(t.kind == "punct" and t.text == ";" for t in sig):
            violations.append(
                Violation("MULTI_STATEMENT", "Only a single SQL statement is allowed.", security=True)
            )

        
        head = next((t for t in sig if not (t.kind == "punct" and t.text == "(")), None)
        if head is None or head.kind != "word" or head.text.lower() not in ("select", "with"):
            violations.append(
                Violation("NOT_READ_ONLY", "Only SELECT queries are allowed (AskDB is read-only).", security=True)
            )

        violations.extend(self._scan_tokens(sig))

        
        ctes = self._cte_names(sig)
        referenced = self._referenced_tables(sig)
        unknown: List[str] = []
        known: List[str] = []
        for name in referenced:
            if name in self.tables:
                if name not in known:
                    known.append(name)
            elif name in ctes or name in _ALWAYS_OK_TABLES:
                continue
            elif name not in unknown:
                unknown.append(name)
        if unknown:
            violations.append(
                Violation(
                    "UNKNOWN_TABLE",
                    "Unknown table(s): " + ", ".join(unknown) + ". Use only tables from the schema.",
                )
            )

        
        cleaned = "".join(" " if t.kind == "comment" else t.text for t in tokens).strip()
        limit_applied = False
        if not violations and self.enforce_limit and not self._has_top_level_limit(sig):
            
            cleaned = f"{cleaned} LIMIT {self.max_rows + 1}"
            limit_applied = True
            warnings.append(f"A LIMIT of {self.max_rows:,} rows was added.")

        return GuardResult(
            ok=not violations,
            sql=cleaned,
            violations=violations,
            warnings=warnings,
            tables=known,
            limit_applied=limit_applied,
        )

    
    def _fail(self, code: str, message: str, security: bool = False) -> GuardResult:
        return GuardResult(ok=False, sql="", violations=[Violation(code, message, security)])

    @staticmethod
    def _strip_trailing_semicolons(tokens: List[Token]) -> List[Token]:
        end = len(tokens)
        while end > 0:
            tok = tokens[end - 1]
            if tok.kind in ("ws", "comment") or (tok.kind == "punct" and tok.text == ";"):
                end -= 1
            else:
                break
        return tokens[:end]

    def _scan_tokens(self, sig: Sequence[Token]) -> List[Violation]:
        found: List[Violation] = []
        seen_codes: Set[Tuple[str, str]] = set()

        def add(code: str, message: str, security: bool) -> None:
            key = (code, message)
            if key not in seen_codes:
                seen_codes.add(key)
                found.append(Violation(code, message, security))

        for idx, tok in enumerate(sig):
            nxt = sig[idx + 1] if idx + 1 < len(sig) else None
            followed_by_paren = nxt is not None and nxt.kind == "punct" and nxt.text == "("
            followed_by_dot = nxt is not None and nxt.kind == "punct" and nxt.text == "."

            if tok.kind == "word":
                low = tok.text.lower()
                if low in FORBIDDEN_KEYWORDS and not (low in KEYWORDS_ALLOWED_AS_FUNCTION and followed_by_paren):
                    add("FORBIDDEN_KEYWORD", f"'{tok.text.upper()}' is not allowed: AskDB only runs read-only queries.", True)
                if low in FORBIDDEN_FUNCTIONS and followed_by_paren:
                    add("FORBIDDEN_FUNCTION", f"The function {tok.text}() is not allowed.", True)

            if tok.kind in ("word", "ident"):
                name = _ident_name(tok)
                if name in SYSTEM_CATALOGS or (
                    name.startswith(SYSTEM_SCHEMA_PREFIXES) and name not in self.tables
                ):
                    add("SYSTEM_CATALOG", "Access to system catalogs is not allowed.", True)
                if name in SYSTEM_QUALIFIERS and followed_by_dot and name not in self.tables:
                    add("SYSTEM_CATALOG", "Access to system schemas is not allowed.", True)
                if name in self.restricted:
                    add("RESTRICTED_COLUMN", f"The column '{name}' is restricted and cannot be queried.", True)
        return found

    @staticmethod
    def _cte_names(sig: Sequence[Token]) -> Set[str]:
        """Names introduced by ``name [(cols)] AS [MATERIALIZED] (`` (CTEs / WINDOW)."""
        names: Set[str] = set()
        for idx, tok in enumerate(sig):
            if not (tok.kind == "punct" and tok.text == "("):
                continue
            j = idx - 1
            while j >= 0 and sig[j].kind == "word" and sig[j].text.lower() in ("materialized", "not"):
                j -= 1
            if j < 1 or not (sig[j].kind == "word" and sig[j].text.lower() == "as"):
                continue
            k = j - 1
            if sig[k].kind == "punct" and sig[k].text == ")":  
                depth = 0
                while k >= 0:
                    if sig[k].kind == "punct" and sig[k].text == ")":
                        depth += 1
                    elif sig[k].kind == "punct" and sig[k].text == "(":
                        depth -= 1
                        if depth == 0:
                            break
                    k -= 1
                k -= 1
            if k >= 0 and sig[k].kind in ("word", "ident"):
                names.add(_ident_name(sig[k]))
        return names

    def _referenced_tables(self, sig: Sequence[Token]) -> List[str]:
        refs: List[str] = []
        paren_owner: List[str] = []  

        def is_punct(tok: Optional[Token], ch: str) -> bool:
            return tok is not None and tok.kind == "punct" and tok.text == ch

        n = len(sig)

        def skip_parens(pos: int) -> int:
            """``sig[pos]`` is '('; return the index just past its matching ')'."""
            depth = 0
            while pos < n:
                if is_punct(sig[pos], "("):
                    depth += 1
                elif is_punct(sig[pos], ")"):
                    depth -= 1
                    if depth == 0:
                        return pos + 1
                pos += 1
            return pos

        def skip_alias(pos: int) -> int:
            if pos < n and sig[pos].kind == "word" and sig[pos].text.lower() == "as":
                return pos + 2 if pos + 1 < n else pos + 1
            if pos < n and sig[pos].kind in ("word", "ident") and not (
                sig[pos].kind == "word" and sig[pos].text.lower() in _CLAUSE_WORDS
            ):
                return pos + 1
            return pos

        def parse_ref(pos: int) -> Tuple[Optional[str], int]:
            """Parse one table reference at ``pos``; return (table name | None, next_pos)."""
            while pos < n and sig[pos].kind == "word" and sig[pos].text.lower() in ("lateral", "only"):
                pos += 1
            if pos >= n:
                return None, pos
            if is_punct(sig[pos], "("):  
                return None, skip_alias(skip_parens(pos))
            if sig[pos].kind not in ("word", "ident"):
                return None, pos
            parts = [_ident_name(sig[pos])]
            pos += 1
            while pos + 1 < n and is_punct(sig[pos], ".") and sig[pos + 1].kind in ("word", "ident"):
                parts.append(_ident_name(sig[pos + 1]))
                pos += 2
            if pos < n and is_punct(sig[pos], "("):  
                return None, skip_alias(skip_parens(pos))
            return parts[-1], skip_alias(pos)

        for idx, tok in enumerate(sig):
            if is_punct(tok, "("):
                prev = sig[idx - 1] if idx > 0 else None
                paren_owner.append(prev.text.lower() if prev is not None and prev.kind == "word" else "")
                continue
            if is_punct(tok, ")"):
                if paren_owner:
                    paren_owner.pop()
                continue
            if tok.kind != "word":
                continue
            low = tok.text.lower()
            if low == "join":
                name, _ = parse_ref(idx + 1)
                if name:
                    refs.append(name)
            elif low == "from":
                if paren_owner and paren_owner[-1] in FROM_FUNCTIONS:
                    continue
                prev = sig[idx - 1] if idx > 0 else None
                if prev is not None and prev.kind == "word" and prev.text.lower() == "distinct":
                    continue  
                pos = idx + 1
                while True:
                    name, pos = parse_ref(pos)
                    if name:
                        refs.append(name)
                    if pos < len(sig) and is_punct(sig[pos], ","):
                        pos += 1
                        continue
                    break
        return refs

    @staticmethod
    def _has_top_level_limit(sig: Sequence[Token]) -> bool:
        depth = 0
        for tok in sig:
            if tok.kind == "punct" and tok.text == "(":
                depth += 1
            elif tok.kind == "punct" and tok.text == ")":
                depth -= 1
            elif depth == 0 and tok.kind == "word" and tok.text.lower() in ("limit", "fetch"):
                return True
        return False



@dataclass
class InputCheck:
    ok: bool
    code: str = ""
    message: str = ""


_INJECTION_PATTERNS: List[Pattern[str]] = [
    re.compile(r"ignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|prompts?|rules|messages)", re.I),
    re.compile(r"disregard\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)", re.I),
    re.compile(r"(?:reveal|show|print|repeat|display|leak|output)\b.{0,40}\b(?:system|hidden|initial|developer)\s+(?:prompt|instructions?|message)", re.I),
    re.compile(r"\byou\s+are\s+now\s+(?:a|an|in)\b", re.I),
    re.compile(r"\b(?:jailbreak|DAN\s+mode|developer\s+mode)\b", re.I),
    re.compile(r"</?\s*(?:system|assistant|user)\s*>|<\|[a-z_]+\|>", re.I),
]
_WRITE_INTENT = re.compile(
    r"^\s*(?:(?:please|kindly)\s+)?(?:(?:can|could|would)\s+you\s+)?"
    r"(?:delete|drop|truncate|wipe|erase|purge|destroy|insert\s+into|alter\s+table|create\s+table|grant|revoke)\b",
    re.I,
)


class InputGuard:
    def __init__(self, max_chars: int = 1000) -> None:
        self.max_chars = max_chars

    def check(self, question: Optional[str]) -> InputCheck:
        text = (question or "").strip()
        if not text:
            return InputCheck(False, "EMPTY", "Please enter a question.")
        if len(text) > self.max_chars:
            return InputCheck(
                False, "TOO_LONG", f"Questions are limited to {self.max_chars} characters (yours is {len(text)})."
            )
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                return InputCheck(
                    False,
                    "PROMPT_INJECTION",
                    "That looks like an attempt to change how the assistant behaves. "
                    "Ask a question about your data instead.",
                )
        if _WRITE_INTENT.search(text):
            return InputCheck(
                False,
                "WRITE_INTENT",
                "AskDB is read-only, so it can't change or delete data. "
                "Try asking to view or analyse the data instead.",
            )
        return InputCheck(True)



def redact_rows(
    columns: Sequence[str],
    rows: List[Dict[str, Any]],
    restricted_names: Set[str],
    pattern: Optional[Pattern[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Mask restricted columns in a result set. Returns (rows, redacted_columns)."""
    redacted = [
        c
        for c in columns
        if c.lower() in restricted_names or (pattern is not None and pattern.search(c.lower()))
    ]
    if not redacted:
        return rows, []
    masked = set(redacted)
    return [{k: (MASK if k in masked and v is not None else v) for k, v in row.items()} for row in rows], redacted
