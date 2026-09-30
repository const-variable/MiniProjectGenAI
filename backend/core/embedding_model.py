"""[Embedding Model] boxes in the diagram (yellow).

The SAME model is used offline (to embed Table/SQL summaries) and online
(to embed the user's question), so both live in the same vector space.
"""
import os


def load_embedding_model():
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(
        model_name=os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
