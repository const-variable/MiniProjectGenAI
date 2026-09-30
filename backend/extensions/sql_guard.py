"""Dialect-aware validation and table extraction for generated read queries."""
import sqlglot
from sqlglot import exp


READ_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
FORBIDDEN_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
                   exp.Alter, exp.Command, exp.Merge)


def _sqlglot_dialect(dialect: str) -> str:
    # SQLAlchemy says "postgresql"; sqlglot calls it "postgres".
    return {"postgresql": "postgres"}.get(dialect.lower(), dialect.lower())


def parse_single_select(sql: str, dialect: str = "sqlite"):
    try:
        statements = sqlglot.parse(sql, read=_sqlglot_dialect(dialect))
    except sqlglot.errors.ParseError as error:
        raise ValueError(f"SQL could not be parsed for {dialect}: {error}") from error
    if len(statements) != 1 or statements[0] is None:
        raise ValueError("Exactly one SQL statement is allowed.")
    syntax_tree = statements[0]
    if not isinstance(syntax_tree, READ_ROOTS):
        raise ValueError("Only a read-only SELECT query is allowed.")
    if any(isinstance(node, FORBIDDEN_NODES) for node in syntax_tree.walk()):
        raise ValueError("Only a read-only SELECT query is allowed.")
    return syntax_tree


def tables_in_query(sql: str, known_tables: list[str], dialect: str = "sqlite") -> list[str]:
    """Real table names the query reads, matched case-insensitively and skipping CTE names."""
    syntax_tree = parse_single_select(sql, dialect)
    cte_names = {cte.alias_or_name.casefold() for cte in syntax_tree.find_all(exp.CTE)}
    known_by_folded_name = {table.casefold(): table for table in known_tables}
    referenced_tables = []
    for table_node in syntax_tree.find_all(exp.Table):
        folded_name = table_node.name.casefold()
        table = known_by_folded_name.get(folded_name)
        if folded_name not in cte_names and table and table not in referenced_tables:
            referenced_tables.append(table)
    return referenced_tables
