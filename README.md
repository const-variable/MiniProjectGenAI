# Table RAG: Text2SQL with a vector index over table and SQL summaries

Upload tables (and optionally past SQL queries), ask questions in plain English, get SQL plus a grounded answer.
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
│   ├── data_store.py              [Tables]           the rows, in in-memory SQLite
│   └── loader.py                  reads .csv/.txt, cleans, classifies columns
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
    └── answer_generator.py        result → plain-English answer

frontend/                          React UI (upload, chat, "How this was answered")
sample_data/                       4 tables + query_logs.sql
docs/reference_architecture.png    the architecture this code implements
```

**To follow the flow, read two files:** `offline/build_index.py` (top half of the diagram) and `online/pipeline.py` (bottom half). Each step is numbered and calls the module for that box.

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

**Why the extensions:** the diagram returns SQL to the user. Our users are non-technical, so the SQL is run and explained. Two checks come first: the query must be one read-only SELECT, and it must **read from an uploaded table**. The second check stops the LLM answering from memory (e.g. `SELECT 'Oklahoma City' AS capital`); if the data can't answer, the system says so.

## Run it locally

Needs **Python 3.10+** and **Node.js 18+**. Two terminals.

**Terminal 1: backend**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add your API key (OpenRouter works)
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

## Demo with the sample data

1. **Tables:** upload `orders.csv`, `products.csv`, `students.csv`, `scores.csv` together.
2. **Query logs:** upload `query_logs.sql`.
3. Ask *"Why did revenue decrease in the last quarter, and which product category contributed the most?"*
   Open **How this was answered**: Top N should list all four tables, Top K should keep only `orders` and `products`, and the answer should be Electronics.

## Query log format

`.sql` or `.txt` file of SELECT queries separated by `;`. `--` comments are ignored. Table names must match the uploaded file names (lowercase, no extension, spaces as `_`). Up to 40 queries are indexed. Without logs, summaries are built from table metadata alone.

## Limitations

- Sessions are in memory: lost on restart, expire after 1 hour idle.
- Join keys are detected by identical column names across tables.
- One LLM call per table on upload, so many tables mean a slower upload.
- "Why" answers show which categories drove a change, not real-world causes.
