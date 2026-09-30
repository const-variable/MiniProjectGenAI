import pytest

from extensions.sql_guard import parse_single_select, tables_in_query


def test_select_function_and_semicolon_literal_are_allowed():
    parse_single_select("SELECT replace(name, 'a', 'b') FROM t")
    parse_single_select("SELECT ';' AS x FROM t")


def test_cte_is_allowed_and_cte_names_are_not_sources():
    sql = "WITH recent AS (SELECT * FROM Orders) SELECT * FROM recent"
    parse_single_select(sql)
    assert tables_in_query(sql, ["Orders"]) == ["Orders"]


@pytest.mark.parametrize("sql", [
    "DROP TABLE t",
    "SELECT 1; DELETE FROM t",
    "WITH x AS (SELECT 1) DELETE FROM t",
])
def test_mutating_or_multiple_statements_are_rejected(sql):
    with pytest.raises(ValueError):
        parse_single_select(sql)


def test_comma_joins_and_case_insensitive_names_are_found():
    assert tables_in_query("SELECT * FROM A, b", ["a", "B"]) == ["a", "B"]


def test_postgres_schema_qualified_names_resolve_to_real_names():
    assert tables_in_query('SELECT * FROM public."InvoiceLine"', ["InvoiceLine"], "postgresql") == ["InvoiceLine"]


def test_quoted_case_sensitive_table_name_resolves():
    assert tables_in_query('SELECT * FROM "InvoiceLine"', ["InvoiceLine"]) == ["InvoiceLine"]
