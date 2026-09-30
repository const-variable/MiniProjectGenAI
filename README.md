# Table RAG: Text2SQL with a vector index over table and SQL summaries

Upload tables or connect a read-only database (and optionally provide past SQL queries), ask questions in plain English, get SQL plus a grounded answer.
The code follows `docs/reference_architecture.png` **box by box**: every component in the diagram has its own file.

## Folder structure = architecture

```
backend/
├── main.py                        API: /upload runs OFFLINE, /ask runs ONLINE
├── rag_session.py                 one uploaded dataset: builds the index, answers questions
├── sessions.py                    keeps each user's session in memory
│
├── core/                          shared building blocks
│   ├── llm.py                     [LLM]              blue boxes
│   ├── embedding_model.py         [Embedding Model]  yellow boxes (same model offline + online)
│   └── loader.py                  reads, cleans and classifies uploaded table files
│
├── sources/                       shared SQLAlchemy-backed data sources
│   ├── base.py                    DataSource interface and query helpers
│   ├── upload_source.py           uploaded files in in-memory SQLite
│   └── db_source.py               read-only SQLite / PostgreSQL / other databases
│
├── prompts/                       green boxes
│   ├── schemas.py                 structured LLM outputs
│   ├── summarization_prompt.py    [Summarization Prompt]
│   ├── table_selection_prompt.py  [Table Selection Prompt]
│   ├── text2sql_prompt.py         [Text2SQL Prompt]
│   └── answer_prompt.py           extension: answer, overview, suggestions
│
├── offline/                       OFFLINE VECTOR INDEX CREATION
│   ├── build_index.py             ▶ the offline pipeline, steps 1-5
│   ├── table_metadata_store.py    [Table Metadata Store]   red cylinder
│   ├── sql_query_logs.py          [SQL Query Logs] (sqlglot parsing, regex fallback)
│   ├── summarizer.py              [Summarization Prompt → LLM → Table/SQL Summary]
│   └── vector_store.py            [Vector Store]: Embeddings Index + Similarity Search
│
├── online/                        ONLINE TEXT2SQL
│   ├── pipeline.py                ▶ the online pipeline, steps 1-6
│   ├── similarity_search.py       [Question Embeddings → Similarity Search → Top N Tables]
│   ├── table_selection.py         [Table Selection Prompt → LLM → Top K Tables]
│   └── text2sql.py                [Text2SQL Prompt → LLM → Generated SQL]
│
└── extensions/                    steps AFTER the diagram's "Generated SQL"
    ├── sql_executor.py            safety check, grounding check, execute, retry
    ├── answer_generator.py        result → plain-English answer
    └── sql_guard.py               dialect-aware read-only SQL validation

frontend/                          React + Vite UI (upload, dataset summary, chat, "How this was answered")
sample_data/                       sample CSVs + school.xlsx + Chinook SQLite + SQL logs
docs/reference_architecture.png    the architecture this code implements
docs/online_graph.md               generated LangGraph execution diagram
backend/tests/                     offline API, source, SQL guard, and graph tests
docker-compose.yml, docker/init/   optional PostgreSQL Chinook database with a read-only user
```

**To follow the flow, read two files:** `offline/build_index.py` (top half of the diagram) and `online/pipeline.py` (bottom half). Both source types implement `DataSource`, and each step calls the module for that box.

## Offline: runs once per source (`offline/build_index.py`)

| Step | Diagram box | File |
|---|---|---|
| 1 | Table Metadata Store | `offline/table_metadata_store.py` |
| 2 | SQL Query Logs | `offline/sql_query_logs.py` |
| 3 | Summarization Prompt → LLM → Table/SQL Summary | `offline/summarizer.py`, `prompts/summarization_prompt.py` |
| 4 | Embedding Model | `core/embedding_model.py` |
| 5 | Vector Store → Embeddings Index | `offline/vector_store.py` |

