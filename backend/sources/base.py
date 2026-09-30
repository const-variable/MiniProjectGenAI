"""Common SQLAlchemy-backed interface for every dataset source."""
from abc import ABC, abstractmethod
import os
import threading
import time

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from langchain_community.utilities import SQLDatabase


class DataSource(ABC):
    kind: str
    engine: Engine
    db: SQLDatabase

    def __init__(self, engine: Engine):
        self.engine = engine
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

    def query(self, sql: str, max_rows: int | None = None) -> pd.DataFrame:
        row_limit = max_rows if max_rows is not None else int(os.getenv("MAX_RESULT_ROWS", "1000"))
        with self._query_lock, self.engine.connect() as connection:
            raw_connection = connection.connection.driver_connection
            if self.dialect == "sqlite":
                deadline = time.monotonic() + float(os.getenv("SQLITE_QUERY_TIMEOUT_SECONDS", "15"))
                raw_connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            try:
                result = connection.execute(text(sql))
                rows = result.fetchmany(max(0, int(row_limit)))
                return pd.DataFrame(rows, columns=result.keys())
            finally:
                if self.dialect == "sqlite":
                    raw_connection.set_progress_handler(None, 0)

    def row_count(self, table: str) -> int:
        result = self.query(f"SELECT COUNT(*) AS count FROM {self.quote(table)}", max_rows=1)
        return int(result.iloc[0, 0])

    def preview(self, table: str, limit: int = 20) -> pd.DataFrame:
        return self.query(f"SELECT * FROM {self.quote(table)} LIMIT {int(limit)}")

    def close(self) -> None:
        self.engine.dispose()