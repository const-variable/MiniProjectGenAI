"""Dialect-aware validation and table extraction for generated read queries."""
import sqlglot
from sqlglot import exp


READ_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
FORBIDDEN_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
                   exp.Alter, exp.Command, exp.Merge)


def _dialect_name(dialect: str) -> str:
    return {"postgresql": "postgres"}.get(dialect.lower(), dialect.lower())


def parse_single_select(sql: str, dialect: str = "sqlite"):
    try:
        statements = sqlglot.parse(sql, read=_dialect_name(dialect))
    except sqlglot.errors.ParseError as error:
        raise ValueError(f"SQL could not be parsed for {dialect}: {error}") from error
    if len(statements) != 1 or statements[0] is None:
        raise ValueError("Exactly one SQL statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, READ_ROOTS):
        raise ValueError("Only a read-only SELECT query is allowed.")
    if any(isinstance(node, FORBIDDEN_NODES) for node in tree.walk()):
        raise ValueError("Only a read-only SELECT query is allowed.")
    return tree


def tables_in_query(sql: str, known_tables: list[str], dialect: str = "sqlite") -> list[str]:
    tree = parse_single_select(sql, dialect)
    cte_names = {cte.alias_or_name.casefold() for cte in tree.find_all(exp.CTE)}
    known = {table.casefold(): table for table in known_tables}
    found = []
    for table in tree.find_all(exp.Table):
        name = table.name
        folded = name.casefold()
        if folded not in cte_names and folded in known and known[folded] not in found:
            found.append(known[folded])
    return found