# Table RAG: Implementation Plan (Phases 0–4)

> **How to use this file:** save it in the repo as `docs/IMPLEMENTATION_PLAN.md`, then ask Claude Code one phase at a time, e.g.
> *"Read @docs/IMPLEMENTATION_PLAN.md and @README.md. Implement Phase 1, step by step. Commit after each numbered step. Stop at the end of the phase and show me what changed."*
> One phase per session keeps the diffs reviewable.

---

## Context for Claude Code (read before every phase)

This repo is a Text2SQL Table-RAG app (FastAPI backend in `backend/`, React + Vite frontend in `frontend/`). It follows `docs/reference_architecture.png` box by box; the README maps every box to a file. The offline flow lives in `backend/offline/build_index.py` and the online flow in `backend/online/pipeline.py`.

Today the app only accepts **uploaded files**: `main.py /upload` → `core/loader.py` reads CSV/TXT/TSV into pandas → `core/data_store.py` loads them into in-memory SQLite → `TableRAGSession(tables: dict[str, DataFrame], …)`.

**Goal of this plan:** support two input flows (manual upload and connecting a real database) through one shared pipeline, use LangChain more deeply (as promised in the Stage 1 submission), close the gaps against the submission, and add tests.

### Ground rules
- Do not break the existing upload flow. After every phase, the README demo (upload the 4 sample CSVs + `query_logs.sql`, ask the "revenue decreased last quarter" question) must still work and answer **Electronics**.
- Keep the "one file per diagram box" structure and the numbered-step comments in `build_index.py` and `pipeline.py`. Update the README tables when a file moves or is added.
- Keep the API response shapes (`UploadResponse`, `AskResponse`) backward compatible. New fields are allowed; removing or renaming fields is not.
- Never log, store in responses, or show in the UI a database password. Use `engine.url.render_as_string(hide_password=True)` wherever a URL is displayed.
- Add new dependencies to `backend/requirements.txt`. Add new env vars to `backend/.env.example` and the README configuration table.
- Before every commit, run `cd backend && pytest -q` (once tests exist, from Phase 1 on) and `cd frontend && npm run build`.
- Small commits, one per numbered step, with clear messages.

---

## Phase 0: Setup and cleanup (≈30 min)

