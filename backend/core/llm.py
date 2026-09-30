"""[LLM] boxes in the diagram (blue).

One chat model is created at startup and shared by every prompt:
Summarization Prompt, Table Selection Prompt and Text2SQL Prompt.
"""
import os

from langchain_core.output_parsers import StrOutputParser


def load_llm():
    """Create the Groq-hosted open-weight chat model from backend/.env."""
    from langchain_groq import ChatGroq
    cache = os.getenv("LLM_CACHE", "").lower()
    if cache == "sqlite":
        from langchain_community.cache import SQLiteCache
        from langchain_core.globals import set_llm_cache
        set_llm_cache(SQLiteCache(".llm_cache.db"))
    return ChatGroq(
        model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        api_key=os.environ["GROQ_API_KEY"],
        temperature=0,
    )


def is_llm_provider_error(error: Exception) -> bool:
    """Identify errors raised by the configured Groq client without inspecting messages."""
    return any(cls.__module__.split(".", 1)[0] in {"groq", "langchain_groq"}
               for cls in type(error).__mro__)


def make_chain(prompt, llm):
    """Prompt -> LLM -> plain text. Every arrow 'Prompt -> LLM' in the diagram is one of these."""
    return prompt | llm | StrOutputParser()
