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
    table_example_questions: dict
    vector_store: VectorStore


def build_offline_index(source, llm, embedding_model, notes: dict | None = None,
                        raw_queries: list | None = None,
                        dataset_description: str = "") -> OfflineIndex:
    # Step 1: Profile tables before assembling schema metadata.
    tables = source.list_tables()
    types = {table: classify_columns(source.profile_frame(table)) for table in tables}
    metadata_store = TableMetadataStore(source, types, notes, dataset_description)

    # Step 2: Attach each logged query to its referenced source tables.
    query_log = build_query_log(raw_queries or [], tables, source.dialect)

    # Step 3: Summarize table profiles and useful query patterns.
    summarizer = Summarizer(llm)
    summarizer.summarise_queries(query_log)
    summary_inputs = []
    for table in tables:
        table_queries = [entry["sql"] for entry in query_log if table in entry["tables"]][:10]
        summary_inputs.append({
            "metadata": metadata_store.get(table),
            "queries": "\n\n".join(table_queries) or "(no query logs provided)",
            "dataset_description": dataset_description.strip() or "(not provided)",
        })
    summaries = summarizer.summarise_tables(summary_inputs)
    table_summaries = {table: summary.summary.strip() for table, summary in zip(tables, summaries)}
    table_example_questions = {table: summary.example_questions
                               for table, summary in zip(tables, summaries)}

    # Steps 4 + 5: Embed summaries for question-time retrieval.
    search_documents = [
        table_document(table, table_summaries[table], source.columns(table),
                       table_example_questions[table])
        for table in tables
    ]
    search_documents += [sql_document(query_index, query_entry)
                         for query_index, query_entry in enumerate(query_log)]
    vector_store = VectorStore(search_documents, embedding_model)

    return OfflineIndex(metadata_store, query_log, table_summaries, table_example_questions, vector_store)
