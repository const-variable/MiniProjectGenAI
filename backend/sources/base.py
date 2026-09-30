"""Common SQLAlchemy-backed interface for every dataset source."""
from abc import ABC, abstractmethod
import os
import threading
import time

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from langchain_community.utilities import SQLDatabase


def shared_column_joins(columns_by_table: dict[str, list[str]]) -> list[tuple[str, str, str, str]]:
    """Join-key heuristic when no foreign keys exist: identical column names across tables."""
    table_names = list(columns_by_table)
    join_keys = []
    for table_index, table_a in enumerate(table_names):
        for table_b in table_names[table_index + 1:]:
            shared_columns = set(columns_by_table[table_a]) & set(columns_by_table[table_b])
            join_keys.extend((table_a, column, table_b, column) for column in sorted(shared_columns))
    return join_keys


class DataSource(ABC):
    kind: str
    engine: Engine
    db: SQLDatabase
    schema: str | None = None

    def __init__(self, engine: Engine):
        self.engine = engine
        # The in-memory SQLite connection can't be used by two threads at once.
        self._query_lock = threading.Lock()

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    @abstractmethod
    def display_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def list_tables(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def columns(self, table: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def profile_frame(self, table: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def is_sampled(self, table: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def join_keys(self) -> list[tuple[str, str, str, str]]:
        raise NotImplementedError

    @abstractmethod
    def column_types(self, table: str) -> dict[str, str]:
        raise NotImplementedError

    def quote(self, identifier: str) -> str:
        return self.engine.dialect.identifier_preparer.quote(identifier)

    def qualified_name(self, table: str) -> str:
        quoted_table = self.quote(table)
        return f"{self.quote(self.schema)}.{quoted_table}" if self.schema else quoted_table

    def query(self, sql: str, max_rows: int | None = None) -> pd.DataFrame:
        if max_rows is None:
            max_rows = int(os.getenv("MAX_RESULT_ROWS", "1000"))
        with self._query_lock, self.engine.connect() as connection:
            raw_connection = connection.connection.driver_connection
            if self.dialect == "sqlite":
                # SQLite has no statement timeout; the progress handler aborts long queries.
                deadline = time.monotonic() + float(os.getenv("SQLITE_QUERY_TIMEOUT_SECONDS", "15"))
                raw_connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            try:
                query_cursor = connection.execute(text(sql))
                rows = query_cursor.fetchmany(max_rows)
                return pd.DataFrame(rows, columns=query_cursor.keys())
            finally:
                if self.dialect == "sqlite":
                    raw_connection.set_progress_handler(None, 0)

    def row_count(self, table: str) -> int:
        count_frame = self.query(f"SELECT COUNT(*) AS count FROM {self.qualified_name(table)}", max_rows=1)
        return int(count_frame.iloc[0, 0])

    def preview(self, table: str, limit: int = 20) -> pd.DataFrame:
        return self.query(f"SELECT * FROM {self.qualified_name(table)} LIMIT {int(limit)}")

    def close(self) -> None:
        self.engine.dispose()
