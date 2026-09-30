"""[Vector Store] (orange cylinder): [Embeddings Index] + [Similarity Search].

Built offline from Table/SQL Summary embeddings; searched online with the
question embedding. FAISS runs in memory.
"""
import os

from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document


def table_document(table: str, summary: str, column_names,
                   example_questions: list[str] | None = None) -> Document:
    suggested_questions_text = "\n".join(example_questions or [])
    document_text = f'Table "{table}": {summary}\nColumns: {", ".join(column_names)}'
    if suggested_questions_text:
        document_text += "\nExample questions:\n" + suggested_questions_text
    return Document(page_content=document_text,
                    metadata={"kind": "table", "tables": [table]})


def sql_document(query_log_index: int, query_log_entry: dict) -> Document:
    return Document(page_content=f'{query_log_entry["description"]}\nSQL: {query_log_entry["sql"]}',
                    metadata={"kind": "sql", "tables": query_log_entry["tables"],
                              "log": query_log_index})


class VectorStore:
    def __init__(self, documents: list, embedding_model):
        self.documents = documents
        self.faiss_index = FAISS.from_documents(documents, embedding_model)
        self.retriever_kind = os.getenv("RETRIEVER", "vector").lower()
        if self.retriever_kind not in {"vector", "hybrid"}:
            raise ValueError("RETRIEVER must be either 'vector' or 'hybrid'.")

    def similarity_search(self, question: str, k: int = 10) -> list:  # k: hyperparameter
        """Embed the question and return [(document, distance)]. L2 distance: lower is more similar."""
        return self.faiss_index.similarity_search_with_score(question, k=min(k, len(self.documents)))

    def as_retriever(self, k: int):
        vector_retriever = self.faiss_index.as_retriever(
            search_kwargs={"k": min(k, len(self.documents))})
        if self.retriever_kind == "vector":
            return vector_retriever
        keyword_retriever = BM25Retriever.from_documents(self.documents, k=min(k, len(self.documents)))
        return EnsembleRetriever(
            retrievers=[vector_retriever, keyword_retriever],
            weights=[0.5, 0.5],  # hyperparameter
        )
