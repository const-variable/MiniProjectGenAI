"""[LLM] boxes in the diagram (blue).

One chat model is created at startup and shared by every prompt:
Summarization Prompt, Table Selection Prompt and Text2SQL Prompt.
"""
import os

from langchain_core.output_parsers import StrOutputParser


def load_llm():
    """Create the chat model named in backend/.env (LLM_PROVIDER + LLM_MODEL)."""
    from langchain.chat_models import init_chat_model
    return init_chat_model(os.environ["LLM_MODEL"],
                           model_provider=os.environ["LLM_PROVIDER"], temperature=0)


def make_chain(prompt, llm):
    """Prompt -> LLM -> plain text. Every arrow 'Prompt -> LLM' in the diagram is one of these."""
    return prompt | llm | StrOutputParser()
