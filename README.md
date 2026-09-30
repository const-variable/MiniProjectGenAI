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
│   └── loader.py                  reads and profiles uploaded delimited files
│
├── sources/                       shared SQLAlchemy-backed data sources
│   ├── base.py                    DataSource interface and query helpers
│   ├── upload_source.py           uploaded files in in-memory SQLite
│   └── db_source.py               read-only SQLite / PostgreSQL / other databases
│
├── prompts/                       green boxes
│   ├── summarization_prompt.py    [Summarization Prompt]
│   ├── table_selection_prompt.py  [Table Selection Prompt]
│   ├── text2sql_prompt.py         [Text2SQL Prompt]
│   └── answer_prompt.py           extension: answer, overview, suggestions
│
├── offline/                       OFFLINE VECTOR INDEX CREATION
│   ├── build_index.py             ▶ the offline pipeline, steps 1-5
│   ├── table_metadata_store.py    [Table Metadata Store]   red cylinder
│   ├── sql_query_logs.py          [SQL Query Logs]
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
sample_data/                       sample CSVs + Chinook SQLite database + SQL logs
docs/reference_architecture.png    the architecture this code implements
```

**To follow the flow, read two files:** `offline/build_index.py` (top half of the diagram) and `online/pipeline.py` (bottom half). Both source types implement `DataSource`, and each step calls the module for that box.

## Offline: runs once per upload (`offline/build_index.py`)

| Step | Diagram box | File |
|---|---|---|
| 1 | Table Metadata Store | `offline/table_metadata_store.py` |
| 2 | SQL Query Logs | `offline/sql_query_logs.py` |
| 3 | Summarization Prompt → LLM → Table/SQL Summary | `offline/summarizer.py`, `prompts/summarization_prompt.py` |
| 4 | Embedding Model | `core/embedding_model.py` |
| 5 | Vector Store → Embeddings Index | `offline/vector_store.py` |

## Online: runs per question (`online/pipeline.py`)

| Step | Diagram box | File |
|---|---|---|
| 1 | Data Analytical Question → Embedding Model | `core/embedding_model.py` |
| 2 | Similarity Search → Top N Tables | `online/similarity_search.py` |
| 3 | Table Selection Prompt → LLM → Top K Tables | `online/table_selection.py` |
| 4 | Text2SQL Prompt (+ Table Metadata Store) → LLM → Generated SQL | `online/text2sql.py` |
| 5 | *Extension:* check, execute, retry | `extensions/sql_executor.py` |
| 6 | *Extension:* grounded answer | `extensions/answer_generator.py` |

**Why the extensions:** the diagram returns SQL to the user. Our users are non-technical, so the SQL is run and explained. Two checks come first: the query must be one read-only SELECT, and it must **read from a table in the current dataset**. The second check stops the LLM answering from memory (e.g. `SELECT 'Oklahoma City' AS capital`); if the data can't answer, the system says so.

## Run it locally

Needs **Python 3.10+** and **Node.js 18+**. Two terminals.

**Terminal 1: backend**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add your Groq API key
uvicorn main:app --reload --port 8000
```
Wait for `Application startup complete`. API test page: http://localhost:8000/docs

**Terminal 2: frontend**
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173.

### Configuration (`backend/.env`)

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER`, `LLM_MODEL` | Defaults in `.env.example`: `groq` + `openai/gpt-oss-120b`, an open-weight chat model served by Groq. Both are configurable. |
| `GROQ_API_KEY` | Groq API credential for hosted inference (see `.env.example`). |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | Optional OpenAI-compatible provider configuration, such as OpenRouter. |
| `EMBED_MODEL` | Open-source local embedding model, default `sentence-transformers/all-MiniLM-L6-v2`. |
| `FRONTEND_ORIGINS` | Allowed CORS origins, default `http://localhost:5173` |
| `MAX_UPLOAD_MB` | Max size per table file, default `20` |
| `MAX_DB_TABLES` | Maximum discovered database tables, default `50`; narrow the connection with the table list when exceeded |
| `PROFILE_SAMPLE_ROWS` | Maximum rows sampled per database table for profiling, default `5000` |

The frontend reads `VITE_API_URL` (default `http://localhost:8000`).

## Demo with uploaded files

1. **Tables:** upload `orders.csv`, `products.csv`, `students.csv`, `scores.csv` together.
2. **Query logs:** upload `query_logs.sql`.
3. Ask *"Why did revenue decrease in the last quarter, and which product category contributed the most?"*
   Open **How this was answered**: Top N should list all four tables, Top K should keep only `orders` and `products`, and the answer should be Electronics.

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

`.csv`, `.txt` or `.tsv`. The separator (comma, tab, `|` or `;`) is detected automatically, e.g. `sample_data/marks_pipe.txt`. Column names are cleaned (`Order Date (UTC)` → `order_date_utc`), numbers and dates stored as text are converted, and each column is classified as date / id / number / category / text.

**Column descriptions (optional):** on the upload screen, explain unclear columns one per line as `column: meaning` or `table.column: meaning` (e.g. `marks: exam score out of 100`). They are added to the Table Metadata Store and reach both the summaries and the Text2SQL prompt.

## Query log format

`.sql` or `.txt` file of SELECT queries separated by `;`. `--` comments are ignored. Table names must match the uploaded file names (lowercase, no extension, spaces as `_`). Up to 40 queries are indexed. Without logs, summaries are built from table metadata alone.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/upload` | form fields `files` (tables), `query_logs` (optional), `descriptions` → runs OFFLINE, returns `session_id`, source, dataset summary, tables |
| POST | `/connect` | form fields `connection_url`, `db_schema`, `include_tables` (comma-separated), `query_logs` (optional), `descriptions` → connects and builds the OFFLINE index |
| POST | `/connect/test` | form fields `connection_url`, `db_schema` → tests and lists tables without an LLM call |
| POST | `/ask` | `{session_id, question}` → runs ONLINE, returns answer, SQL, Top N / Top K tables, similar past queries, result rows |
| GET | `/session/{id}` | dataset summary and tables for a session |
| DELETE | `/session/{id}` | drop a session |
| GET | `/suggestions/{id}` | up to 4 suggested questions |
| GET | `/preview/{id}` | first 20 rows of each table |
| GET | `/health` | health check |

## Limitations

- Sessions are in memory: lost on restart, expire after 1 hour idle.
- Upload sources infer join keys from identical column names; database sources use declared foreign keys first.
- Table summaries are generated in batches of up to five concurrent LLM calls, so large sources can take longer to index.
- "Why" answers show which categories drove a change, not real-world causes.
