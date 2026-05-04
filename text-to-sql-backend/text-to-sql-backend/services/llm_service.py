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
      2. qwen/qwen3-32b  (strong reasoning)
      3. llama-3.1-8b-instant  (fast fallback)
    """

    DEFAULT_MODEL_CHAIN = [
        "llama-3.3-70b-versatile",
        "qwen/qwen3-32b",
        "llama-3.1-8b-instant",
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
4. IF THE REQUESTED DATA DOES NOT EXIST IN THE SCHEMA: Do not hallucinate tables or write CREATE statements. Instead, output exactly: SELECT 'Requested data not found in schema' AS error;
5. Output EXACTLY ONE single SQL statement. NEVER output multiple statements separated by semicolons.
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

Remember: Output ONLY the SQL query. Nothing else. No conversational text."""

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
4. Output EXACTLY ONE single SQL statement. NEVER output multiple statements separated by semicolons.
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
    # Chat insight — two-step analysis pipeline for the AI Analyst
    # ------------------------------------------------------------------

    def generate_chat_insight(
        self,
        message: str,
        schema: Dict[str, Any],
        db_type: str = "sqlite",
        query_result: Optional[Dict[str, Any]] = None,
        generated_sql: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Analyse query results and produce a business insight with optional chart config.

        This is the *second* LLM call in the chat pipeline (the first call
        uses the existing ``generate_sql`` method).  It receives the SQL
        result data and asks the LLM to:

        1. Write a clear, actionable business insight/answer.
        2. Auto-detect the best chart type (bar, line, pie, area, scatter)
           for the data — or honour a user-requested chart type.
        3. Return a strict JSON structure so the frontend can render it.
        """
        model = self._get_model()
        dialect = DIALECT_HINTS.get(db_type, DIALECT_HINTS["sqlite"])

        # Truncate result data to keep tokens manageable
        rows = query_result.get("rows", []) if query_result else []
        columns = query_result.get("columns", []) if query_result else []
        truncated_rows = rows[:50]  # max 50 rows for analysis

        # Build conversation history context
        history_text = ""
        if history:
            for h in history[-6:]:  # last 6 messages for context
                role = h.get("role", "user")
                content = h.get("content", "")
                history_text += f"{role.upper()}: {content}\n"

        system_prompt = f"""You are an expert data analyst and business intelligence advisor.
You have been given the results of a SQL query executed against a database.

Your job is to:
1. Provide a clear, insightful business answer to the user's question.
2. If the data is suitable for visualization, suggest the BEST chart type automatically.
3. Format the chart data so it can be directly rendered by a charting library.

{dialect}

STRICT OUTPUT FORMAT — You MUST return ONLY valid JSON, no markdown, no code fences, no explanation outside the JSON:
{{
  "answer": "Your detailed business insight here. Use markdown formatting for emphasis, bullet points, etc.",
  "chart": {{
    "type": "bar | line | pie | area | scatter | none",
    "title": "Chart title",
    "data": [
      {{"label": "Category A", "value": 100}},
      {{"label": "Category B", "value": 200}}
    ],
    "xKey": "label",
    "yKeys": ["value"],
    "yKeyLabels": {{"value": "Human Readable Label"}}
  }}
}}

CHART SELECTION RULES:
- **bar**: Best for comparing discrete categories (e.g., revenue by product, count by city).
- **line**: Best for time-series or trends (e.g., monthly sales, daily users).
- **pie**: Best for showing proportions/percentages of a whole (max 8 slices, combine rest into "Other").
- **area**: Best for cumulative or stacked time-series data.
- **scatter**: Best for showing correlation between two numeric variables.
- **none**: Use when data is not suitable for visualization (single values, text-heavy results, or no data).

IMPORTANT:
- If the user explicitly requests a specific chart type (e.g., "show as pie chart"), USE that type.
- The "data" array must contain objects with consistent keys.
- For multi-series charts, use multiple yKeys (e.g., ["revenue", "cost"]).
- Keep the answer conversational but data-driven. Include specific numbers from the results.
- If there are no rows or the query failed, still provide a helpful answer explaining what happened.
- NEVER wrap the JSON in code fences or add any text before/after the JSON."""

        # Build data context
        data_context = "No data available."
        if truncated_rows and columns:
            data_context = f"Columns: {columns}\nData ({len(rows)} total rows, showing first {len(truncated_rows)}):\n"
            for row in truncated_rows:
                data_context += f"  {json.dumps(row, default=str)}\n"

        user_prompt = f"""### Conversation History:
{history_text if history_text else "No prior conversation."}

### User's Current Message:
{message}

### SQL Query Used:
{generated_sql or "No SQL was generated."}

### Query Results:
{data_context}

### Your Analysis (JSON only):"""

        for try_model in ([model] + [m for m in self.model_chain if m != model]):
            try:
                logger.info(f"Generating chat insight with model={try_model}")

                response = self.client.chat.completions.create(
                    model=try_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=2048,
                    top_p=0.95,
                    stream=False,
                )

                raw = response.choices[0].message.content or ""
                parsed = self._parse_insight_json(raw)

                if parsed:
                    parsed["model_used"] = try_model
                    parsed["raw_response"] = raw
                    return parsed

                # JSON parsing failed — try to use the raw text as the answer
                logger.warning(
                    f"Model {try_model} returned unparseable insight JSON. "
                    f"Raw response (first 300 chars): {raw[:300]}"
                )

                # Fallback: treat the entire LLM response as a plain-text answer
                cleaned_text = self._extract_plain_answer(raw)
                if cleaned_text:
                    return {
                        "answer": cleaned_text,
                        "chart": None,
                        "model_used": try_model,
                        "raw_response": raw,
                    }

            except Exception as e:
                logger.error(f"Chat insight with {try_model} failed: {e}")
                continue

        # Final fallback
        return {
            "answer": f"The query returned {len(rows)} rows with columns: {', '.join(columns)}. "
                      "Please try rephrasing your question for a more detailed analysis.",
            "chart": None,
            "model_used": model,
            "raw_response": "",
        }

    @staticmethod
    def _parse_insight_json(raw: str) -> Optional[Dict[str, Any]]:
        """Parse the LLM's JSON insight response, handling common issues."""
        text = raw.strip()

        # Remove code fences if present
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```", "", text)

        # Remove <think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Try to find JSON object — direct parse
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "answer" in obj:
                chart = obj.get("chart")
                if isinstance(chart, dict) and chart.get("type") == "none":
                    obj["chart"] = None
                return obj
        except json.JSONDecodeError:
            pass

        # Try to extract the outermost JSON object using brace matching
        start = text.find("{")
        if start != -1:
            depth = 0
            end = start
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break

            if end > start:
                candidate = text[start:end]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict) and "answer" in obj:
                        chart = obj.get("chart")
                        if isinstance(chart, dict) and chart.get("type") == "none":
                            obj["chart"] = None
                        return obj
                except json.JSONDecodeError:
                    pass

        # Try with regex — greedy match
        match = re.search(r'\{[\s\S]*"answer"\s*:\s*"[\s\S]*\}', text)
        if match:
            try:
                obj = json.loads(match.group())
                if isinstance(obj, dict) and "answer" in obj:
                    chart = obj.get("chart")
                    if isinstance(chart, dict) and chart.get("type") == "none":
                        obj["chart"] = None
                    return obj
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _extract_plain_answer(raw: str) -> Optional[str]:
        """Extract usable text from a non-JSON LLM response as a fallback answer."""
        text = raw.strip()

        # Remove think blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Remove code fences
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```", "", text)

        # If it looks like a JSON attempt that failed, try to extract the answer field
        answer_match = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        if answer_match:
            return answer_match.group(1).replace('\\n', '\n').replace('\\"', '"')

        # Otherwise, just use the cleaned text as-is (it's probably a natural language response)
        text = text.strip()
        if len(text) > 20:  # Must be substantive
            return text

        return None

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
