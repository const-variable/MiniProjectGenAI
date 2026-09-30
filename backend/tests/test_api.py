import os
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "groq")
os.environ.setdefault("LLM_MODEL", "openai/gpt-oss-120b")

from fastapi.testclient import TestClient

import main

ROOT = Path(__file__).resolve().parents[2]


class FakeSession:
    def __init__(self, source, *_args, **_kwargs):
        self.source = source
        type(self).last_dataset_description = _kwargs.get("dataset_description", "")
        self.summary = "Test dataset"
        self.query_log = []

    def tables_info(self):
        return [{"name": table, "rows": self.source.row_count(table), "summary": "test",
                 "columns": [{"name": column, "type": "text"}
                             for column in self.source.columns(table)]}
                for table in self.source.list_tables()]

    def close(self):
        self.source.close()


def test_upload_and_connect_api(monkeypatch):
    monkeypatch.setattr(main, "TableRAGSession", FakeSession)
    monkeypatch.setitem(main.models, "llm", object())
    monkeypatch.setitem(main.models, "embeddings", object())
    client = TestClient(main.app)
    sample = ROOT / "sample_data" / "orders.csv"

    uploaded = client.post(
        "/upload",
        data={"dataset_description": "School enrollment and assessment data."},
        files={"files": (sample.name, sample.read_bytes(), "text/csv")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["source"]["kind"] == "upload"
    assert FakeSession.last_dataset_description == "School enrollment and assessment data."

    workbook = ROOT / "sample_data" / "school.xlsx"
    excel_upload = client.post(
        "/upload",
        files={"files": (workbook.name, workbook.read_bytes(),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert excel_upload.status_code == 200
    assert [table["name"] for table in excel_upload.json()["tables"]] == [
        "school_students", "school_scores"]
    assert excel_upload.json()["relationships"] == [{
        "table_a": "school_students", "column_a": "student_id",
        "table_b": "school_scores", "column_b": "student_id",
    }]

    database_url = f"sqlite:///{ROOT / 'sample_data' / 'chinook.sqlite'}"
    connected = client.post("/connect", data={
        "connection_url": database_url,
        "dataset_description": "Music sales records.",
    })
    assert connected.status_code == 200
    assert connected.json()["source"]["kind"] == "database"
    assert FakeSession.last_dataset_description == "Music sales records."

    tested = client.post("/connect/test", data={"connection_url": database_url})
    assert tested.status_code == 200
    assert tested.json()["count"] == 11

    bad = client.post("/connect", data={"connection_url": "sqlite:///missing-file.db"})
    assert bad.status_code == 400
    assert "password" not in bad.json()["detail"].lower()