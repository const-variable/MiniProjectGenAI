from langchain_core.documents import Document

from online.similarity_search import top_n_tables


class Hits:
    retriever_kind = "vector"

    def __init__(self, values):
        self.values = values
        self.requested_k = None

    def similarity_search(self, question, k):
        self.requested_k = k
        return self.values[:k]


def test_table_and_sql_hits_combine_and_keep_best_distance():
    query_log = [{"description": f"query {index}", "sql": "SELECT * FROM orders"}
                 for index in range(4)]
    hits = Hits([
        (Document(page_content="table", metadata={"kind": "table", "tables": ["orders"]}), 0.4),
        (Document(page_content="log", metadata={"kind": "sql", "tables": ["orders"], "log": 0}), 0.2),
        (Document(page_content="another log", metadata={"kind": "sql", "tables": ["products"], "log": 1}), 0.3),
        (Document(page_content="third log", metadata={"kind": "sql", "tables": ["orders"], "log": 2}), 0.1),
        (Document(page_content="fourth log", metadata={"kind": "sql", "tables": ["orders"], "log": 3}), 0.15),
    ])

    candidate_tables, similar_queries, score_kind = top_n_tables(
        hits, query_log, "sales", candidate_limit=5)

    assert score_kind == "distance"
    assert hits.requested_k == 15
    assert candidate_tables == [{"name": "orders", "score": 0.1}, {"name": "products", "score": 0.3}]
    assert [query["description"] for query in similar_queries] == ["query 0", "query 1", "query 2"]


def test_top_n_environment_controls_retrieval_fan_out(monkeypatch):
    monkeypatch.setenv("TOP_N", "12")
    hits = Hits([])
    candidate_tables, similar_queries, score_kind = top_n_tables(hits, [], "question")
    assert hits.requested_k == 36
    assert candidate_tables == []
    assert similar_queries == []
    assert score_kind == "distance"