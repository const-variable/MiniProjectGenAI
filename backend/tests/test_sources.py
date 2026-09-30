from pathlib import Path

import pytest

from sources.db_source import DBSource
from sources.upload_source import UploadSource

ROOT = Path(__file__).resolve().parents[2]


def test_uploads_sample_csvs_and_pipe_file():
    files = [(path.name, path.read_bytes()) for path in (ROOT / "sample_data").glob("*.csv")]
    files.append(("marks_pipe.txt", (ROOT / "sample_data" / "marks_pipe.txt").read_bytes()))
    source = UploadSource(files)
    try:
        assert {"orders", "products", "students", "scores", "marks_pipe"} <= set(source.list_tables())
        assert source.dialect == "sqlite"
    finally:
        source.close()


def test_duplicate_filenames_and_query_row_cap():
    raw = b"id,value\n1,a\n2,b\n3,c\n"
    source = UploadSource([("items.csv", raw), ("items.csv", raw)])
    try:
        assert source.list_tables() == ["items", "items_2"]
        assert len(source.query("SELECT * FROM items", max_rows=2)) == 2
        assert len(source.preview("items", limit=1)) == 1
    finally:
        source.close()


def test_db_source_preserves_names_and_is_read_only():
    path = ROOT / "sample_data" / "chinook.sqlite"
    source = DBSource(f"sqlite:///{path}")
    try:
        assert len(source.list_tables()) == 11
        assert "InvoiceLine" in source.list_tables()
        assert ("InvoiceLine", "InvoiceId", "Invoice", "InvoiceId") in source.join_keys()
        assert "sqlite" in source.display_name()
        with pytest.raises(Exception):
            source.query("DELETE FROM Genre")
        assert "Genre" in source.list_tables()
    finally:
        source.close()


def test_db_source_rejects_missing_sqlite_path_without_echoing_credentials():
    with pytest.raises(ValueError) as error:
        DBSource("sqlite:////definitely/not/a/database.sqlite")
    assert "password" not in str(error.value).lower()
