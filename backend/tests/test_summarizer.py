from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from offline.summarizer import Summarizer
from prompts.schemas import QueryDescriptions, QueryDescription, TableSummary


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


class StructuredSummaryModel(FakeListChatModel):
    def with_structured_output(self, schema):
        if schema is TableSummary:
            return RunnableLambda(lambda _input: TableSummary(
                summary="Table summary.", example_questions=["Which rows are present?"]))
        if schema is QueryDescriptions:
            return RunnableLambda(lambda _input: QueryDescriptions(queries=[
                QueryDescription(index=1, description="Orders by date"),
                QueryDescription(index=2, description="Product catalog"),
            ]))
        raise AssertionError(f"Unexpected structured schema: {schema}")


def test_query_summary_uses_structured_output_when_supported():
    query_log = [
        {"sql": "SELECT * FROM orders", "tables": ["orders"], "description": ""},
        {"sql": "SELECT * FROM products", "tables": ["products"], "description": ""},
    ]
    Summarizer(StructuredSummaryModel(responses=[])).summarise_queries(query_log)
    assert [entry["description"] for entry in query_log] == [
        "Orders by date", "Product catalog"]