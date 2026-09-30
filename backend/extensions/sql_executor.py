"""EXTENSION after [Generated SQL]: check it, run it on the data, retry on error.

The reference diagram hands the SQL back to the user. Here it is executed so the
user gets an answer. Two checks run first:
  - safety:    exactly one read-only SELECT
  - grounding: the query must read from an uploaded table (no answers typed from
               the LLM's own memory, e.g. SELECT 'Oklahoma City' AS capital)
"""
import re

from core.llm import make_chain
from offline.sql_query_logs import tables_in_query
from online.text2sql import extract_sql
from prompts.text2sql_prompt import FIX_SQL_PROMPT

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum)\b", re.I)
NO_ANSWER = "NO_ANSWER"
MAX_RETRIES = 2


def is_no_answer(sql: str) -> bool:
    return sql.strip().upper().startswith(NO_ANSWER)


def is_safe(sql: str) -> bool:
    s = sql.lstrip().lower()
    return s.startswith(("select", "with")) and ";" not in sql and not FORBIDDEN.search(sql)


class SQLExecutor:
    def __init__(self, llm, data_store, tables: dict):
        self.fix_chain = make_chain(FIX_SQL_PROMPT, llm)
        self.data_store = data_store
        self.tables = tables

    def run(self, sql: str):
        if not is_safe(sql):
            raise ValueError("Only a single read-only SELECT query is allowed.")
        if not tables_in_query(sql, self.tables):
            raise ValueError("The query does not read from any uploaded table. Use FROM <table> and "
                             "take the answer from the data, or reply NO_ANSWER if the data can't answer.")
        return self.data_store.query(sql)

    def run_with_retry(self, question: str, sql: str, schema: str, examples: str):
        """Returns (result DataFrame or None, final sql, error or None)."""
        for attempt in range(MAX_RETRIES + 1):
            if is_no_answer(sql):
                return None, sql, NO_ANSWER
            try:
                return self.run(sql), sql, None
            except Exception as e:
                if attempt == MAX_RETRIES:
                    return None, sql, str(e)
                sql = extract_sql(self.fix_chain.invoke({
                    "schema": schema, "examples": examples, "question": question,
                    "sql": sql, "error": str(e)}))
