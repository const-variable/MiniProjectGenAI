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


def build_offline_index(tables: dict, llm, embedding_model, notes: dict | None = None,
                        raw_queries: list | None = None) -> OfflineIndex:
    # Step 1: Table Metadata Store
    types = {t: classify_columns(df) for t, df in tables.items()}
    metadata_store = TableMetadataStore(tables, types, notes)

    # Step 2: SQL Query Logs
    query_log = build_query_log(raw_queries or [], tables)

    # Step 3: Summarization Prompt -> LLM -> Table/SQL Summary
    summarizer = Summarizer(llm)
    summarizer.summarise_queries(query_log)
    table_summaries = {
        t: summarizer.summarise_table(
            t, metadata_store.get(t), query_log,
            fallback=f'Table with {len(df)} rows and columns: {", ".join(df.columns)}.')
        for t, df in tables.items()
    }

    # Steps 4 + 5: Embedding Model -> Vector Store (Embeddings Index)
    documents = [table_document(t, table_summaries[t], tables[t].columns) for t in tables]
    documents += [sql_document(i, entry) for i, entry in enumerate(query_log)]
    vector_store = VectorStore(documents, embedding_model)

    return OfflineIndex(metadata_store, query_log, table_summaries, vector_store)
