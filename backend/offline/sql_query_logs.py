"""[SQL Query Logs] (offline, grey box, top left).

Past SELECT queries, uploaded as a .sql / .txt file. Each query is linked to the
uploaded tables it reads, so it can be summarised and retrieved later.
"""
import logging
import re

from extensions.sql_guard import tables_in_query as parsed_tables_in_query

MAX_LOG_QUERIES = 40
logger = logging.getLogger(__name__)


def parse_query_logs(log_text: str) -> list:
    """Split a log file into individual SELECT queries (comments removed)."""
    log_text = re.sub(r"/\*.*?\*/", " ", log_text or "", flags=re.S)
    sql_statements = []
    for statement_part in log_text.split(";"):
        sql_statement = "\n".join(
            line for line in statement_part.splitlines()
            if not line.strip().startswith("--")).strip()
        if re.match(r"(?is)^(select|with)\b", sql_statement):
            sql_statements.append(sql_statement)
    return sql_statements


def tables_in_query(sql: str, known_tables, dialect: str = "sqlite") -> list:
    """Which source tables a query reads, falling back for unsupported log SQL."""
    try:
        return parsed_tables_in_query(sql, known_tables, dialect)
    except ValueError as error:
        logger.debug("SQL log parser fallback (%s)", type(error).__name__)
    found = []
    known = {table.casefold(): table for table in known_tables}
    for name in re.findall(r'(?i)\b(?:from|join)\s+["`\[]?([A-Za-z_][\w\.]*)', sql):
        table = known.get(name.split(".")[-1].casefold())
        if table and table not in found:
            found.append(table)
    return found


def build_query_log(sql_statements: list, source_tables: list[str], dialect: str = "sqlite") -> list:
    query_log = []
    for sql_statement in sql_statements:
        if len(query_log) >= MAX_LOG_QUERIES:
            break
        referenced_tables = tables_in_query(sql_statement, source_tables, dialect)
        if referenced_tables:
            query_log.append({"sql": sql_statement, "tables": referenced_tables, "description": ""})
    return query_log
