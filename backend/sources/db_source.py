"""Read-only SQLAlchemy source for existing database tables."""
import os
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from core.loader import convert_types
from sources.base import DataSource, shared_column_joins


class DBSource(DataSource):
    kind = "database"

    def __init__(self, url: str, schema: str | None = None,
                 include_tables: list[str] | None = None):
        self.schema = schema or None
        self._profile_sample_rows = int(os.getenv("PROFILE_SAMPLE_ROWS", "5000"))
        max_tables = int(os.getenv("MAX_DB_TABLES", "50"))
        super().__init__(self._create_engine(url))
        try:
            inspector = inspect(self.engine)
            self._tables = inspector.get_table_names(schema=self.schema)
            if include_tables:
                missing_tables = sorted(set(include_tables) - set(self._tables))
                if missing_tables:
                    raise ValueError("Unknown table(s): " + ", ".join(missing_tables))
                self._tables = [table for table in self._tables if table in include_tables]
            if len(self._tables) > max_tables:
                raise ValueError(
                    f"Database has {len(self._tables)} tables; select at most {max_tables} with include_tables.")
            self._foreign_keys = self._load_foreign_keys(inspector)
            self.db = SQLDatabase(self.engine, schema=self.schema, include_tables=self._tables,
                                  sample_rows_in_table_info=3)
        except ValueError:
            self.close()
            raise
        except SQLAlchemyError as error:
            self.close()
            # Don't echo the driver message: it can contain the connection URL.
            raise ValueError("Could not connect to the database or inspect its schema.") from error

    @staticmethod
    def _create_engine(url: str):
        parsed_url = make_url(url)
        if parsed_url.get_backend_name() == "sqlite":
            database_path = parsed_url.database
            if not database_path or database_path in (":memory:", "file::memory:"):
                raise ValueError("In-memory SQLite connections are not supported.")
            path = Path(database_path.removeprefix("file:")).expanduser().resolve()
            if not path.is_file():
                raise ValueError("SQLite database file does not exist.")
            readonly_url = f"sqlite:///file:{quote(str(path), safe='/')}?mode=ro&uri=true"
            return create_engine(readonly_url, connect_args={"uri": True}, pool_pre_ping=True)
        if parsed_url.get_backend_name() == "postgresql":
            return create_engine(
                url,
                connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=15000"},
                pool_pre_ping=True,
            )
        # Other dialects are untested; read-only access then depends on the database user.
        return create_engine(url, pool_pre_ping=True)

    def _load_foreign_keys(self, inspector) -> list[tuple[str, str, str, str]]:
        join_keys = []
        for table in self._tables:
            for foreign_key in inspector.get_foreign_keys(table, schema=self.schema):
                referred_table = foreign_key.get("referred_table")
                if referred_table in self._tables:
                    join_keys.extend(
                        (table, local_column, referred_table, remote_column)
                        for local_column, remote_column in zip(
                            foreign_key.get("constrained_columns") or [],
                            foreign_key.get("referred_columns") or []))
        return join_keys or shared_column_joins({table: self.columns(table) for table in self._tables})

    def display_name(self) -> str:
        return self.engine.url.render_as_string(hide_password=True)

    def query(self, sql: str, max_rows: int | None = None) -> pd.DataFrame:
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

    def profile_frame(self, table: str) -> pd.DataFrame:
        sample_frame = self.query(
            f"SELECT * FROM {self.qualified_name(table)} LIMIT {self._profile_sample_rows}",
            max_rows=self._profile_sample_rows)
        return convert_types(sample_frame)

    def is_sampled(self, table: str) -> bool:
        return self.row_count(table) > self._profile_sample_rows

    def join_keys(self) -> list[tuple[str, str, str, str]]:
        return list(self._foreign_keys)
