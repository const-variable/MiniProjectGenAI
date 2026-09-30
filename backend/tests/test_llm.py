from core.llm import is_llm_provider_error, load_llm


def test_load_llm_uses_groq_chat_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.delenv("LLM_CACHE", raising=False)

    model = load_llm()

    assert model.__class__.__name__ == "ChatGroq"


def test_provider_error_detection_uses_exception_type_only():
    class FakeGroqError(Exception):
        pass

    FakeGroqError.__module__ = "groq._exceptions"
    assert is_llm_provider_error(FakeGroqError("sensitive message"))
    assert not is_llm_provider_error(RuntimeError("ordinary failure"))