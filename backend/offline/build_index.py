"""OFFLINE VECTOR INDEX CREATION: the top half of the diagram, step by step.

  Step 1  Table Metadata Store        profile every uploaded table
  Step 2  SQL Query Logs              link each past query to its tables
  Step 3  Summarization Prompt + LLM  -> Table/SQL Summary
  Step 4  Embedding Model             -> Table/SQL Summary Embeddings
  Step 5  Vector Store                -> Embeddings Index
"""
from dataclasses import dataclass
from core.loader import classify_columns
from offline.sql_query_logs import build_query_log
from offline.summarizer import Summarizer
from offline.table_metadata_store import TableMetadataStore
from offline.vector_store import VectorStore, sql_document, table_document


@dataclass
class OfflineIndex:
    metadata_store: TableMetadataStore
    query_log: list
    table_summaries: dict
    vector_store: VectorStore


def build_offline_index(source, llm, embedding_model, notes: dict | None = None,
                        raw_queries: list | None = None) -> OfflineIndex:
    # Step 1: Table Metadata Store
    tables = source.list_tables()
    frames = {table: source.profile_frame(table) for table in tables}
    types = {table: classify_columns(frame) for table, frame in frames.items()}
    metadata_store = TableMetadataStore(source, types, notes)

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
        })
    try:
        summaries = summarizer.table_chain.batch(
            summary_inputs, config={"max_concurrency": 5}, return_exceptions=True)
    except Exception:
        summaries = [RuntimeError("Table summary failed") for _ in tables]
    table_summaries = {}
    for table, frame, summary in zip(tables, frames.values(), summaries):
        if isinstance(summary, Exception):
            summary = f'Table with {source.row_count(table)} rows and columns: {", ".join(frame.columns)}.'
        table_summaries[table] = str(summary).strip()

    # Steps 4 + 5: Embedding Model -> Vector Store (Embeddings Index)
    documents = [table_document(t, table_summaries[t], source.columns(t)) for t in tables]
    documents += [sql_document(i, entry) for i, entry in enumerate(query_log)]
    vector_store = VectorStore(documents, embedding_model)

    return OfflineIndex(metadata_store, query_log, table_summaries, vector_store)
