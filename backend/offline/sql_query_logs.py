"""[SQL Query Logs] (offline, grey box, top left).

Past SELECT queries, uploaded as a .sql / .txt file. Each query is linked to the
uploaded tables it reads, so it can be summarised and retrieved later.
"""
import re

from extensions.sql_guard import tables_in_query as parsed_tables_in_query

MAX_LOG_QUERIES = 40


def parse_query_logs(text: str) -> list:
    """Split a log file into individual SELECT queries (comments removed)."""
    text = re.sub(r"/\*.*?\*/", " ", text or "", flags=re.S)
    queries = []
    for part in text.split(";"):
        q = "\n".join(ln for ln in part.splitlines() if not ln.strip().startswith("--")).strip()
        if re.match(r"(?is)^(select|with)\b", q):
            queries.append(q)
    return queries


def tables_in_query(sql: str, known_tables, dialect: str = "sqlite") -> list:
    """Which source tables a query reads, falling back for unsupported log SQL."""
    try:
        return parsed_tables_in_query(sql, known_tables, dialect)
    except ValueError:
        pass
    found = []
    known = {table.casefold(): table for table in known_tables}
    for name in re.findall(r'(?i)\b(?:from|join)\s+["`\[]?([A-Za-z_][\w\.]*)', sql):
        table = known.get(name.split(".")[-1].casefold())
        if table and table not in found:
            found.append(table)
    return found


def build_query_log(queries: list, tables: list[str], dialect: str = "sqlite") -> list:
    """Keep queries that use at least one uploaded table.
    Each entry: {'sql', 'tables', 'description'} (description is filled by the summarizer)."""
    log = []
    for q in queries[:MAX_LOG_QUERIES]:
        used = tables_in_query(q, tables, dialect)
        if used:
            log.append({"sql": q, "tables": used, "description": ""})
    return log
