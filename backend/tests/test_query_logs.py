from offline import sql_query_logs
from offline.sql_query_logs import build_query_log, parse_query_logs


def test_comments_and_non_select_statements_are_filtered():
    parsed = parse_query_logs("-- line comment\nSELECT * FROM orders; DROP TABLE orders; "
                              "/* block */ SELECT * FROM products;")
    assert parsed == ["SELECT * FROM orders", "SELECT * FROM products"]


def test_query_log_requires_known_tables_and_respects_limit(monkeypatch):
    monkeypatch.setattr(sql_query_logs, "MAX_LOG_QUERIES", 1)
    log = build_query_log([
        "SELECT * FROM missing",
        "SELECT * FROM orders",
        "SELECT * FROM products",
    ], ["orders", "products"])
    assert len(log) == 1
    assert log[0]["tables"] == ["orders"]