Table summaries include suggested business questions in their embedded text. Structured outputs use Pydantic models with `PydanticOutputParser`; when the model returns malformed output (`OutputParserException`), a plain-text fallback prompt is used instead. Provider errors such as rate limits or an invalid key are not masked: index building stops and the API returns a 502 with a clear message.

## Online: runs per question (`online/pipeline.py`)

| Step | Diagram box | File |
|---|---|---|
| Follow-up | `condense` rewrites questions using up to three prior turns | `online/pipeline.py`, `prompts/answer_prompt.py` |
| 1-2 | `retrieve`: question embedding → Similarity Search → Top N Tables | `online/similarity_search.py` |
| 3 | `select_tables`: Table Selection Prompt → LLM → Top K Tables | `online/table_selection.py` |
| 4 | `generate_sql`: Text2SQL Prompt → LLM → Generated SQL | `online/text2sql.py` |
| 5-5b | `check_and_execute` / `fix_sql`: guard, execute, repair and retry | `extensions/sql_executor.py` |
| 6 | `answer`: grounded answer | `extensions/answer_generator.py` |

The online path is a LangGraph `StateGraph`; `condense` runs only when conversation history exists. Its nodes and conditional retry edges are exported in [docs/online_graph.md](docs/online_graph.md). The answer details display the table-selection reason, SQL explanation, and score direction.

**Why the extensions:** the diagram returns SQL to the user. Our users are non-technical, so the SQL is run and explained. Two checks come first: the query must be one read-only SELECT, and it must **read from a table in the current dataset**. The second check stops the LLM answering from memory (e.g. `SELECT 'Oklahoma City' AS capital`); if the data can't answer, the system says so.

## Run it locally

