from langchain_core.language_models.fake_chat_models import FakeListChatModel

from offline.summarizer import Summarizer
from prompts.schemas import TableSummary


def test_query_summary_plain_text_fallback_parses_numbered_lines():
    query_log = [
        {"sql": "SELECT * FROM orders", "tables": ["orders"], "description": ""},
        {"sql": "SELECT * FROM products", "tables": ["products"], "description": ""},
    ]
    summarizer = Summarizer(FakeListChatModel(
        responses=["1. Summarizes orders\n2. Summarizes products"]))
    summarizer.summarise_queries(query_log)
    assert [entry["description"] for entry in query_log] == [
        "Summarizes orders", "Summarizes products"]


def test_query_summary_parser_returns_pydantic_descriptions():
    query_log = [
        {"sql": "SELECT * FROM orders", "tables": ["orders"], "description": ""},
        {"sql": "SELECT * FROM products", "tables": ["products"], "description": ""},
    ]
    Summarizer(FakeListChatModel(responses=[
        '{"queries":[{"query_number":1,"description":"Orders by date"},'
        '{"query_number":2,"description":"Product catalog"}]}'
    ])).summarise_queries(query_log)
    assert [entry["description"] for entry in query_log] == [
        "Orders by date", "Product catalog"]


def test_table_summary_parser_returns_pydantic_model():
    summary = '{"summary":"Orders record purchases.","example_questions":["What sold?"]}'
    summarizer = Summarizer(FakeListChatModel(responses=[summary]))
    parsed = summarizer.table_chain.invoke({
        "metadata": "Orders table",
        "queries": "(none)",
        "dataset_description": "Retail orders",
    })
    assert isinstance(parsed, TableSummary)
    assert parsed.summary == "Orders record purchases."


def test_table_summary_parser_error_uses_text_prompt_fallback():
    text_summary = "Orders record purchases and their total amounts."
    summarizer = Summarizer(FakeListChatModel(responses=["not JSON", text_summary]))
    summaries = summarizer.summarise_tables([{
        "metadata": "Orders table",
        "queries": "(none)",
        "dataset_description": "Retail orders",
    }])
    assert summaries == [TableSummary(summary=text_summary, example_questions=[])]