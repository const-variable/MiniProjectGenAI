"""[Vector Store] (orange cylinder): [Embeddings Index] + [Similarity Search].

Built offline from Table/SQL Summary embeddings; searched online with the
question embedding. FAISS runs in memory.
"""
import os

from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document


def table_document(table: str, summary: str, columns, example_questions: list[str] | None = None) -> Document:
    question_text = "\n".join(example_questions or [])
    content = f'Table "{table}": {summary}\nColumns: {", ".join(columns)}'
    if question_text:
        content += "\nExample questions:\n" + question_text
    return Document(page_content=content,
                    metadata={"kind": "table", "tables": [table]})


def sql_document(index: int, entry: dict) -> Document:
    return Document(page_content=f'{entry["description"]}\nSQL: {entry["sql"]}',
                    metadata={"kind": "sql", "tables": entry["tables"], "log": index})


class VectorStore:
    def __init__(self, documents: list, embedding_model):
        """Embeddings Index: every document is embedded and stored."""
        self.documents = documents
        self.index = FAISS.from_documents(documents, embedding_model)
        self.retriever_kind = os.getenv("RETRIEVER", "vector").lower()
        if self.retriever_kind not in {"vector", "hybrid"}:
            raise ValueError("RETRIEVER must be either 'vector' or 'hybrid'.")

    def similarity_search(self, question: str, k: int = 10) -> list:
        """Similarity Search: embeds the question and returns [(document, distance)].
        Distance is L2, so LOWER means MORE similar."""
        return self.index.similarity_search_with_score(question, k=min(k, len(self.documents)))

    def as_retriever(self, k: int):
        """Build the configured vector-only or reciprocal-rank ensemble retriever."""
        vector_retriever = self.index.as_retriever(search_kwargs={"k": min(k, len(self.documents))})
        if self.retriever_kind == "vector":
            return vector_retriever
        keyword_retriever = BM25Retriever.from_documents(self.documents, k=min(k, len(self.documents)))
        return EnsembleRetriever(
            retrievers=[vector_retriever, keyword_retriever],
            weights=[0.5, 0.5],
        )
