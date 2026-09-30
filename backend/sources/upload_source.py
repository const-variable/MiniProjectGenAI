"""Uploaded delimited files, backed by a shared in-memory SQLite engine."""
from pathlib import Path
import io
import os

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from langchain_community.utilities import SQLDatabase

from core.loader import ALLOWED_EXTENSIONS, clean_name, clean_table, read_table
from sources.base import DataSource


class UploadSource(DataSource):
    kind = "upload"

    def __init__(self, files: list[tuple[str, bytes]], max_bytes: int | None = None):
        engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        super().__init__(engine)
        self._max_tables = int(os.getenv("MAX_TABLES_PER_UPLOAD", "20"))
        self._max_rows = int(os.getenv("MAX_ROWS_PER_TABLE", "1000000"))
        self.frames: dict[str, pd.DataFrame] = {}
        self._join_keys: list[tuple[str, str, str, str]] = []
        try:
            if len(files) > self._max_tables:
                raise ValueError(f"Upload contains more than {self._max_tables} table files.")
            for filename, raw in files:
                self._add_file(filename, raw, max_bytes)
            self._join_keys = self._identical_column_joins()
            self.db = SQLDatabase(engine, sample_rows_in_table_info=3)
        except Exception:
            self.close()
            raise

    def _add_file(self, filename: str, raw: bytes, max_bytes: int | None) -> None:
        name = filename or "table"
        if not name.lower().endswith(ALLOWED_EXTENSIONS):
            raise ValueError(f"{name}: tables must be .csv, .txt, .tsv or .xlsx files.")
        if max_bytes is not None and len(raw) > max_bytes:
            raise ValueError(f"{name} is larger than {max_bytes // (1024 * 1024)} MB.")
        try:
            if name.lower().endswith(".xlsx"):
                sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
                populated = [(sheet, clean_table(frame)) for sheet, frame in sheets.items()
                             if not frame.empty and frame.shape[1] > 0]
                if not populated:
                    raise ValueError("workbook has no data in any sheet")
                base = clean_name(Path(name).stem)
                for sheet, frame in populated:
                    table_name = base if len(populated) == 1 else clean_name(f"{base}_{sheet}")
                    self._add_frame(table_name, frame)
                return
            frame = clean_table(read_table(raw))
        except Exception as error:
            if isinstance(error, ValueError) and str(error).startswith(f"{name}"):
                raise
            raise ValueError(f"Could not read {name}: {error}") from error
        if frame.empty or frame.shape[1] == 0:
            raise ValueError(f"{name} has no data.")

        self._add_frame(clean_name(Path(name).stem), frame)

    def _add_frame(self, base: str, frame: pd.DataFrame) -> None:
        if len(self.frames) >= self._max_tables:
            raise ValueError(f"Upload exceeds the maximum of {self._max_tables} tables.")
        if len(frame) > self._max_rows:
            raise ValueError(
                f"{base} has {len(frame):,} rows; the maximum is {self._max_rows:,} rows per table."
            )
        table, suffix = base, 2
        while table in self.frames:
            table, suffix = f"{base}_{suffix}", suffix + 1
        sql_frame = frame.copy()
        for column in sql_frame.columns:
            if pd.api.types.is_datetime64_any_dtype(sql_frame[column]):
                sql_frame[column] = sql_frame[column].dt.strftime("%Y-%m-%d")
        sql_frame.to_sql(table, self.engine, index=False)
        self.frames[table] = frame

    def _identical_column_joins(self) -> list[tuple[str, str, str, str]]:
        names = list(self.frames)
        joins = []
        for index, table_a in enumerate(names):
            for table_b in names[index + 1:]:
                for column in sorted(set(self.frames[table_a].columns) & set(self.frames[table_b].columns)):
                    joins.append((table_a, column, table_b, column))
        return joins

    def display_name(self) -> str:
        count = len(self.frames)
        return f"{count} uploaded file{'s' if count != 1 else ''}"

    def list_tables(self) -> list[str]:
        return list(self.frames)

    def columns(self, table: str) -> list[str]:
        return [str(column) for column in self.frames[table].columns]

    def row_count(self, table: str) -> int:
        return len(self.frames[table])

    def profile_frame(self, table: str) -> pd.DataFrame:
        return self.frames[table].copy()

    def is_sampled(self, table: str) -> bool:
        return False

    def join_keys(self) -> list[tuple[str, str, str, str]]:
        return list(self._join_keys)

    def column_types(self, table: str) -> dict[str, str]:
        return {column: str(dtype) for column, dtype in self.frames[table].dtypes.items()}