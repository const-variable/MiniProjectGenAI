"""[Tables] in the diagram: the user's uploaded data, loaded into an in-memory SQL database.

The vector store only holds summaries. The actual rows live here, and the
generated SQL runs against them.
"""
import sqlite3
import threading

import pandas as pd


class DataStore:
    def __init__(self, tables: dict):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        for name, df in tables.items():
            out = df.copy()
            for c in out.columns:
                if pd.api.types.is_datetime64_any_dtype(out[c]):
                    out[c] = out[c].dt.strftime("%Y-%m-%d")   # SQLite has no date type
            out.to_sql(name, self.conn, index=False)

    def query(self, sql: str) -> pd.DataFrame:
        with self._lock:
            return pd.read_sql_query(sql, self.conn)
