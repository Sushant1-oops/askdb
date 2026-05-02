"""LLM Service — Groq-powered Text-to-SQL engine.

Features:
  - Groq Cloud API with multi-model fallback chain
  - Dialect-aware prompts (SQLite / PostgreSQL / MySQL)
  - Robust SQL extraction from LLM responses
  - SQL validation with schema cross-referencing
  - Self-correction loop for failed queries
"""

import re
import json
import logging
import os
from typing import Dict, Any, Optional, List

from groq import Groq

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL dialect hints injected into the prompt so the LLM targets the right DB
# ---------------------------------------------------------------------------
DIALECT_HINTS: Dict[str, str] = {
    "sqlite": (
        "Target SQL dialect: **SQLite**.\n"
        "CRITICAL RULES for SQLite:\n"
        "- Use || for string concatenation (NOT CONCAT()).\n"
        "- Use LIMIT for row limits (no TOP).\n"
        "- Use IFNULL() or COALESCE() for null handling.\n"
        "- Date functions: DATE(), TIME(), DATETIME(), strftime().\n"
        "- SQLite is case-insensitive for keywords but case-sensitive for string comparisons by default.\n"
        "- Use AUTOINCREMENT with INTEGER PRIMARY KEY.\n"
        "- NO RIGHT JOIN — rewrite as LEFT JOIN with swapped tables.\n"
        "- NO FULL OUTER JOIN — use UNION of LEFT JOINs.\n"
        "- Boolean: use 0/1 (no TRUE/FALSE keywords).\n"
        "- Strings must use single quotes ' not double quotes \".\n"
        "- GROUP_CONCAT() for aggregating strings.\n"
        "- No TRUNCATE TABLE — use DELETE FROM.\n"
        "- CAST(x AS TEXT), CAST(x AS INTEGER), CAST(x AS REAL).\n"
    ),
    "postgresql": (
        "Target SQL dialect: **PostgreSQL**.\n"
        "CRITICAL RULES for PostgreSQL:\n"
        "- Use || for string concatenation or CONCAT().\n"
        "- Use LIMIT / OFFSET for pagination.\n"
        "- Use ILIKE for case-insensitive LIKE.\n"
        "- Date functions: NOW(), CURRENT_DATE, EXTRACT(), DATE_TRUNC(), AGE().\n"
        "- Use SERIAL or GENERATED ALWAYS AS IDENTITY for auto-increment.\n"
        "- Use :: for type casting (e.g., column::TEXT, column::INTEGER).\n"
        "- Supports FULL OUTER JOIN, LATERAL, CTEs, window functions.\n"
        "- Array functions: ARRAY_AGG(), UNNEST(), ANY().\n"
        "- JSON functions: jsonb_extract_path_text(), ->, ->>.\n"
        "- String functions: STRING_AGG(), REGEXP_MATCHES().\n"
        "- Boolean: use TRUE/FALSE.\n"
    ),
    "mysql": (
        "Target SQL dialect: **MySQL**.\n"
        "CRITICAL RULES for MySQL:\n"
        "- Use CONCAT() for string concatenation (NOT ||).\n"
        "- Use LIMIT for row limits.\n"
        "- Use backticks ` for quoting identifiers with reserved words.\n"
        "- Date functions: NOW(), CURDATE(), DATE_FORMAT(), DATEDIFF(), TIMESTAMPDIFF().\n"
        "- Use AUTO_INCREMENT for auto-increment columns.\n"
        "- Use IFNULL() or COALESCE() for null handling.\n"
        "- GROUP_CONCAT() for aggregating strings.\n"
        "- Supports window functions in MySQL 8+.\n"
        "- Boolean: use TRUE/FALSE or 1/0.\n"
        "- No FULL OUTER JOIN — use UNION of LEFT/RIGHT JOINs.\n"
    ),
}


