"""FastAPI app: the entry point. Run from the backend folder:
    uvicorn main:app --reload --port 8000
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.embedding_model import load_embedding_model
from core.llm import is_llm_provider_error, load_llm
from core.loader import decode_text
from offline.sql_query_logs import parse_query_logs
from offline.table_metadata_store import parse_notes
from rag_session import TableRAGSession
from sessions import SessionStore
from sources import DBSource, UploadSource

# Load backend/.env no matter which folder the server is started from.
load_dotenv(Path(__file__).parent / ".env")
if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY is not set. Create backend/.env (copy .env.example) and fill it in.")

MAX_BYTES = int(float(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024)
LOG_EXTENSIONS = (".sql", ".txt")
models = {}                      # LLM + embedding model, loaded once at startup
sessions = SessionStore()
logger = logging.getLogger(__name__)
PROVIDER_ERROR_DETAIL = (
    "The LLM provider returned an error: check GROQ_API_KEY, model availability, or quota."
)


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
    allow_origins=[origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ColumnInfo(BaseModel):
    name: str
    type: str


class TableInfo(BaseModel):
    name: str
    rows: int
    summary: str
    columns: List[ColumnInfo]
    example_questions: List[str] = []


class RelationshipInfo(BaseModel):
    table_a: str
    column_a: str
    table_b: str
    column_b: str


class QueryResult(BaseModel):
    columns: List[str]
    rows: List[List[Any]]


class UploadResponse(BaseModel):
    session_id: str
    summary: str
    query_logs: int
    tables: List[TableInfo]
    source: dict
    relationships: List[RelationshipInfo] = []


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
    result: QueryResult
    error: Optional[str] = None
    selection_reason: Optional[str] = None
    sql_explanation: Optional[str] = None
    score_kind: str = "distance"
    standalone_question: Optional[str] = None


def get_session(session_id: str) -> TableRAGSession:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found or expired. Please build the dataset again.")
    return session


def session_payload(session_id: str, session: TableRAGSession) -> dict:
    return {"session_id": session_id, "summary": session.summary,
            "query_logs": len(session.query_log), "tables": session.tables_info(),
            "source": {"kind": session.source.kind, "dialect": session.source.dialect,
                       "name": session.source.display_name()},
            "relationships": [{"table_a": table_a, "column_a": column_a,
                               "table_b": table_b, "column_b": column_b}
                              for table_a, column_a, table_b, column_b in session.source.join_keys()]}


def read_query_logs(sql_files: Optional[List[UploadFile]]) -> list[str]:
    sql_statements = []
    for query_log_file in sql_files or []:
        filename = query_log_file.filename or "logs"
        if not filename.lower().endswith(LOG_EXTENSIONS):
            raise HTTPException(400, f"{filename}: query logs must be .sql or .txt files.")
        sql_statements.extend(parse_query_logs(decode_text(query_log_file.file.read())))
    return sql_statements


def build_session(source, descriptions: str, dataset_description: str,
                  sql_statements: list[str]) -> dict:
    try:
        session = TableRAGSession(source, models["llm"], models["embeddings"],
                                  notes=parse_notes(descriptions), raw_queries=sql_statements,
                                  dataset_description=dataset_description)
    except Exception as error:
        source.close()
        logger.warning("Indexing failed for %s source (%s)", source.kind, type(error).__name__)
        if is_llm_provider_error(error):
            raise HTTPException(502, PROVIDER_ERROR_DETAIL) from error
        raise HTTPException(500, "Failed to build the knowledge base.") from error
    return session_payload(sessions.create(session), session)


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
    dataset_description: str = Form(""),
):
    """Build an index from uploaded table files and optional SQL logs."""
    sql_statements = read_query_logs(query_logs)
    try:
        source = UploadSource([(table_file.filename or "table", table_file.file.read())
                               for table_file in files], MAX_BYTES)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return build_session(source, descriptions, dataset_description, sql_statements)


@app.post("/connect", response_model=UploadResponse)
def connect_database(
    connection_url: str = Form(...),
    db_schema: str = Form(""),
    include_tables: str = Form(""),
    query_logs: Optional[List[UploadFile]] = File(None),
    descriptions: str = Form(""),
    dataset_description: str = Form(""),
):
    """Connect to a database and build an index from its selected tables."""
    sql_statements = read_query_logs(query_logs)
    table_names = [table.strip() for table in include_tables.split(",") if table.strip()] or None
    try:
        source = DBSource(connection_url, db_schema.strip() or None, table_names)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return build_session(source, descriptions, dataset_description, sql_statements)


@app.post("/connect/test")
def test_database_connection(connection_url: str = Form(...), db_schema: str = Form("")):
    try:
        source = DBSource(connection_url, db_schema.strip() or None)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    try:
        table_names = source.list_tables()
        return {"connected": True, "tables": table_names, "count": len(table_names),
                "dialect": source.dialect, "name": source.display_name()}
    finally:
        source.close()


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    """Retrieve tables, generate guarded SQL, and answer from its query rows."""
    if not request.question.strip():
        raise HTTPException(400, "Question is empty.")
    session = get_session(request.session_id)
    try:
        return session.ask(request.question.strip())
    except Exception as error:
        logger.warning("Ask endpoint failed (%s)", type(error).__name__)
        if is_llm_provider_error(error):
            raise HTTPException(502, PROVIDER_ERROR_DETAIL) from error
        raise HTTPException(500, "Failed to answer the question.") from error


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
