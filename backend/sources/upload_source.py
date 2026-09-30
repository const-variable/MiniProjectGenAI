"""Uploaded delimited files and Excel workbooks, backed by a shared in-memory SQLite engine."""
from pathlib import Path
import io
import os

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from langchain_community.utilities import SQLDatabase

from core.loader import ALLOWED_EXTENSIONS, clean_name, clean_table, read_table
from sources.base import DataSource, shared_column_joins


class UploadSource(DataSource):
    kind = "upload"

    def __init__(self, files: list[tuple[str, bytes]], max_bytes: int | None = None):
        # StaticPool keeps one connection, so every query sees the same in-memory database.
        engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        super().__init__(engine)
        self._max_tables = int(os.getenv("MAX_TABLES_PER_UPLOAD", "20"))
        self._max_rows = int(os.getenv("MAX_ROWS_PER_TABLE", "1000000"))
        self.table_frames: dict[str, pd.DataFrame] = {}
        try:
            if len(files) > self._max_tables:
                raise ValueError(f"Upload contains more than {self._max_tables} table files.")
            for filename, file_bytes in files:
                self._add_file(filename, file_bytes, max_bytes)
            self._join_keys = shared_column_joins(
                {table: list(frame.columns) for table, frame in self.table_frames.items()})
            self.db = SQLDatabase(engine, sample_rows_in_table_info=3)
        except Exception:
            self.close()
            raise

    def _add_file(self, filename: str, file_bytes: bytes, max_bytes: int | None) -> None:
        if not filename.lower().endswith(ALLOWED_EXTENSIONS):
            raise ValueError(f"{filename}: tables must be .csv, .txt, .tsv or .xlsx files.")
        if max_bytes is not None and len(file_bytes) > max_bytes:
            raise ValueError(f"{filename} is larger than {max_bytes // (1024 * 1024)} MB.")
        try:
            if filename.lower().endswith(".xlsx"):
                sheet_frames = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
            else:
                sheet_frames = {"": read_table(file_bytes)}
            cleaned_sheets = {sheet_name: clean_table(sheet_frame)
                              for sheet_name, sheet_frame in sheet_frames.items()}
        except Exception as error:  # pandas and openpyxl raise many parser-specific types
            raise ValueError(f"Could not read {filename}: {error}") from error

        populated_sheets = {sheet_name: sheet_frame for sheet_name, sheet_frame in cleaned_sheets.items()
                            if not sheet_frame.empty}
        if not populated_sheets:
            raise ValueError(f"{filename} has no data.")
        # A multi-sheet workbook becomes one table per populated sheet.
        table_base_name = clean_name(Path(filename).stem)
        for sheet_name, sheet_frame in populated_sheets.items():
            table_name = (table_base_name if len(populated_sheets) == 1
                          else clean_name(f"{table_base_name}_{sheet_name}"))
            self._add_frame(table_name, sheet_frame)

    def _add_frame(self, table_base_name: str, table_frame: pd.DataFrame) -> None:
        if len(self.table_frames) >= self._max_tables:
            raise ValueError(f"Upload exceeds the maximum of {self._max_tables} tables.")
        if len(table_frame) > self._max_rows:
            raise ValueError(
                f"{table_base_name} has {len(table_frame):,} rows; "
                f"the maximum is {self._max_rows:,} rows per table.")
        table_name, duplicate_number = table_base_name, 2
        while table_name in self.table_frames:
            table_name = f"{table_base_name}_{duplicate_number}"
            duplicate_number += 1
        # SQLite has no DATE type; the SQL prompt rules assume 'YYYY-MM-DD' text.
        sql_frame = table_frame.copy()
        for column_name in sql_frame.columns:
            if pd.api.types.is_datetime64_any_dtype(sql_frame[column_name]):
                sql_frame[column_name] = sql_frame[column_name].dt.strftime("%Y-%m-%d")
        sql_frame.to_sql(table_name, self.engine, index=False)
        self.table_frames[table_name] = table_frame

    def display_name(self) -> str:
        table_count = len(self.table_frames)
        return f"{table_count} uploaded file{'s' if table_count != 1 else ''}"

    def list_tables(self) -> list[str]:
        return list(self.table_frames)

    def columns(self, table: str) -> list[str]:
        return [str(column) for column in self.table_frames[table].columns]

    def row_count(self, table: str) -> int:
        return len(self.table_frames[table])

    def profile_frame(self, table: str) -> pd.DataFrame:
        return self.table_frames[table].copy()

    def is_sampled(self, table: str) -> bool:
        return False

    def join_keys(self) -> list[tuple[str, str, str, str]]:
        return list(self._join_keys)

    def column_types(self, table: str) -> dict[str, str]:
        return {column: str(dtype) for column, dtype in self.table_frames[table].dtypes.items()}