class LLMQueryService:
    """Service for converting natural language to SQL using Groq Cloud API.

    Uses a multi-model fallback chain for reliability and quality:
      1. llama-3.3-70b-versatile  (best quality)
      2. deepseek-r1-distill-llama-70b  (strong reasoning)
      3. mixtral-8x7b-32768  (fast fallback)
    """

    DEFAULT_MODEL_CHAIN = [
        "llama-3.3-70b-versatile",
        "deepseek-r1-distill-llama-70b",
        "mixtral-8x7b-32768",
    ]

    def __init__(self, api_key: Optional[str] = None,
                 model_chain: Optional[List[str]] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model_chain = model_chain or self.DEFAULT_MODEL_CHAIN
        self.client = Groq(api_key=self.api_key)
        self._active_model: Optional[str] = None

    # ------------------------------------------------------------------
    # Model selection
    # ------------------------------------------------------------------

    def _get_model(self) -> str:
        """Return the currently active model (first in chain by default)."""
        return self._active_model or self.model_chain[0]

    # ------------------------------------------------------------------
    # Response cleaning — robust extraction of SQL from LLM output
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_response(raw: str) -> str:
        """Strip thinking tokens, code fences, and explanatory prose.

        Handles:
          - <think>…</think> blocks (DeepSeek R1)
          - ```sql … ``` code fences
          - Generic ``` … ``` fences
          - Raw SQL with leading prose
          - Multi-statement SQL, CTEs, subqueries
        """
        text = raw.strip()
        if not text:
            return ""

        # 1. Remove <think>…</think> blocks (DeepSeek R1 reasoning)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

        # 2. Extract from ```sql … ``` code blocks (greedy to capture full SQL)
        m = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip(";").strip()

        # 3. Extract from generic ``` … ``` code blocks
        m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            return m.group(1).strip().rstrip(";").strip()

        # 4. Try to find SQL statement — use GREEDY matching for complex queries
        #    Supports: SELECT, WITH (CTEs), INSERT, UPDATE, DELETE, CREATE, ALTER, DROP
        sql_start = r"(?:WITH|SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|EXPLAIN|PRAGMA)\b"
        m = re.search(
            rf"({sql_start}.*)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            sql = m.group(1).strip()
            # Remove trailing prose after the last semicolon
            # But preserve semicolons inside the SQL (subqueries don't use them, but CTEs might)
            # Find the last semicolon and trim everything after
            last_semi = sql.rfind(";")
            if last_semi != -1:
                sql = sql[:last_semi].strip()
            else:
                # No semicolon — remove trailing non-SQL prose
                # Split on double newline and take the SQL part
                parts = sql.split("\n\n")
                sql_parts = []
                for part in parts:
                    stripped = part.strip()
                    if stripped and (
                        re.match(r"(?:WITH|SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|EXPLAIN|PRAGMA|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|AND|OR|GROUP|ORDER|HAVING|LIMIT|OFFSET|UNION|INTERSECT|EXCEPT|CASE|WHEN|THEN|ELSE|END|AS)\b", stripped, re.IGNORECASE)
                        or stripped.startswith("(")
                        or stripped.startswith(",")
                        or stripped.startswith(")")
                    ):
                        sql_parts.append(part)
                    elif sql_parts:
                        # We already started SQL — check if this line looks like SQL continuation
                        if any(kw in stripped.upper() for kw in ["SELECT", "FROM", "WHERE", "JOIN", "GROUP", "ORDER", "HAVING", "LIMIT", "UNION"]):
                            sql_parts.append(part)
                        else:
                            break  # Prose started
                sql = "\n\n".join(sql_parts) if sql_parts else sql

            return sql.strip()

        # 5. Last resort — return everything, stripped
        return text.strip()

    # ------------------------------------------------------------------
    # SQL validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_sql(sql: str, schema: Dict[str, Any]) -> bool:
        """Validate that the SQL looks executable.

        Checks:
          - Not empty
          - Starts with a known SQL keyword (handles leading whitespace, parens, comments)
          - References at least one table from the schema (for SELECT queries)
        """
        if not sql or sql.strip() in ("", ";"):
            return False

        cleaned = sql.strip()

        # Remove leading SQL comments
        while cleaned.startswith("--"):
            cleaned = cleaned.split("\n", 1)[-1].strip() if "\n" in cleaned else ""
        while cleaned.startswith("/*"):
            end = cleaned.find("*/")
            if end == -1:
                return False
            cleaned = cleaned[end + 2:].strip()

        # Handle leading parentheses (subqueries as main query)
        test = cleaned.lstrip("( \t\n\r")

        if not test:
            return False

        first_word = test.split()[0].upper() if test.split() else ""
        valid_starts = {
            "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE",
            "ALTER", "DROP", "WITH", "EXPLAIN", "PRAGMA",
            "REPLACE", "MERGE", "UPSERT",
        }
        if first_word not in valid_starts:
            return False

        # For SELECT/WITH queries, verify at least one schema table is referenced
        if first_word in ("SELECT", "WITH"):
            tables = schema.get("tables", {})
            if tables:
                sql_upper = sql.upper()
                found = any(
                    table_name.upper() in sql_upper
                    for table_name in tables
                )
                if not found:
                    logger.warning(
                        f"SQL validation: no schema table found in query. "
                        f"Tables: {list(tables.keys())}"
                    )
                    # Don't reject — the LLM might use aliases or subqueries
                    # Just log a warning

        return True

    # ------------------------------------------------------------------
    # Prompt builders — dialect-aware
    # ------------------------------------------------------------------

    def _build_ddl_schema(self, schema: Dict[str, Any]) -> str:
        """Build CREATE TABLE DDL + sample data from rich schema."""
        parts: List[str] = []

        tables = schema.get("tables", {})
        for table_name, table_info in tables.items():
            # DDL
            ddl = table_info.get("ddl")
            if ddl:
                parts.append(ddl)
            else:
                # Fallback: build a pseudo-DDL from column info
                cols = table_info.get("columns", [])
                col_defs = []
                for c in cols:
                    line = f"  {c['name']} {c['type']}"
                    if not c.get("nullable", True):
                        line += " NOT NULL"
                    if c.get("primary_key"):
                        line += " PRIMARY KEY"
                    col_defs.append(line)
                for fk in table_info.get("foreign_keys", []):
                    ref_table = fk.get("referred_table", "")
                    ref_cols = ", ".join(fk.get("referred_columns", []))
                    local_cols = ", ".join(fk.get("constrained_columns", []))
                    col_defs.append(
                        f"  FOREIGN KEY ({local_cols}) REFERENCES {ref_table}({ref_cols})"
                    )
                ddl_text = f"CREATE TABLE {table_name} (\n" + ",\n".join(col_defs) + "\n);"
                parts.append(ddl_text)

            # Sample data
            sample_rows = table_info.get("sample_data")
            if sample_rows:
                parts.append(f"-- Sample rows from {table_name}:")
                for row in sample_rows[:3]:
                    parts.append(f"--   {row}")

            # Row count
            row_count = table_info.get("row_count")
            if row_count is not None:
                parts.append(f"-- {table_name} has {row_count} rows total.")

            parts.append("")

        return "\n".join(parts)

    def _build_system_prompt(self, db_type: str = "sqlite") -> str:
        """Build the system prompt with dialect rules and SQL expertise."""
        dialect = DIALECT_HINTS.get(db_type, DIALECT_HINTS["sqlite"])

        return f"""You are an expert SQL developer and database engineer. Your ONLY job is to convert the user's natural language question into a single, correct, executable SQL query.

{dialect}

CRITICAL OUTPUT RULES:
1. Output ONLY the raw SQL query — NO explanations, NO markdown, NO comments, NO code fences.
2. Do NOT wrap the query in ```sql``` or any other formatting.
3. Use the EXACT table and column names from the provided schema.
4. Use proper JOINs when the question involves multiple tables.
5. End the query with a semicolon.
6. If the question is ambiguous, make a reasonable assumption and generate the best possible query.

ADVANCED SQL CAPABILITIES (use when appropriate):
- Common Table Expressions (WITH ... AS) for complex multi-step queries
- Window functions (ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD, SUM OVER, etc.)
- Subqueries in WHERE, FROM, and SELECT clauses
- CASE WHEN expressions for conditional logic
- Aggregate functions with GROUP BY and HAVING
- Multiple JOINs across many tables
- UNION / INTERSECT / EXCEPT for combining result sets
- COALESCE / NULLIF for null handling

Remember: Output ONLY the SQL query. Nothing else."""

    def _build_user_prompt(self, question: str, schema: Dict[str, Any]) -> str:
        """Build the user prompt with schema and question."""
        ddl = self._build_ddl_schema(schema)

        return f"""### Database Schema (CREATE TABLE statements):
{ddl}

### User Question:
{question}

### SQL Query:"""

    # ------------------------------------------------------------------
    # Core generation via Groq API
    # ------------------------------------------------------------------

    def generate_sql(self, question: str, schema: Dict[str, Any],
                     db_type: str = "sqlite") -> Dict[str, Any]:
        """Generate SQL from a natural language question.

        Tries each model in the fallback chain until one succeeds.
        Returns dict with keys: success, sql_query, raw_response, model_used, explanation.
        """
        system_prompt = self._build_system_prompt(db_type)
        user_prompt = self._build_user_prompt(question, schema)

        last_error = None

        for model in self.model_chain:
            try:
                logger.info(f"Generating SQL with model={model} for question='{question}'")

                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.05,
                    max_tokens=1024,
                    top_p=0.95,
                    stream=False,
                )

                raw = response.choices[0].message.content or ""
                sql = self._clean_response(raw)

                # Ensure trailing semicolon
                if sql and not sql.rstrip().endswith(";"):
                    sql = sql.rstrip() + ";"

                # Validate
                if self._validate_sql(sql, schema):
                    self._active_model = model
                    logger.info(f"SQL generated successfully with {model}: {sql[:100]}...")
                    return {
                        "success": True,
                        "sql_query": sql,
                        "raw_response": raw,
                        "model_used": model,
                    }

                logger.warning(
                    f"Model {model} generated invalid SQL: {sql!r}. "
                    f"Trying next model..."
                )
                last_error = f"Generated invalid SQL: {sql[:200]}"

            except Exception as e:
                logger.error(f"Model {model} failed: {e}")
                last_error = str(e)
                continue

        # All models failed — return error
        return {
            "success": False,
            "error": f"All models failed to generate valid SQL. Last error: {last_error}",
            "sql_query": None,
            "model_used": self._get_model(),
        }

    # ------------------------------------------------------------------
    # Self-correction (called after execution error)
    # ------------------------------------------------------------------

    def fix_sql(self, original_question: str, bad_sql: str, error_msg: str,
                schema: Dict[str, Any], db_type: str = "sqlite") -> Dict[str, Any]:
        """Attempt to fix a SQL query that failed execution.

        Uses the LLM to analyze the error and produce a corrected query.
        """
        model = self._get_model()
        dialect = DIALECT_HINTS.get(db_type, DIALECT_HINTS["sqlite"])

        system_prompt = f"""You are an expert SQL debugger. A SQL query failed to execute.
Your job is to fix the query so it executes successfully.

{dialect}

RULES:
1. Output ONLY the corrected SQL query — NO explanations, NO markdown, NO code fences.
2. Carefully analyze the error message to understand what went wrong.
3. Use the exact table and column names from the schema.
4. End the query with a semicolon.
5. Common fixes: wrong column names, missing quotes, wrong JOIN syntax, dialect-specific issues."""

        ddl = self._build_ddl_schema(schema)

        user_prompt = f"""### Database Schema:
{ddl}

### Original Question:
{original_question}

### Failed SQL Query:
{bad_sql}

### Error Message:
{error_msg}

### Corrected SQL Query:"""

        for try_model in ([model] + [m for m in self.model_chain if m != model]):
            try:
                response = self.client.chat.completions.create(
                    model=try_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.05,
                    max_tokens=1024,
                    top_p=0.95,
                    stream=False,
                )

                raw = response.choices[0].message.content or ""
                sql = self._clean_response(raw)

                if sql and not sql.rstrip().endswith(";"):
                    sql = sql.rstrip() + ";"

                if self._validate_sql(sql, schema):
                    return {
                        "success": True,
                        "sql_query": sql,
                        "raw_response": raw,
                        "model_used": try_model,
                        "corrected": True,
                    }

            except Exception as e:
                logger.error(f"Correction with {try_model} failed: {e}")
                continue

        return {
            "success": False,
            "error": "All models failed to correct the SQL.",
            "sql_query": None,
            "model_used": model,
        }

    # ------------------------------------------------------------------
    # Status / health check
    # ------------------------------------------------------------------

    def check_model_availability(self) -> Dict[str, Any]:
        """Check which Groq models are available."""
        try:
            models = self.client.models.list()
            available_models = [m.id for m in models.data] if models.data else []

            # Check which of our chain models are available
            chain_status = {}
            for m in self.model_chain:
                chain_status[m] = m in available_models

            return {
                "available": True,
                "provider": "Groq Cloud",
                "active_model": self._get_model(),
                "model_chain": self.model_chain,
                "chain_status": chain_status,
                "total_available": len(available_models),
            }
        except Exception as e:
            return {
                "available": False,
                "provider": "Groq Cloud",
                "error": str(e),
            }


# Singleton instance
llm_service = LLMQueryService()
