"""[SQL Query Logs] (offline, grey box, top left).

Past SELECT queries, uploaded as a .sql / .txt file. Each query is linked to the
uploaded tables it reads, so it can be summarised and retrieved later.
"""
import re

from core.loader import clean_name

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


def tables_in_query(sql: str, known_tables) -> list:
    """Which uploaded tables a query reads from (its FROM / JOIN clauses)."""
    found = []
    for name in re.findall(r'(?i)\b(?:from|join)\s+["`\[]?([A-Za-z_][\w\.]*)', sql):
        t = clean_name(name.split(".")[-1])
        if t in known_tables and t not in found:
            found.append(t)
    return found


def build_query_log(queries: list, tables: dict) -> list:
    """Keep queries that use at least one uploaded table.
    Each entry: {'sql', 'tables', 'description'} (description is filled by the summarizer)."""
    log = []
    for q in queries[:MAX_LOG_QUERIES]:
        used = tables_in_query(q, tables)
        if used:
            log.append({"sql": q, "tables": used, "description": ""})
    return log
