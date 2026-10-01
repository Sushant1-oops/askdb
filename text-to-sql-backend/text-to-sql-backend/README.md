# AskDB backend

FastAPI service: natural language → guarded, verified, read-only SQL.

```bash
pip install -r requirements.txt
cp .env.example .env      # set GROQ_API_KEY
python main.py            # http://localhost:8000/docs
```

## Layout

```
main.py                 app, CORS, error mapping
config.py               every setting (env-driven)
routers/                database.py · query.py · export.py   (thin HTTP layer)
services/
  pipeline.py           orchestrates the whole flow and returns the response contract
  guardrails.py         SQL tokenizer + policy, input guard, result redaction
  sql_generator.py      prompts, JSON parsing, repair prompts
  judge.py              LLM-as-judge + deterministic result signals
  insight.py            answer + chart-spec validation
  schema.py / schema_profiler.py / schema_linker.py   schema model, data-derived hints, table selection
  executor.py           the single guarded path to any database
  database_service.py   connections, read-only sessions, introspection (SQLAlchemy)
  sql_runtime.py        driver-agnostic execution, JSON-safe values, timeouts
  llm_client.py         Groq wrapper: model fallback chain, JSON mode
  export_service.py     CSV / Excel / PDF (formula-injection safe)
  history.py · suggestions.py · sample_data.py
tests/                  100+ tests (guardrails, pipeline, units)
```

## API

All paths are under the host root. Errors are `{ "detail": "…" }` (404 unknown connection/table,
400 bad request / query error, 503 AI unavailable).

### Connections — `/api/database`
| Method | Path | Notes |
| --- | --- | --- |
| POST | `/connect` | `{db_type, database, host?, port?, username?, password?, file_path?, ssl?}` |
| POST | `/connect-demo` | bundled e-commerce SQLite |
| POST | `/connect-upload` | multipart `file` (.db/.sqlite/.sqlite3) |
| GET | `/connections` · `/connections/{id}` | |
| DELETE | `/connections/{id}` | also clears history |
| GET | `/connections/{id}/overview` | health, latency, stats, usage, suggestions, AI status |
| GET | `/connections/{id}/schema?refresh=` | tables, columns, keys, row counts |
| GET | `/connections/{id}/tables` · `/tables/{t}/schema` · `/tables/{t}/data?limit&offset` | |

### Queries — `/api/query`
| Method | Path | Notes |
| --- | --- | --- |
| POST | `/chat` | `{connection_id, question, history?, judge?}` → pipeline + answer, chart, follow-ups |
| POST | `/natural-language` | same pipeline without the summary |
| POST | `/sql` | `{connection_id, sql_query}` — read-only, guarded |
| GET/DELETE | `/history?connection_id=` | |
| GET | `/model-status?deep=` | configuration; `deep` checks model availability |

Pipeline response (abridged):

```jsonc
{
  "status": "success | blocked | failed | clarification",
  "sql": "SELECT …", "message": "",
  "result": { "columns": [], "rows": [], "row_count": 5, "truncated": false, "execution_ms": 3, "redacted_columns": [] },
  "guardrails": { "passed": true, "violations": [], "warnings": [], "limit_applied": true, "read_only": true },
  "judge": { "enabled": true, "verdict": "pass", "score": 0.92, "issues": [], "summary": "…", "revisions": 0 },
  "attempts": [{ "n": 1, "stage": "generate", "sql": "…", "outcome": "ok" }],
  "assumptions": [], "answer": "…", "chart": { "type": "bar", "xKey": "…", "yKeys": ["…"] }, "follow_ups": []
}
```

### Export — `/api/export`
`POST /query {connection_id, sql_query, format, filename?}` and `POST /table {connection_id, table_name, format, limit?}`
with `format` ∈ `csv | excel | pdf`. Exports re-run the query through the same guardrails.

## Security model (defence in depth)

1. Input guard (injection, write intent) → 2. SQL guard (lexed, not regex'd; dialect-aware escaping) →
3. read-only DB session + statement timeout → 4. result row cap → 5. restricted-column masking.
Passwords are never stored or returned. **There is no user authentication**: put the API behind your own
auth/network controls before exposing it beyond localhost.

## Known limits

- Connections, chat history and query history live in memory (lost on restart).
- Introspection covers the default schema only (PostgreSQL `public`).
- Postgres/MySQL code paths are exercised by logic tests, not by integration tests against live servers.
