# AskDB — design notes

## 1. Goal
Let non-experts query a SQL database in natural language **safely** and **verifiably**: every answer shows
the SQL that produced it, what guardrails it passed, and an independent review of its correctness.

## 2. Architecture

```
Browser (React)                              FastAPI
  routes ─ WorkspaceProvider ─ lib/api.ts ──► routers/*  (thin)
                                                  │
                                                  ▼
                                          services/pipeline.py
   input guard → schema link → generate → GuardedExecutor → repair loop → judge → pick best → summarise
                                              │                    │
                                      guardrails.py          database_service.py
                                      (lexer + policy)       (read-only sessions, SQLAlchemy)
```

Principles: routers hold no logic; the pipeline depends on narrow interfaces (`LLM`, `DatabaseBackend`) so
it is fully testable with a scripted LLM and a SQLite backend; one `GuardedExecutor` is the only path to a
database (AI pipeline, SQL editor and exports all share it).

## 3. Guardrails
| Layer | Mechanism |
| --- | --- |
| Input | length cap, prompt-injection patterns, explicit write intent ("delete all…") rejected before any LLM call |
| SQL policy | tokenizer (strings / comments / quoted identifiers / MySQL backslash escapes / Postgres `E''` and `$$`), single statement, SELECT/WITH only, no `INSERT/UPDATE/DELETE/…` anywhere (blocks data-modifying CTEs, `SELECT INTO`, `FOR UPDATE`), dangerous functions (`pg_sleep`, `load_extension`, `LOAD_FILE`…), system catalogs, unknown tables, restricted columns |
| Executed text | rebuilt from the tokens that were inspected (comments stripped), so validated == executed |
| Database | read-only session (`default_transaction_read_only` / `READ ONLY` / `PRAGMA query_only`), statement timeout |
| Result | row cap (`LIMIT max+1` injected so truncation is detectable), restricted columns masked |
| Prompt | restricted columns never shown to the LLM; DB-derived text is labelled as data |

Restricted columns are those matching `RESTRICTED_COLUMN_PATTERN` (passwords, tokens, secrets, SSN, card numbers…).

## 4. Query quality
- **Schema linking** for large databases (name/column/value matching + FK neighbours).
- **Data-derived hints**: low-cardinality values and date ranges are in the prompt, so `'Completed'` is not guessed as `'completed'`, and "last month" can be reconciled with stale data.
- **Structured output** with `unanswerable` / `ambiguous` states instead of hallucinated SQL.
- **Repair loop**: guard and DB errors are fed back (bounded by `MAX_REPAIR_ATTEMPTS`).
- **Follow-up context**: recent turns and their SQL are included ("now by month").

## 5. LLM-as-judge
An independent model (different family by default) receives question, schema slice, SQL, assumptions, the
**observed** result preview and deterministic signals (0 rows, duplicate rows from join fan-out, all-NULL
columns, truncation). It returns verdict + score + per-criterion scores + issues + a fix suggestion.
`revise`/`fail` or `score < JUDGE_MIN_SCORE` triggers one regeneration (`MAX_JUDGE_REVISIONS`); the
highest-scoring *executed* candidate is returned, never blindly the latest. If the judge is down, the answer is
still delivered and labelled "unreviewed". Caveat: an LLM judge reduces, not removes, wrong answers.

## 6. Accuracy of answers and charts
The summariser may only use numbers present in the rows. Charts are specified as *column names*; the backend
validates them against the real result (existing columns, numeric y-axes, pie ≤ 8 slices) or falls back to a
deterministic heuristic. The frontend plots the actual rows — no data is transcribed by the model.

## 7. Frontend
Real routes (`/`, `/ask`, `/sql`, `/schema`, `/tables`, `/connections`) under a shared shell. TanStack Query owns
server state; `WorkspaceProvider` owns the active connection, the Ask AI conversation (so it survives
navigation and in-flight requests) and hand-off drafts. All states are handled: loading skeletons, empty,
error with retry, offline backend banner, stale connection after a backend restart.

## 8. Privacy
With AI features on, schema text, optionally sample values (`LLM_INCLUDE_SAMPLES`) and a preview of result rows
(`RESULT_ROWS_TO_LLM`) are sent to the LLM provider. Set both to off/0 for sensitive data.

## 9. Not included (by design / future work)
User authentication and per-user connection ownership; persistence of connections and history; credential
encryption at rest; non-default Postgres schemas; integration tests against live Postgres/MySQL; streaming
responses; an evaluation harness (golden question/SQL pairs) to measure accuracy over time.
