"""OFFLINE VECTOR INDEX CREATION: the top half of the diagram, step by step.

  Step 1  Table Metadata Store        profile every uploaded table
  Step 2  SQL Query Logs              link each past query to its tables
  Step 3  Summarization Prompt + LLM  -> Table/SQL Summary
  Step 4  Embedding Model             -> Table/SQL Summary Embeddings
  Step 5  Vector Store                -> Embeddings Index
"""
from dataclasses import dataclass
import logging
from core.loader import classify_columns
from offline.sql_query_logs import build_query_log
from offline.summarizer import Summarizer
from offline.table_metadata_store import TableMetadataStore
from offline.vector_store import VectorStore, sql_document, table_document
from prompts.schemas import TableSummary

logger = logging.getLogger(__name__)


@dataclass
class OfflineIndex:
    metadata_store: TableMetadataStore
    query_log: list
    table_summaries: dict
    table_example_questions: dict
    vector_store: VectorStore


def build_offline_index(source, llm, embedding_model, notes: dict | None = None,
                        raw_queries: list | None = None,
                        dataset_description: str = "") -> OfflineIndex:
    # Step 1: Table Metadata Store
    tables = source.list_tables()
    frames = {table: source.profile_frame(table) for table in tables}
    types = {table: classify_columns(frame) for table, frame in frames.items()}
    metadata_store = TableMetadataStore(source, types, notes, dataset_description)

    # Step 2: SQL Query Logs
    query_log = build_query_log(raw_queries or [], tables, source.dialect)

    # Step 3: Summarization Prompt -> LLM -> Table/SQL Summary
    summarizer = Summarizer(llm)
    summarizer.summarise_queries(query_log)
    summary_inputs = []
    for table in tables:
        queries = [q["sql"] for q in query_log if table in q["tables"]][:10]
        summary_inputs.append({
            "metadata": metadata_store.get(table),
            "queries": "\n\n".join(queries) or "(no query logs provided)",
            "dataset_description": dataset_description.strip() or "(not provided)",
        })
    try:
        summaries = summarizer.table_chain.batch(
            summary_inputs, config={"max_concurrency": 5}, return_exceptions=True)
    except Exception as error:
        logger.warning("Batch table summarization failed (%s); using metadata fallback", type(error).__name__)
        summaries = [RuntimeError("Table summary failed") for _ in tables]
    table_summaries = {}
    table_example_questions = {}
    for table, frame, summary in zip(tables, frames.values(), summaries):
        if isinstance(summary, Exception):
            summary = f'Table with {source.row_count(table)} rows and columns: {", ".join(frame.columns)}.'
        if isinstance(summary, TableSummary):
            table_summaries[table] = summary.summary.strip()
            table_example_questions[table] = summary.example_questions
        elif isinstance(summary, dict):
            table_summaries[table] = str(summary.get("summary", "")).strip()
            table_example_questions[table] = list(summary.get("example_questions", []))
        else:
            table_summaries[table] = str(summary).strip()
            table_example_questions[table] = []

    # Steps 4 + 5: Embedding Model -> Vector Store (Embeddings Index)
    documents = [table_document(t, table_summaries[t], source.columns(t), table_example_questions[t])
                 for t in tables]
    documents += [sql_document(i, entry) for i, entry in enumerate(query_log)]
    vector_store = VectorStore(documents, embedding_model)

    return OfflineIndex(metadata_store, query_log, table_summaries, table_example_questions, vector_store)
