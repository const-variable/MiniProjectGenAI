"""[Vector Store] (orange cylinder): [Embeddings Index] + [Similarity Search].

Built offline from Table/SQL Summary embeddings; searched online with the
question embedding. FAISS runs in memory.
"""
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document


def table_document(table: str, summary: str, columns) -> Document:
    return Document(page_content=f'Table "{table}": {summary}\nColumns: {", ".join(columns)}',
                    metadata={"kind": "table", "tables": [table]})


def sql_document(index: int, entry: dict) -> Document:
    return Document(page_content=f'{entry["description"]}\nSQL: {entry["sql"]}',
                    metadata={"kind": "sql", "tables": entry["tables"], "log": index})


class VectorStore:
    def __init__(self, documents: list, embedding_model):
        """Embeddings Index: every document is embedded and stored."""
        self.documents = documents
        self.index = FAISS.from_documents(documents, embedding_model)

    def similarity_search(self, question: str, k: int = 10) -> list:
        """Similarity Search: embeds the question and returns [(document, distance)].
        Distance is L2, so LOWER means MORE similar."""
        return self.index.similarity_search_with_score(question, k=min(k, len(self.documents)))