Needs **Python 3.10+**, **Node.js 18+**, npm, and a [Groq API key](https://console.groq.com/keys). Run the backend and frontend in separate terminals from the repository root.

### 1. Configure the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`; in Command Prompt use `.venv\Scripts\activate.bat`. Edit `backend/.env` and replace `your_groq_key_here` with your Groq API key. The default `LLM_MODEL` is `llama-3.3-70b-versatile`; leave it as-is unless selecting another model supported by Groq. Do not commit `.env` or share its key.

For Windows, create the environment with `py -3 -m venv .venv` and copy the template with `Copy-Item .env.example .env` while in `backend/`.

Start the API in the same terminal, with the virtual environment active:

```bash
uvicorn main:app --reload --port 8000
```

Wait for `Application startup complete`. In a second terminal, verify the API:

```bash
curl http://localhost:8000/health
```

Expected response: `{"status":"ok"}`. Interactive API docs are available at http://localhost:8000/docs.

### 2. Install and start the frontend

Open a second terminal from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. The frontend uses `http://localhost:8000` by default. If the backend uses another port, set `VITE_API_URL` before starting Vite, for example `VITE_API_URL=http://localhost:8001 npm run dev`.

### 3. Build an index and ask a question

- File demo: upload `orders.csv`, `products.csv`, `students.csv`, and `scores.csv` from `sample_data/`; optionally attach `query_logs.sql` and add column or dataset descriptions.
- Excel demo: upload `school.xlsx`. The `Students` and `Scores` sheets become separate tables joined by `student_id`.
- Database demo: choose **Connect database**, paste a connection URL, and run **Test connection** before building the index. Since Uvicorn starts in `backend/`, use `sqlite:///../sample_data/chinook.sqlite` for the included SQLite file.
- PostgreSQL demo: install Docker Desktop, open a third terminal at the repository root, and run `docker compose up -d`. Wait until `docker compose logs postgres` reports that the database is ready to accept connections, then connect with `postgresql://readonly:readonly@localhost:5432/chinook`.

The revenue sample question should identify Electronics. Chinook can answer *"Which 5 artists have the most tracks?"* The first index build may download the local embedding model; later builds reuse the cached model.

### 4. Stop or restart

Press `Ctrl+C` in the frontend and backend terminals. Stop the optional database from the repository root with `docker compose down`. To restart, rerun the backend and frontend start commands; the virtual environment and installed packages remain in `backend/.venv`.

### Troubleshooting

- `GROQ_API_KEY is not set`: confirm `backend/.env` exists and contains the key assignment, then restart Uvicorn.
- The browser cannot reach the API: confirm Uvicorn is running and `VITE_API_URL` matches its address and port.
- A port is occupied: from `backend/`, start Uvicorn with `uvicorn main:app --reload --port 8001`, then start Vite with `VITE_API_URL=http://localhost:8001 npm run dev` from `frontend/`.
- Database indexing is slow: restrict the selected database tables; upload, profile, and result limits are listed in the configuration table below.
- `The LLM provider returned an error` (HTTP 502): check `GROQ_API_KEY`, that `LLM_MODEL` is available on Groq, and your rate limit or quota. Server logs record only the failing step and error type, never keys or connection URLs.

### Configuration (`backend/.env`)

| Variable | Purpose |
|---|---|
| `LLM_MODEL` | Defaults to `llama-3.3-70b-versatile`, an open-weight Llama model served by Groq. |
| `GROQ_API_KEY` | Required Groq API credential (see `.env.example`). |
| `EMBED_MODEL` | Open-source local embedding model, default `sentence-transformers/all-MiniLM-L6-v2`. |
| `FRONTEND_ORIGINS` | Allowed CORS origins, default `http://localhost:5173` |
| `MAX_UPLOAD_MB` | Max size per table file, default `20` |
| `MAX_TABLES_PER_UPLOAD` | Maximum tables created by an upload, including Excel sheets; default `20` |
| `MAX_ROWS_PER_TABLE` | Maximum uploaded rows per table; default `1,000,000` |
| `MAX_RESULT_ROWS` | Maximum rows returned by a generated query; default `1000` |
| `SQLITE_QUERY_TIMEOUT_SECONDS` | SQLite query deadline; default `15` seconds |
| `MAX_DB_TABLES` | Maximum discovered database tables, default `50`; narrow the connection with the table list when exceeded |
| `PROFILE_SAMPLE_ROWS` | Maximum rows sampled per database table for profiling, default `5000` |
| `TOP_N`, `TOP_K` | Candidate and selected table limits for retrieval/selection, defaults `5` and `3` |
| `RETRIEVER` | `vector` (default) or `hybrid` (FAISS + BM25 reciprocal-rank fusion) |
| `LLM_CACHE` | Set to `sqlite` to cache repeated model calls in `.llm_cache.db` |

The frontend reads `VITE_API_URL` (default `http://localhost:8000`).

`LLM_CACHE=sqlite` can reduce repeated model calls during demos and evaluation; the local cache file is ignored by git.

### Tunable values in code

Values that affect retrieval or generation quality are marked with a `# hyperparameter` comment where they are defined.

| Value | Default | Where |
|---|---|---|
| LLM `temperature` | `0` | `core/llm.py` |
| Concurrent table-summary calls | `5` | `offline/summarizer.py` |
| Similarity-search hits | `max(10, 3 × TOP_N)`, so every table can be scored | `online/similarity_search.py` |
| Similar past queries passed to the Text2SQL prompt | `3` | `online/similarity_search.py` |
| Hybrid retriever weights (FAISS, BM25) | `0.5, 0.5` | `offline/vector_store.py` |

## Demo with uploaded files

1. **Tables:** upload `orders.csv`, `products.csv`, `students.csv`, `scores.csv` together.
2. **Query logs:** upload `query_logs.sql`.
3. Ask *"Why did revenue decrease in the last quarter, and which product category contributed the most?"*
   Open **How this was answered**: Top N should list all four tables, Top K should keep only `orders` and `products`, and the answer should be Electronics.

For an Excel join demo, upload `sample_data/school.xlsx` and ask *"Which student has the highest math mark?"*. Its `Students` and `Scores` sheets load as separate tables joined by `student_id`.

## Connect a database

Choose **Connect database**, enter a read-only connection URL, and optionally provide a schema and comma-separated table list. SQLite database files are opened in read-only mode; PostgreSQL connections set transactions read-only and use a 15-second statement timeout. Other SQLAlchemy dialects are allowed, but read-only behavior depends on the database user and is not tested by this app.

Examples:

```text
sqlite:///path/to/chinook.sqlite
postgresql://readonly:password@localhost:5432/chinook
```

The connection URL is never included in an API error with its password. The dataset overview displays a password-hidden source name. Use **Test connection** to list tables without building the index. For large databases, include only the tables relevant to the questions. The same query-log upload and column-description fields are available for both source types.

For the included Chinook SQLite demo, connect to `sqlite:///../sample_data/chinook.sqlite` when the backend runs from `backend/`. It is the MIT-licensed [Chinook sample database](https://github.com/lerocha/chinook-database). To run its PostgreSQL variant, use `docker compose up -d` at the repo root and connect with `postgresql://readonly:readonly@localhost:5432/chinook`.

## Table file format

`.csv`, `.txt`, `.tsv` or `.xlsx` (Excel; `.xls` is not supported). The separator for text files (comma, tab, `|` or `;`) is detected automatically, e.g. `sample_data/marks_pipe.txt`. Each populated worksheet in an Excel workbook becomes its own table. Column names are cleaned (`Order Date (UTC)` → `order_date_utc`), numbers and dates stored as text are converted, and each column is classified as date / id / number / category / text.

**Column descriptions (optional):** on the upload screen, explain unclear columns one per line as `column: meaning` or `table.column: meaning` (e.g. `marks: exam score out of 100`). They are added to the Table Metadata Store and reach both the summaries and the Text2SQL prompt.

**Dataset context (optional):** add a short description of the business/domain represented by the tables. It is included when generating table summaries, the dataset overview, and SQL-generation context.

Follow-up questions use the previous three question/SQL/answer turns to interpret short questions such as *"and in 2011?"*. Start **New dataset** to clear that conversation history.

## Query log format

`.sql` or `.txt` file of SELECT queries separated by `;`. `--` and `/* */` comments are ignored. For uploads, table names must match the cleaned file names (lowercase, no extension, spaces as `_`); for databases, they must match the real table names (matched case-insensitively, schema prefixes allowed). Queries that reference no known table are skipped. Up to 40 queries are indexed. Without logs, summaries are built from table metadata alone.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/upload` | form fields `files` (tables), `query_logs` (optional), `descriptions`, `dataset_description` → runs OFFLINE, returns session, source, relationships and dataset summary |
| POST | `/connect` | form fields `connection_url`, `db_schema`, `include_tables` (comma-separated), `query_logs`, `descriptions`, `dataset_description` → connects and builds the OFFLINE index |
| POST | `/connect/test` | form fields `connection_url`, `db_schema` → tests and lists tables without an LLM call |
| POST | `/ask` | `{session_id, question}` → runs ONLINE, returns answer, SQL, Top N / Top K tables, similar past queries, result rows |
| GET | `/session/{id}` | dataset summary and tables for a session |
| DELETE | `/session/{id}` | drop a session |
| GET | `/suggestions/{id}` | up to 4 suggested questions |
| GET | `/preview/{id}` | first 20 rows of each table |
| GET | `/health` | health check |

## Running tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
cd ../frontend
npm ci
npm run build
```

Backend tests use fake models and do not require a Groq key or download the embedding model.

## Limitations

- Sessions are in memory: lost on restart, expire after 1 hour idle.
- Upload sources infer join keys from identical column names; database sources use declared foreign keys first.
- Table summaries are generated in batches of up to five concurrent LLM calls, so large sources can take longer to index.
- Database column statistics use up to `PROFILE_SAMPLE_ROWS` records; min/max/category statistics may not represent every row.
- Query output is limited to `MAX_RESULT_ROWS`; SQLite statements are interrupted after `SQLITE_QUERY_TIMEOUT_SECONDS`.
- Non-SQLite/PostgreSQL database dialects depend on database-user permissions for read-only enforcement.
- "Why" answers show which categories drove a change, not real-world causes.
