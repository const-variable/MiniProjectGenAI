"""FastAPI app: the entry point. Run from the backend folder:
    uvicorn main:app --reload --port 8000
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.embedding_model import load_embedding_model
from core.llm import load_llm
from core.loader import _decode
from offline.sql_query_logs import parse_query_logs
from offline.table_metadata_store import parse_notes
from rag_session import TableRAGSession
from sessions import SessionStore
from sources import DBSource, UploadSource

# Load backend/.env no matter which folder the server is started from.
load_dotenv(Path(__file__).parent / ".env")
for _key in ("LLM_PROVIDER", "LLM_MODEL"):
    if not os.getenv(_key):
        raise RuntimeError(f"{_key} is not set. Create backend/.env (copy .env.example) and fill it in.")

MAX_BYTES = int(float(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024)
LOG_EXTENSIONS = (".sql", ".txt")
models = {}                      # LLM + embedding model, loaded once at startup
sessions = SessionStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if "llm" not in models:
        models["llm"] = load_llm()
    if "embeddings" not in models:
        models["embeddings"] = load_embedding_model()
    yield


app = FastAPI(title="Table RAG API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- schemas

class ColumnInfo(BaseModel):
    name: str
    type: str


class TableInfo(BaseModel):
    name: str
    rows: int
    summary: str
    columns: List[ColumnInfo]


class ResultTable(BaseModel):
    columns: List[str]
    rows: List[List[Any]]


class UploadResponse(BaseModel):
    session_id: str
    summary: str
    query_logs: int
    tables: List[TableInfo]
    source: dict


class AskRequest(BaseModel):
    session_id: str
    question: str


class CandidateTable(BaseModel):
    name: str
    score: float


class SimilarQuery(BaseModel):
    description: str
    sql: str


class AskResponse(BaseModel):
    answer: str
    sql: str
    top_n_tables: List[CandidateTable]
    selected_tables: List[str]
    similar_queries: List[SimilarQuery]
    result: ResultTable
    error: Optional[str] = None


def get_session(session_id: str) -> TableRAGSession:
    s = sessions.get(session_id)
    if s is None:
        raise HTTPException(404, "Session not found or expired. Please build the dataset again.")
    return s


def session_payload(sid: str, s: TableRAGSession) -> dict:
    return {"session_id": sid, "summary": s.summary, "query_logs": len(s.query_log),
            "tables": s.tables_info(), "source": {"kind": s.source.kind,
            "dialect": s.source.dialect, "name": s.source.display_name()}}


def read_query_logs(query_logs: Optional[List[UploadFile]]) -> list[str]:
    queries = []
    for file in query_logs or []:
        name = file.filename or "logs"
        if not name.lower().endswith(LOG_EXTENSIONS):
            raise HTTPException(400, f"{name}: query logs must be .sql or .txt files.")
        queries.extend(parse_query_logs(_decode(file.file.read())))
    return queries


def build_session(source, descriptions: str, queries: list[str]) -> tuple[str, TableRAGSession]:
    try:
        session = TableRAGSession(source, models["llm"], models["embeddings"],
                                  notes=parse_notes(descriptions), raw_queries=queries)
    except Exception:
        source.close()
        raise
    return sessions.create(session), session


# ---------------------------------------------------------------- endpoints
# Plain `def` (not async): FastAPI runs these in a thread pool, so a slow
# LLM call for one user doesn't block everyone else.

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
def upload(
    files: List[UploadFile] = File(...),
    query_logs: Optional[List[UploadFile]] = File(None),
    descriptions: str = Form(""),
):
    """Tables (+ optional SQL query logs) -> OFFLINE VECTOR INDEX CREATION."""
    queries = read_query_logs(query_logs)
    try:
        source = UploadSource([(f.filename or "table", f.file.read()) for f in files], MAX_BYTES)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    try:
        sid, session = build_session(source, descriptions, queries)
    except Exception as error:
        raise HTTPException(500, f"Failed to build the knowledge base: {error}") from error
    return session_payload(sid, session)


@app.post("/connect", response_model=UploadResponse)
def connect_database(
    connection_url: str = Form(...),
    db_schema: str = Form(""),
    include_tables: str = Form(""),
    query_logs: Optional[List[UploadFile]] = File(None),
    descriptions: str = Form(""),
):
    """Connect a read-only database source and build its offline index."""
    queries = read_query_logs(query_logs)
    try:
        tables = [table.strip() for table in include_tables.split(",") if table.strip()] or None
        source = DBSource(connection_url, db_schema.strip() or None, tables)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    try:
        sid, session = build_session(source, descriptions, queries)
    except Exception as error:
        raise HTTPException(500, f"Failed to build the knowledge base: {error}") from error
    return session_payload(sid, session)


@app.post("/connect/test")
def test_database_connection(connection_url: str = Form(...), db_schema: str = Form("")):
    """Check a database connection without loading models or building an index."""
    try:
        source = DBSource(connection_url, db_schema.strip() or None)
        tables = source.list_tables()
        return {"connected": True, "tables": tables, "count": len(tables),
                "dialect": source.dialect, "name": source.display_name()}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    finally:
        if "source" in locals():
            source.close()


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """Question -> ONLINE TEXT2SQL."""
    if not req.question.strip():
        raise HTTPException(400, "Question is empty.")
    s = get_session(req.session_id)
    try:
        return s.ask(req.question.strip())
    except Exception as e:
        raise HTTPException(500, f"Failed to answer: {e}")


@app.get("/session/{session_id}", response_model=UploadResponse)
def session_info(session_id: str):
    return session_payload(session_id, get_session(session_id))


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    return {"deleted": sessions.delete(session_id)}


@app.get("/suggestions/{session_id}")
def suggestions(session_id: str):
    return {"questions": get_session(session_id).suggestions()}


@app.get("/preview/{session_id}")
def preview(session_id: str):
    return {"tables": get_session(session_id).preview()}
