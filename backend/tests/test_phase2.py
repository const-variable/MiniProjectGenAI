from types import SimpleNamespace

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.documents import Document
from langchain_core.embeddings.fake import DeterministicFakeEmbedding

from offline.vector_store import VectorStore
from online.pipeline import OnlinePipeline
from online.similarity_search import top_n_tables
from prompts.answer_prompt import OVERVIEW_PROMPT
from prompts.summarization_prompt import TABLE_SUMMARY_PROMPT
from prompts.text2sql_prompt import TEXT2SQL_PROMPT
from rag_session import TableRAGSession
from online.table_selection import TableSelector
from sources.upload_source import UploadSource


class MetadataStub:
    def schema_for(self, tables):
        return "Table items (value TEXT)"

    def joins_among(self, tables):
        return []


class RetrievalMustNotRun:
    retriever_kind = "vector"

    def similarity_search(self, *_args, **_kwargs):
        raise AssertionError("retrieve node should have been skipped")


class TextOnlyFakeChatModel(FakeListChatModel):
    def with_structured_output(self, *_args, **_kwargs):
        raise NotImplementedError("structured output is not supported by this test model")


def make_pipeline(responses):
    llm = TextOnlyFakeChatModel(responses=responses)
    source = UploadSource([("items.csv", b"item,category\na,first\nb,second\n")])
    index = SimpleNamespace(
        vector_store=RetrievalMustNotRun(),
        query_log=[],
        table_summaries={"items": "Simple item values."},
        metadata_store=MetadataStub(),
    )
    return OnlinePipeline(llm, index, source)


def test_graph_repairs_first_sql_failure_and_tracks_attempts():
    pipeline = make_pipeline([
        "```sql\nSELECT missing FROM items\n```",
        "```sql\nSELECT item FROM items\n```",
        "There are two values.",
    ])
    try:
        result = pipeline.run("List the values", tables_override=["items"])
        assert pipeline.last_state["attempts"] == 1
        assert result["answer"] == "There are two values."
        assert result["result"]["rows"] == [["a"], ["b"]]
    finally:
        pipeline.source.close()


def test_no_answer_routes_directly_to_answer_node():
    pipeline = make_pipeline(["NO_ANSWER"])
    try:
        result = pipeline.run("Question not covered", tables_override=["items"])
        assert result["error"] == "NO_ANSWER"
        assert "doesn't contain" in result["answer"]
        assert pipeline.last_state["attempts"] == 0
    finally:
        pipeline.source.close()


def test_retry_limit_returns_error_answer():
    pipeline = make_pipeline([
        "```sql\nSELECT missing FROM items\n```",
        "```sql\nSELECT still_missing FROM items\n```",
        "```sql\nSELECT also_missing FROM items\n```",
    ])
    try:
        result = pipeline.run("List the values", tables_override=["items"])
        assert pipeline.last_state["attempts"] == 2
        assert result["error"]
        assert "couldn't calculate" in result["answer"]
    finally:
        pipeline.source.close()


def test_table_override_skips_retrieval():
    pipeline = make_pipeline(["```sql\nSELECT item FROM items\n```", "Two items."])
    try:
        result = pipeline.run("List the values", tables_override=["items"])
        assert result["top_n_tables"] == []
        assert result["selected_tables"] == ["items"]
        assert "override" in result["selection_reason"]
    finally:
        pipeline.source.close()


def test_follow_up_question_is_condensed_before_sql_generation():
    pipeline = make_pipeline([
        "Which student scored highest in math?",
        "```sql\nSELECT item FROM items\n```",
        "The highest score is 95.",
    ])
    try:
        pipeline.run(
            "And in 2011?",
            tables_override=["items"],
            history=[{"question": "Which student scored highest?", "sql": "SELECT ...",
                      "answer": "Ari scored highest."}],
        )
        assert pipeline.last_state["standalone_question"] == "Which student scored highest in math?"
    finally:
        pipeline.source.close()


def test_table_selection_uses_text_fallback_without_structured_output():
    selector = TableSelector(TextOnlyFakeChatModel(responses=['["orders", "products"]']))
    selected, reason = selector.select(
        "What sold?", [{"name": "orders"}, {"name": "products"}],
        {"orders": "Sales", "products": "Catalog"}, MetadataStub(), k=2)
    assert selected == ["orders", "products"]
    assert reason


def test_hybrid_retriever_reports_reciprocal_rank_scores(monkeypatch):
    monkeypatch.setenv("RETRIEVER", "hybrid")
    documents = [
        Document(page_content="regional order sales", metadata={"kind": "table", "tables": ["orders"]}),
        Document(page_content="student exam scores", metadata={"kind": "table", "tables": ["scores"]}),
    ]
    store = VectorStore(documents, DeterministicFakeEmbedding(size=8))
    tables, similar, score_kind = top_n_tables(store, [], "sales orders")
    assert score_kind == "rank"
    assert similar == []
    assert tables
    assert tables[0]["score"] >= tables[-1]["score"]


def test_session_passes_only_last_three_turns_to_online_pipeline():
    class OnlineStub:
        def run(self, question, history):
            assert len(history) == 3
            assert [turn["question"] for turn in history] == ["q2", "q3", "q4"]
            return {"sql": "SELECT 1", "answer": "answer"}

    session = object.__new__(TableRAGSession)
    session.online = OnlineStub()
    session.history = [
        {"question": f"q{index}", "sql": "SELECT 1", "answer": "a"}
        for index in range(1, 5)
    ]
    session.ask("q5")
    assert [turn["question"] for turn in session.history] == ["q3", "q4", "q5"]


def test_dataset_context_is_available_to_relevant_prompt_templates():
    context = "School enrollment and assessment data"
    summary = TABLE_SUMMARY_PROMPT.format_messages(
        metadata="Students and scores", queries="(none)", dataset_description=context)
    overview = OVERVIEW_PROMPT.format_messages(profile="Students", dataset_description=context)
    sql = TEXT2SQL_PROMPT.format_messages(
        question="Which student scored highest?", schema="scores", examples="(none)",
        dialect="sqlite", dialect_rules="SQLite rules", dataset_context=f"Dataset context: {context}")
    assert context in summary[1].content
    assert context in overview[1].content
    assert context in sql[0].content