1. **Branch:** `git checkout -b feature/data-sources` from the latest `main`.
2. **Remove the duplicate `main.py` at the repo root.** It is identical to `backend/main.py`. Delete the root copy and remove the "copy of backend/main.py" line from the README folder tree.
3. **Add dev dependencies:** create `backend/requirements-dev.txt` containing `-r requirements.txt`, `pytest`, `httpx` (needed for FastAPI's `TestClient`).
4. **Add `backend/tests/` with `conftest.py`.** It provides fixtures that need no network or API key:
   - `fake_llm`: `langchain_core.language_models.fake_chat_models.GenericFakeChatModel` or `FakeListChatModel`, with scripted replies
   - `fake_embeddings`: `langchain_core.embeddings.DeterministicFakeEmbedding(size=64)`
   - `sample_tables`: loads `sample_data/*.csv` with `read_table` + `clean_table`
5. **Add `backend/pytest.ini`** with `pythonpath = .` so that `from core.loader import …` works inside the tests.
6. **Smoke test** `tests/test_smoke.py`: build a `TableRAGSession` from the sample tables with the fake LLM and fake embeddings, and assert that `tables_info()` returns 4 tables. This is the safety net for the Phase 1 refactor.

**Done when:** `pytest -q` passes, the app starts, and the README demo works.

---

## Phase 1: Separate the upload flow from the database connection flow

### Target design
```
Upload files (CSV/TXT/TSV/Excel) ──► UploadSource ─┐
                                                   ├──► DataSource ──► offline index ──► online pipeline
Connection string (SQLite/Postgres) ──► DBSource ──┘   (one interface, all downstream code shared)
```
Both sources are backed by a **SQLAlchemy engine** wrapped in LangChain's `SQLDatabase`, so executing SQL, reading the schema and previewing rows work the same way for both.

### Step 1.1: Dependencies
Add to `requirements.txt`: `sqlalchemy>=2.0`, `psycopg2-binary` (Postgres driver), `sqlglot` (dialect-aware SQL parsing, used in step 1.6).

### Step 1.2: `backend/sources/base.py`, the `DataSource` interface
Create the package `backend/sources/` (with `__init__.py`). Define an abstract base class:

```python
class DataSource(ABC):
    kind: str                      # "upload" | "database"
    engine: sqlalchemy.Engine
    db: langchain_community.utilities.SQLDatabase

    @property
    def dialect(self) -> str: ...          # "sqlite" | "postgresql" | ...  (engine.dialect.name)
    def display_name(self) -> str: ...     # e.g. "4 uploaded files" or "postgresql://user@host/db" (NO password)
    def list_tables(self) -> list[str]: ...
    def columns(self, table) -> list[str]: ...
    def row_count(self, table) -> int: ...                 # SELECT COUNT(*)
    def profile_frame(self, table) -> pd.DataFrame: ...    # rows used for profiling (see 1.5)
    def is_sampled(self, table) -> bool: ...               # True if profile_frame is a sample
    def join_keys(self) -> list[tuple[str, str, str, str]]: ...  # (table_a, col_a, table_b, col_b)
    def quote(self, identifier) -> str: ...                # engine.dialect.identifier_preparer.quote
    def query(self, sql, max_rows=1000) -> pd.DataFrame: ...
    def preview(self, table, limit=20) -> pd.DataFrame: ...
    def close(self) -> None: ...                           # engine.dispose()
```

Implement `query`, `preview`, `quote`, `row_count`, `dialect` and `close` once in the base class:
- `query` uses `with engine.connect() as c: res = c.execute(text(sql)); rows = res.fetchmany(max_rows)`, then builds a DataFrame from `res.keys()`. Cap the rows with `fetchmany`, not by rewriting the SQL.
- Keep a `threading.Lock` around queries, as `core/data_store.py` does today. The in-memory SQLite connection cannot be used concurrently.
- `preview` builds `SELECT * FROM {quote(table)} LIMIT {int(limit)}`.

**Join keys change shape:** they become 4-tuples `(table_a, col_a, table_b, col_b)`, because real foreign keys can have different column names on each side (`orders.customer_id = customers.id`). Update `TableMetadataStore.joins_among()` to format `a.col_a = b.col_b`.

### Step 1.3: `backend/sources/upload_source.py`, `UploadSource`
Move the file-loading logic out of `main.py` and `core/data_store.py`:
- The constructor takes `files: list[tuple[filename, bytes]]`.
- For each file: `read_table` + `clean_table` (existing code in `core/loader.py`). Name the table with `clean_name(filename)` and de-duplicate names, as `main.py` does today.
- Create the engine with `create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})`.
- Write each DataFrame with `df.to_sql(name, engine, index=False)`. Convert datetime columns to `YYYY-MM-DD` strings first, exactly as `DataStore` does now.
- Keep the cleaned DataFrames in `self.frames`. `profile_frame(t)` returns the full frame and `is_sampled()` returns False.
- `join_keys()`: identical column names across tables, as `TableMetadataStore` computes them today. Move that logic here.
- `display_name()` returns `"N uploaded file(s)"`.
- Keep the validation errors from `main.py` (wrong extension, empty file, too large). Raise `ValueError` with the same messages so the endpoint can turn them into HTTP 400.

Then delete `core/data_store.py`.

### Step 1.4: `backend/sources/db_source.py`, `DBSource`
- The constructor takes `url: str`, `schema: str | None = None` and `include_tables: list[str] | None = None`.
- **Read-only engine per dialect:**
  - PostgreSQL: `create_engine(url, connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=15000"}, pool_pre_ping=True)`
  - SQLite file: open read-only with `sqlite:///file:{path}?mode=ro&uri=true`. Convert a plain `sqlite:///path` URL to that form. Reject `sqlite://` (in-memory) and paths that don't exist.
  - Any other dialect: allow it, but show a warning in the UI that it is untested. Read-only then depends on the DB user.
- `self.db = SQLDatabase(engine, schema=schema, include_tables=include_tables, sample_rows_in_table_info=3)`.
- Refuse more than `MAX_DB_TABLES` tables (env var, default 50). The error tells the user to pass `include_tables`.
- **Do NOT clean table or column names.** SQL runs against the real names. Chinook's SQLite version uses PascalCase names like `InvoiceLine`, which is a good test case. Everything downstream must use names exactly as `list_tables()` and `columns()` return them.
- `join_keys()`: real foreign keys from `sqlalchemy.inspect(engine).get_foreign_keys(table, schema=schema)`. If a database declares no foreign keys, fall back to the identical-column-name heuristic.
- `profile_frame(t)`: `SELECT * FROM t LIMIT PROFILE_SAMPLE_ROWS` (env var, default 5000). `is_sampled(t)` is `row_count(t) > PROFILE_SAMPLE_ROWS`.
- Run a light version of the `clean_table` type conversion on the sample (numbers stored as text, dates stored as text) **without renaming the columns**. Split `clean_table` into `clean_column_names()` and `convert_types()` so the DB source can call only `convert_types()`.
- Connection errors: catch `sqlalchemy.exc.SQLAlchemyError` and re-raise `ValueError` with a message stripped of the password, e.g. `str(e).replace(password, "***")`. Better still, don't echo the URL at all.
- `display_name()`: `engine.url.render_as_string(hide_password=True)`.

### Step 1.5: Make the offline pipeline read from `DataSource`
- `TableMetadataStore(source, types, notes, dataset_description="")` replaces `TableMetadataStore(tables, types, notes)`. Build the metadata from `source.profile_frame(t)` and use `source.row_count(t)` for the row count.
- When `source.is_sampled(t)`, add `"(stats from a sample of 5,000 rows)"` to the table header, so the LLM doesn't treat min/max/top values as exact.
- `describe_column` currently hard-codes `date (TEXT 'YYYY-MM-DD')`. Pass the dialect in:
  - For SQLite it stays TEXT.
  - For Postgres, report the real column type (e.g. `DATE` or `TIMESTAMP`), which you can get from `inspect(engine).get_columns()`.
- `build_offline_index(source, llm, embedding_model, notes, raw_queries)`. `classify_columns` runs on `source.profile_frame(t)`.
- `build_query_log(queries, source.list_tables())`
- `TableRAGSession(source, llm, embedding_model, notes, raw_queries)`:
  - store `self.source`
  - `tables_info()` and `preview()` read from the source
  - `close()` calls `source.close()`
  - `profile_text()` is unchanged
- `SessionStore.delete()` and TTL cleanup must call `session.close()`, so DB connections are released.
- **Summaries in parallel:** a real database may have dozens of tables. Build all the table-summary prompt inputs first, then call `summarizer.table_chain.batch(inputs, config={"max_concurrency": 5}, return_exceptions=True)` instead of looping. Use the existing fallback text for any input that raised an exception.

### Step 1.6: Dialect-aware SQL generation and safety checks
- **Prompts:** in `prompts/text2sql_prompt.py`, split `SQL_RULES` into a common part and a `DIALECT_RULES` dict:
  - `sqlite`: the current `strftime` rules
  - `postgresql`: `date_trunc('quarter', col)`, `EXTRACT(YEAR FROM col)`, `to_char(col, 'YYYY-MM')`, `ILIKE`
  - Add a `{dialect}` / `{dialect_rules}` variable and pass it from `Text2SQL.generate()` and the fix-SQL call.
  - Also add: *"Quote identifiers exactly as listed (case-sensitive)"*. Postgres needs `"InvoiceLine"` for mixed-case names.
- **Replace the regex safety checks with `sqlglot`** (new module `extensions/sql_guard.py`):
  - `parse_single_select(sql, dialect)`: `sqlglot.parse(sql, read=dialect)` must return exactly one statement, and its root must be a `Select`, `Union`, `Intersect` or `Except`. A CTE is fine as long as the root is one of these.
  - Walk the tree and reject any `Insert`, `Update`, `Delete`, `Drop`, `Create`, `Alter`, `Command` or `Merge` node anywhere inside it.
  - `tables_in_query(sql, known_tables, dialect)`: collect `exp.Table` nodes, drop CTE names, and match case-insensitively against `known_tables`, returning the real names. This fixes the comma-join (`FROM a, b`) miss and the schema-qualified-name case (`public.orders`).
  - This removes both known bugs: SQLite's `replace()` function no longer blocked, and `;` inside a string literal no longer rejected.
  - If parsing fails, return a readable error so the fix-SQL retry receives it.
- `SQLExecutor` uses `source.query(sql)` and the new guard. Keep the `NO_ANSWER` path and the "must read from an uploaded table" grounding check. Change the message wording to "from a table in this dataset".
- `offline/sql_query_logs.py` uses the new `tables_in_query` too. Keep the old regex-based function only if sqlglot can't parse a log entry.

### Step 1.7: API
- `/upload`: build `UploadSource(files)` → `TableRAGSession`. Behaviour is unchanged for the client.
- **New `POST /connect`** (multipart form, so query-log files can be attached, the same as upload):
  - `connection_url: str` (required)
  - `db_schema: str = ""`
  - `include_tables: str = ""` (comma-separated)
  - `query_logs: list[UploadFile] | None`
  - `descriptions: str = ""`
  - It builds a `DBSource`. A `ValueError` becomes HTTP 400 with the sanitised message.
- `UploadResponse` gets a new field `source: {"kind": "upload" | "database", "dialect": str, "name": str}`, returned by `session_payload`.
- **Optional:** `POST /connect/test`. It connects, lists the tables and closes, without an LLM call, so the UI can show "✓ Connected, 11 tables found" before the slow index build.
- CORS, session TTL and the other endpoints stay unchanged.

### Step 1.8: Frontend
- `UploadPanel.jsx` gets two tabs at the top: **Upload files** | **Connect database**.
  - **Upload tab:** the current table dropzone.
  - **Connect tab:** new `ConnectPanel.jsx` containing:
    - connection URL input (`type="password"` with a show/hide toggle)
    - optional schema
    - optional table list
    - a "Test connection" button, if you built `/connect/test`
    - the helper text: *"Use a read-only database user. Examples: `sqlite:///path/to/chinook.db`, `postgresql://readonly:pwd@localhost:5432/chinook`"*
  - **Shared by both tabs** (below them): the SQL query logs dropzone, the column-descriptions textarea, and the "Build index" button.
- `api.js`: add `connectDatabase(url, schema, tables, logFiles, descriptions)` and `testConnection(url, schema)`.
- `App.jsx`: `handleUpload` becomes `handleBuild(mode, payload)`, which calls either `uploadFiles` or `connectDatabase`. The session shape is the same for both.
- `DatasetSummary.jsx`: show a badge with `source.kind` / `source.dialect` / `source.name`, e.g. "Database · postgresql · readonly@localhost/chinook".
- `AnswerDetails.jsx` needs no change.

### Step 1.9: Demo databases
- Add `sample_data/chinook.sqlite`, the SQLite build of the Chinook database from `github.com/lerocha/chinook-database` releases, about 1 MB. Check the licence (MIT) and mention the source in the README. It has 11 tables with real foreign keys and PascalCase names, which makes a good test of the DB flow.
- Add `docker-compose.yml` at the repo root:
  - a `postgres:16` service
  - the Chinook PostgreSQL script mounted into `/docker-entrypoint-initdb.d/`
  - a read-only role: `CREATE ROLE readonly LOGIN PASSWORD 'readonly'; GRANT CONNECT …; GRANT USAGE ON SCHEMA public …; GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;`
- Put the SQL for the read-only role in `docker/init/99_readonly.sql`.

### Step 1.10: Tests for Phase 1
- `test_upload_source.py`:
  - the 4 CSVs load
  - a pipe-separated `.txt` loads
  - duplicate filenames get `_2`
  - `query()` caps rows at `max_rows`
  - `preview()` works
- `test_db_source.py` (uses `sample_data/chinook.sqlite`):
  - `list_tables()` returns 11 tables with their original case
  - `join_keys()` contains `("InvoiceLine", "InvoiceId", "Invoice", "InvoiceId")` or equivalent
  - writing fails: `source.query("DELETE FROM Genre")` raises, because the connection is read-only
  - the password never appears in `display_name()` or in error messages
- `test_sql_guard.py`:
  - allows `SELECT replace(name,'a','b') FROM t`
  - allows `SELECT ';' AS x FROM t`
  - allows a CTE
  - rejects `DROP TABLE t` and `SELECT 1; DELETE FROM t`
  - rejects `WITH x AS (…) DELETE …`
  - `tables_in_query` finds both tables in `FROM a, b`
  - `tables_in_query` excludes CTE names
  - `tables_in_query` matches case-insensitively and returns the real names
- `test_api.py` (FastAPI `TestClient`; monkeypatch `models` with the fakes):
  - `/upload` with the sample CSVs returns 200
  - `/connect` with the Chinook path returns 200 and `source.kind == "database"`
  - `/connect` with a bad URL returns 400 with no password in `detail`

**Phase 1 is done when:**
- the README upload demo still works
- connecting `sqlite:///…/sample_data/chinook.sqlite` answers *"Which 5 artists have the most tracks?"*
- the docker Postgres database answers *"Total sales by country in 2012"*
- all tests pass
- the README documents both flows (update the folder tree, the API table, and add a new "Connect a database" section)

---

## Phase 2: Deeper LangChain integration

Branch: `feature/langchain`.

### Step 2.1: Structured output for table selection and SQL generation
- Add Pydantic models in `prompts/schemas.py`:
  ```python
  class TableChoice(BaseModel):
      tables: list[str] = Field(description="Tables needed, including join tables")
      reason: str = Field(description="One sentence: why these tables")

  class SQLAnswer(BaseModel):
      can_answer: bool
      sql: str = Field(description="One read-only SELECT, empty if can_answer is false")
      explanation: str = Field(description="One sentence on what the query does")
  ```
- `TableSelector`: use `TABLE_SELECTION_PROMPT | llm.with_structured_output(TableChoice)`, with `.with_fallbacks([old_text_chain])`. Some models or providers don't support tool calling. The old regex parsing stays only inside the fallback path.
- `Text2SQL`: do the same with `SQLAnswer`. `can_answer=False` maps to the existing `NO_ANSWER` path. Update the prompt text: remove "output only SQL in ```sql fences" from the structured version, and keep it in the fallback prompt.
- Return `reason` and `explanation` in `AskResponse` as new optional fields `selection_reason` and `sql_explanation`. Show them in `AnswerDetails.jsx` under steps 2 and 3.

### Step 2.2: Online pipeline as a LangGraph graph
Add `langgraph` to the requirements. Rewrite `online/pipeline.py` as a `StateGraph`, keeping the numbered-step comments and the node names matching the diagram:
```
State (TypedDict): question, top_n, similar, top_k, selection_reason, schema, examples,
                   sql, sql_explanation, result, error, attempts, answer
Nodes:
  retrieve          (steps 1+2)  question → Top N tables + similar past queries
  select_tables     (step 3)     → Top K
  generate_sql      (step 4)     → sql  (or NO_ANSWER)
  check_and_execute (step 5)     guard + source.query → result | error
  fix_sql           (step 5b)    FIX_SQL prompt with the error → new sql, attempts += 1
  answer            (step 6)     grounded answer / no-answer message / error message
Edges:
  retrieve → select_tables → generate_sql → check_and_execute
  check_and_execute ─(ok | NO_ANSWER)────────────────→ answer
  check_and_execute ─(error and attempts < MAX)──────→ fix_sql → check_and_execute
  check_and_execute ─(error and attempts == MAX)─────→ answer
```
- `OnlinePipeline.run(question)` returns the **same dict** as today, so the API is unchanged.
- Add a hook for Phase 5: `run(question, tables_override: list[str] | None = None)`. When set, skip retrieve and select_tables and use these tables as Top K. This becomes the "oracle" evaluation mode later.
- Export a diagram of the graph for the report: `graph.get_graph().draw_mermaid()` → `docs/online_graph.md`.
- The retry loop in `extensions/sql_executor.py` is replaced by the graph edges. Keep `SQLExecutor.run()` as the body of the `check_and_execute` node.

### Step 2.3: Richer table summaries (example questions)
- Change `TABLE_SUMMARY_PROMPT` to use structured output:
  ```python
  class TableSummary(BaseModel):
      summary: str               # 3-5 sentences
      example_questions: list[str]  # 5 business questions this table helps answer
  ```
- Embed `summary` plus the questions (one per line) in `table_document()`. Keep the UI showing only `summary`, and optionally add the questions in a collapsible list in `DatasetSummary.jsx`.
- Fallback when the model can't return structured output: the current plain-text summary with no questions.

### Step 2.4: Retriever abstraction and optional hybrid search
- `offline/vector_store.py`: expose `as_retriever(k)`.
- New setting `RETRIEVER=vector|hybrid` (env var, default `vector`). `hybrid` means `EnsembleRetriever([faiss_retriever, BM25Retriever.from_documents(docs)], weights=[0.5, 0.5])`, and needs the `rank_bm25` package.
- The ensemble returns documents without distances. For `hybrid`, rank tables by reciprocal-rank score (higher is better). Return a `score_kind: "distance" | "rank"` field so `AnswerDetails.jsx` can label the score correctly ("lower is more similar" vs "higher is better").
- Keep `N_CANDIDATES` and `K_SELECTED` configurable via env vars `TOP_N` and `TOP_K`. Phase 5 needs them for the ablations.

### Step 2.5: Tracing and caching
- In `.env.example`, add commented-out LangSmith variables: `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY=`, `LANGSMITH_PROJECT=table-rag`. With these set, LangChain and LangGraph trace automatically; no code change is needed. Document this in the README.
- Optional: `LLM_CACHE=sqlite` → `set_llm_cache(SQLiteCache(".llm_cache.db"))` in `core/llm.py`. This makes repeated demo and eval runs cheap. Add `.llm_cache.db` to `.gitignore`.

### Step 2.6: Tests for Phase 2
- Graph routing with a scripted fake LLM:
  - first SQL fails, then the fix succeeds: `attempts == 1`, answer present
  - NO_ANSWER goes straight to the answer node
  - `MAX_RETRIES` failures end with an error answer
- Structured-output fallback: a fake model without tool support still returns tables via the text path.
- `tables_override` skips retrieval.

**Phase 2 is done when:** the demos from Phase 1 still work; the graph diagram is exported; the UI shows the selection reason and SQL explanation; and all tests pass.

---

## Phase 3: Close the gaps against the Stage 1 submission

Branch: `feature/plan-gaps`.

### Step 3.1: Excel upload
- Add `openpyxl` to requirements.
- `ALLOWED_EXTENSIONS` gains `.xlsx` and `.xls`. `.xls` also needs `xlrd`, so either add it or support `.xlsx` only and say so in the README.
- In `UploadSource`: `pd.read_excel(io.BytesIO(raw), sheet_name=None)` gives one table per non-empty sheet:
  - table name `clean_name(f"{file}_{sheet}")`
  - just `clean_name(file)` if there is only one sheet
  - each sheet goes through `clean_table`
- Frontend: the `accept` and `pattern` attributes in `UploadPanel.jsx` include `.xlsx`, and the hint text mentions Excel.
- Add `sample_data/school.xlsx` with two sheets, e.g. students and scores, to demo this.

### Step 3.2: Dataset-level description (business context)
- New optional form field `dataset_description` on both `/upload` and `/connect`, with a textarea in the shared part of the upload panel: *"What is this dataset about? (optional)"*.
- Store it in `TableMetadataStore.dataset_description`. It goes into:
  - `TABLE_SUMMARY_PROMPT` (as `Dataset context: …`)
  - `OVERVIEW_PROMPT`
  - the Text2SQL system prompt: a `Dataset context:` block before the tables, only when it isn't empty
- Keep the existing per-column notes as they are.

### Step 3.3: Follow-up questions (conversation memory)
- `TableRAGSession` keeps the last 3 turns: `(question, sql, short answer)`.
- A new `CONDENSE_PROMPT` (in `prompts/answer_prompt.py` or a new `prompts/condense_prompt.py`) rewrites a follow-up like *"and for last year?"* into a standalone question, using those turns. It returns the question unchanged when it is already standalone.
- Run it as the first graph node, `condense`, before `retrieve`, and only when there is history.
- `AskResponse` gets `standalone_question`. Show it in `AnswerDetails.jsx` when it differs from what the user typed.
- `/session/{id}` DELETE, or "New dataset", clears the history.

### Step 3.4: Relationships in the metadata
- Now that `DBSource` provides real foreign keys, show them in `DatasetSummary.jsx` as a "Relationships" list (`orders.product_id → products.product_id`).
- Include them in `profile_text()`, so the overview can mention how the tables connect.

**Phase 3 is done when:**
- an Excel file with two sheets uploads as two tables and can be queried with a join
- a dataset description visibly changes the summaries
- a follow-up question ("and in 2011?") works after a first question
- the README documents all three features

---

## Phase 4: Fixes, hardening, and tests

Branch: `feature/hardening`.

### Step 4.1: Bug fixes
Most of these are already solved by Phase 1; verify each one and add a regression test.
- [ ] SQLite `replace()` function no longer blocked (sqlglot guard)
- [ ] `;` inside a string literal no longer rejected
- [ ] `tables_in_query` handles comma joins, CTEs, schema-qualified and quoted names
- [ ] Root `main.py` removed (Phase 0)
- [ ] `/preview` quotes table names per dialect (Phase 1 `quote()`)
- [ ] `similarity_search`: the `k=10` hit count is hard-coded, so with more than 10 documents some tables are never scored. Use `k = max(10, TOP_N * 3)`.
- [ ] `Summarizer.summarise_queries` parses numbered lines. Move it to structured output (`list[QueryDescription]`), keeping the regex as a fallback.
- [ ] `sessions.py` docstring says "session_id -> Engine". Update it to `TableRAGSession`, and make TTL cleanup call `close()` (Phase 1).

### Step 4.2: Robustness
- Upload limits:
  - keep `MAX_UPLOAD_MB`
  - add `MAX_TABLES_PER_UPLOAD` (default 20)
  - add `MAX_ROWS_PER_TABLE` (default 1,000,000), rejecting larger files with a clear message
- Query limits:
  - `MAX_RESULT_ROWS` (default 1000) passed to `source.query`
  - `statement_timeout` for Postgres (Phase 1)
  - for SQLite, `sqlite3` progress handler or `conn.set_progress_handler` to abort queries running longer than about 15 s
- LLM errors:
  - wrap provider errors such as rate limits and auth failures in a clear message: *"The LLM provider returned an error: …"*
  - don't return raw stack traces from `/ask`
- Logging:
  - use `logging` instead of silent `except Exception: pass` blocks (e.g. in `summarizer.py`, `rag_session.py`)
  - log the step name and error at WARNING level
  - never log connection URLs or API keys
- Frontend:
  - disable "Build index" while a request is running (already done)
  - show a progress message like "Summarising 11 tables…"
  - show a useful message on 400 and 500 responses (already mostly done)

### Step 4.3: Test coverage
Target: every module in `core/`, `sources/`, `offline/`, `extensions/` and `online/` has at least one test, all running offline with fakes.
- `test_loader.py`:
  - separator detection (comma, tab, `|`, `;`, quoted commas)
  - `clean_name` edge cases (leading digit, symbols, empty)
  - numbers stored as text
  - dates stored as text
  - `classify_column` for each of the 5 types
- `test_metadata_store.py`:
  - column descriptions for each type
  - notes attached by `column` and by `table.column`
  - the join-key formatting
  - the sampled-table note
- `test_query_logs.py`:
  - comments are stripped
  - non-SELECT statements are dropped
  - only queries using known tables are kept
  - `MAX_LOG_QUERIES` is enforced
- `test_similarity_search.py` (deterministic fake embeddings):
  - a table hit and a SQL-log hit both count toward the table
  - the best distance is kept per table
  - similar queries are capped at `MAX_EXAMPLES`
- `test_pipeline.py` (end to end, fake LLM):
  - the upload flow returns a result table and SQL
  - the NO_ANSWER flow
  - a question with a literal-answer query (`SELECT 'Paris'`) is rejected by the grounding check
- `test_api.py`: all endpoints, including 404 for an expired or unknown session
- **Frontend:** at least `npm run build` in CI. Component tests (Vitest + React Testing Library) are optional, e.g. the ConnectPanel tab switch and the password field never being rendered back.

### Step 4.4: Continuous integration
Add `.github/workflows/ci.yml`:
- `backend` job: Python 3.11, `pip install -r backend/requirements-dev.txt`, `cd backend && pytest -q`
- `frontend` job: Node 20, `npm ci`, `npm run build`
- The tests must not need an API key or network access, other than downloading packages. Use the fakes, and do not load the HuggingFace model in tests (patch `load_embedding_model`).

### Step 4.5: README update
- Update the folder tree (`sources/`, `extensions/sql_guard.py`, `tests/`, `docker-compose.yml`)
- Update the Offline and Online step tables (the LangGraph node names)
- Add a "Connect a database" section: SQLite example, Postgres with docker-compose, read-only user, env vars
- Update the configuration table: `MAX_DB_TABLES`, `PROFILE_SAMPLE_ROWS`, `TOP_N`, `TOP_K`, `RETRIEVER`, `LLM_CACHE`, LangSmith, `MAX_RESULT_ROWS`
- Add a "Running tests" section
- Update Limitations: remove the items that are now fixed, and add new ones (e.g. "database stats are computed from a sample")

**Phase 4 is done when:** CI is green on a pull request; all checklist items in 4.1 are ticked; and the README matches the code.

---

## After Phase 4 (not in this plan)
Phase 5 is evaluation: golden set, `eval/run_eval.py`, the rag / all_tables / oracle modes (the `tables_override` hook from Phase 2 is ready for this), and ablations. Phase 6 is the demo and report.
