"""Common SQLAlchemy-backed interface for every dataset source."""
from abc import ABC, abstractmethod
import threading

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

    def query(self, sql: str, max_rows: int = 1000) -> pd.DataFrame:
        with self._query_lock, self.engine.connect() as connection:
            result = connection.execute(text(sql))
            rows = result.fetchmany(max(0, int(max_rows)))
            return pd.DataFrame(rows, columns=result.keys())

    def row_count(self, table: str) -> int:
        result = self.query(f"SELECT COUNT(*) AS count FROM {self.quote(table)}", max_rows=1)
        return int(result.iloc[0, 0])

    def preview(self, table: str, limit: int = 20) -> pd.DataFrame:
        return self.query(f"SELECT * FROM {self.quote(table)} LIMIT {int(limit)}")

    def close(self) -> None:
        self.engine.dispose()