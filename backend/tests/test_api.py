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

    uploaded = client.post("/upload", files={"files": (sample.name, sample.read_bytes(), "text/csv")})
    assert uploaded.status_code == 200
    assert uploaded.json()["source"]["kind"] == "upload"

    database_url = f"sqlite:///{ROOT / 'sample_data' / 'chinook.sqlite'}"
    connected = client.post("/connect", data={"connection_url": database_url})
    assert connected.status_code == 200
    assert connected.json()["source"]["kind"] == "database"

    tested = client.post("/connect/test", data={"connection_url": database_url})
    assert tested.status_code == 200
    assert tested.json()["count"] == 11

    bad = client.post("/connect", data={"connection_url": "sqlite:///missing-file.db"})
    assert bad.status_code == 400
    assert "password" not in bad.json()["detail"].lower()