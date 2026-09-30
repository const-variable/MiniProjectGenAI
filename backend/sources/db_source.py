"""Read-only SQLAlchemy source for existing database tables."""
import os
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import make_url

from core.loader import convert_types
from sources.base import DataSource


class DBSource(DataSource):
    kind = "database"

    def __init__(self, url: str, schema: str | None = None,
                 include_tables: list[str] | None = None):
        self.schema = schema or None
        self._profile_sample_rows = int(os.getenv("PROFILE_SAMPLE_ROWS", "5000"))
        max_tables = int(os.getenv("MAX_DB_TABLES", "50"))
        try:
            engine = self._create_engine(url)
            super().__init__(engine)
            inspector = inspect(engine)
            self._tables = inspector.get_table_names(schema=self.schema)
            if include_tables:
                missing = sorted(set(include_tables) - set(self._tables))
                if missing:
                    raise ValueError("Unknown table(s): " + ", ".join(missing))
                self._tables = [table for table in self._tables if table in include_tables]
            if len(self._tables) > max_tables:
                raise ValueError(
                    f"Database has {len(self._tables)} tables; select at most {max_tables} with include_tables."
                )
            self._foreign_keys = self._load_foreign_keys(inspector)
            self.db = SQLDatabase(
                engine,
                schema=self.schema,
                include_tables=self._tables,
                sample_rows_in_table_info=3,
            )
        except ValueError:
            if "engine" in locals():
                engine.dispose()
            raise
        except SQLAlchemyError as error:
            if "engine" in locals():
                engine.dispose()
            raise ValueError("Could not connect to the database or inspect its schema.") from error

    @staticmethod
    def _create_engine(url: str):
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite":
            database = parsed.database
            if not database or database in (":memory:", "file::memory:"):
                raise ValueError("In-memory SQLite connections are not supported.")
            path = Path(database.removeprefix("file:")).expanduser().resolve()
            if not path.is_file():
                raise ValueError("SQLite database file does not exist.")
            readonly_url = f"sqlite:///file:{quote(str(path), safe='/')}?mode=ro&uri=true"
            return create_engine(readonly_url, connect_args={"uri": True}, pool_pre_ping=True)
        if parsed.get_backend_name() == "postgresql":
            return create_engine(
                url,
                connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=15000"},
                pool_pre_ping=True,
            )
        return create_engine(url, pool_pre_ping=True)

    def _load_foreign_keys(self, inspector) -> list[tuple[str, str, str, str]]:
        keys = []
        for table in self._tables:
            for foreign_key in inspector.get_foreign_keys(table, schema=self.schema):
                referred = foreign_key.get("referred_table")
                local_columns = foreign_key.get("constrained_columns") or []
                remote_columns = foreign_key.get("referred_columns") or []
                if referred in self._tables:
                    keys.extend((table, local, referred, remote)
                                for local, remote in zip(local_columns, remote_columns))
        if keys:
            return keys
        names = list(self._tables)
        keys = []
        for index, table_a in enumerate(names):
            columns_a = set(self.columns(table_a))
            for table_b in names[index + 1:]:
                keys.extend((table_a, column, table_b, column)
                            for column in sorted(columns_a & set(self.columns(table_b))))
        return keys

    def display_name(self) -> str:
        return self.engine.url.render_as_string(hide_password=True)

    def query(self, sql: str, max_rows: int = 1000) -> pd.DataFrame:
        try:
            return super().query(sql, max_rows)
        except SQLAlchemyError as error:
            raise ValueError("Database query failed. Check the SQL and database permissions.") from error

    def list_tables(self) -> list[str]:
        return list(self._tables)

    def columns(self, table: str) -> list[str]:
        return [column["name"] for column in inspect(self.engine).get_columns(table, schema=self.schema)]

    def column_types(self, table: str) -> dict[str, str]:
        return {column["name"]: str(column["type"])
                for column in inspect(self.engine).get_columns(table, schema=self.schema)}

    def row_count(self, table: str) -> int:
        qualified = self.quote(table)
        if self.schema:
            qualified = f"{self.quote(self.schema)}.{qualified}"
        result = self.query(f"SELECT COUNT(*) AS count FROM {qualified}", max_rows=1)
        return int(result.iloc[0, 0])

    def profile_frame(self, table: str) -> pd.DataFrame:
        qualified = self.quote(table)
        if self.schema:
            qualified = f"{self.quote(self.schema)}.{qualified}"
        return convert_types(self.query(
            f"SELECT * FROM {qualified} LIMIT {self._profile_sample_rows}",
            max_rows=self._profile_sample_rows,
        ))

    def is_sampled(self, table: str) -> bool:
        return self.row_count(table) > self._profile_sample_rows

    def join_keys(self) -> list[tuple[str, str, str, str]]:
        return list(self._foreign_keys)