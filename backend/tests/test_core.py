import langchain_huggingface

from core.embedding_model import load_embedding_model


def test_embedding_model_uses_configured_open_model(monkeypatch):
    monkeypatch.setenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    monkeypatch.setattr(
        langchain_huggingface,
        "HuggingFaceEmbeddings",
        lambda **kwargs: kwargs,
    )
    assert load_embedding_model() == {
        "model_name": "sentence-transformers/all-MiniLM-L6-v2",
    }