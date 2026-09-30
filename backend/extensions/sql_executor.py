"""EXTENSION after [Generated SQL]: check it, run it on the data.

The reference diagram hands the SQL back to the user. Here it is executed so the
user gets an answer. Two checks run first:
  - safety:    exactly one read-only SELECT
  - grounding: the query must read from a table in the dataset (no answers typed
               from the LLM's own memory, e.g. SELECT 'Oklahoma City' AS capital)
"""
from extensions.sql_guard import tables_in_query

NO_ANSWER = "NO_ANSWER"
MAX_RETRIES = 2  # hyperparameter


def is_no_answer(sql: str) -> bool:
    return sql.strip().upper().startswith(NO_ANSWER)


class SQLExecutor:
    def __init__(self, source):
        self.source = source

    def run(self, sql: str):
        # tables_in_query parses with the guard, so unsafe SQL raises before execution.
        if not tables_in_query(sql, self.source.list_tables(), self.source.dialect):
            raise ValueError("The query does not read from a table in this dataset. Use FROM <table> and "
                             "take the answer from the data, or reply NO_ANSWER if the data can't answer.")
        return self.source.query(sql)
