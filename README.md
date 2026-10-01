# AskDB

Ask questions about your database in plain English. AskDB writes **read-only** SQL, checks it with
guardrails, runs it, has a second model **review** the answer, and shows you the result as text, a
chart and a table.

```
askdb-clarity/                     React + TanStack Start frontend
text-to-sql-backend/text-to-sql-backend/   FastAPI backend
```

## Quick start

**1. Backend** (Python 3.10+)

```bash
cd text-to-sql-backend/text-to-sql-backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # add your GROQ_API_KEY
python main.py                                         # http://localhost:8000  (docs at /docs)
```

**2. Frontend** (Node 20+)

```bash
cd askdb-clarity
cp .env.example .env                                   # VITE_API_URL=http://localhost:8000
npm install
npm run dev
```

Open the app and click **Try the demo database** — no credentials needed.

> Without `GROQ_API_KEY` everything except AI features works (SQL editor, schema, table browser, exports).

## What you get

| Page | What it does |
| --- | --- |
| **Overview** | Live connection health, table/row/column counts, usage, suggested questions, recent activity |
| **Ask AI** | Conversational Q&A with follow-ups: answer, chart, table, SQL, and a visible verification trail |
| **SQL Editor** | Run SQL (⌘/Ctrl+Enter), click-to-insert schema explorer, "describe it" AI bar, recent queries, export |
| **Schema** | Tables, columns, keys, relationships; jump to browse or ask |
| **Tables** | Paginated data browser with export |
| **Connections** | Demo DB, SQLite upload, PostgreSQL, MySQL; switch or disconnect |

## How an AI answer is produced

1. **Input guard** – rejects prompt-injection and write intent ("delete all users") before any LLM call.
2. **Schema linking** – only relevant tables go into the prompt (all of them for small databases), with
   foreign keys, distinct-value hints and date ranges so the model uses real literals.
3. **Generation** – structured JSON (`ok` / `unanswerable` / `ambiguous`, assumptions, confidence).
4. **SQL guard** – a tokenizer-based validator: one statement, SELECT/WITH only, no data-modifying CTEs,
   no dangerous functions or system catalogs, only known tables, no restricted columns, LIMIT enforced.
5. **Read-only execution** – read-only DB session, statement timeout, row cap, sensitive columns masked.
6. **Self-repair** – guardrail or database errors are fed back to the model (bounded retries).
7. **LLM-as-judge** – an independent model scores schema fidelity, question match, result plausibility
   and safety; a failing score triggers one revision round, and the best candidate wins.
8. **Summary** – plain-language answer plus a chart spec the backend validates against the real rows
   (the model never copies numbers into charts).

See `Project_Documentation.md` for the architecture, API reference and design decisions.

## Tests

```bash
cd text-to-sql-backend/text-to-sql-backend
python -m unittest discover -s tests -t .      # or: pytest
```
