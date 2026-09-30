import os
from pathlib import Path

os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("LLM_MODEL", "llama-3.3-70b-versatile")

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

    def ask(self, question):
        return {
            "answer": f"Answered: {question}",
            "sql": "SELECT 1",
            "top_n_tables": [],
            "selected_tables": [],
            "similar_queries": [],
            "result": {"columns": ["answer"], "rows": [[1]]},
        }

    def suggestions(self):
        return ["How many rows are there?"]

    def preview(self):
        return []

    def close(self):
        self.source.close()


def test_upload_and_connect_api(monkeypatch):
    monkeypatch.setattr(main, "TableRAGSession", FakeSession)
    monkeypatch.setitem(main.models, "llm", object())
    monkeypatch.setitem(main.models, "embeddings", object())
    client = TestClient(main.app)
    sample = ROOT / "sample_data" / "orders.csv"
    assert client.get("/health").json() == {"status": "ok"}

    uploaded = client.post(
        "/upload",
        data={"dataset_description": "School enrollment and assessment data."},
        files={"files": (sample.name, sample.read_bytes(), "text/csv")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["source"]["kind"] == "upload"
    assert FakeSession.last_dataset_description == "School enrollment and assessment data."
    session_id = uploaded.json()["session_id"]
    assert client.get(f"/session/{session_id}").status_code == 200
    assert client.post("/ask", json={"session_id": session_id, "question": "Count rows"}).status_code == 200
    assert client.get(f"/suggestions/{session_id}").json()["questions"]
    assert client.get(f"/preview/{session_id}").json() == {"tables": []}
    assert client.delete(f"/session/{session_id}").json() == {"deleted": True}
    assert client.get(f"/session/{session_id}").status_code == 404

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
    assert client.delete(f"/session/{excel_upload.json()['session_id']}").json() == {"deleted": True}

    database_url = f"sqlite:///{ROOT / 'sample_data' / 'chinook.sqlite'}"
    connected = client.post("/connect", data={
        "connection_url": database_url,
        "dataset_description": "Music sales records.",
    })
    assert connected.status_code == 200
    assert connected.json()["source"]["kind"] == "database"
    assert FakeSession.last_dataset_description == "Music sales records."
    assert client.delete(f"/session/{connected.json()['session_id']}").json() == {"deleted": True}

    tested = client.post("/connect/test", data={"connection_url": database_url})
    assert tested.status_code == 200
    assert tested.json()["count"] == 11

    bad = client.post("/connect", data={"connection_url": "sqlite:///missing-file.db"})
    assert bad.status_code == 400
    assert "password" not in bad.json()["detail"].lower()
    assert client.get("/session/unknown-session").status_code == 404


def test_ask_errors_do_not_return_exception_details(monkeypatch):
    class BrokenSession:
        def ask(self, _question):
            raise RuntimeError("provider internals and secret value")

    monkeypatch.setattr(main, "get_session", lambda _session_id: BrokenSession())
    client = TestClient(main.app)

    monkeypatch.setattr(main, "is_llm_provider_error", lambda _error: True)
    provider_response = client.post("/ask", json={"session_id": "s", "question": "q"})
    assert provider_response.status_code == 502
    assert "GROQ_API_KEY" in provider_response.json()["detail"]
    assert "secret value" not in provider_response.text

    monkeypatch.setattr(main, "is_llm_provider_error", lambda _error: False)
    internal_response = client.post("/ask", json={"session_id": "s", "question": "q"})
    assert internal_response.status_code == 500
    assert "provider internals" not in internal_response.text


def test_upload_limits_return_http_400(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setenv("MAX_TABLES_PER_UPLOAD", "1")
    too_many_files = client.post("/upload", files=[
        ("files", ("one.csv", b"id,value\n1,a\n", "text/csv")),
        ("files", ("two.csv", b"id,value\n2,b\n", "text/csv")),
    ])
    assert too_many_files.status_code == 400

    monkeypatch.setenv("MAX_ROWS_PER_TABLE", "1")
    too_many_rows = client.post("/upload", files={
        "files": ("large.csv", b"id,value\n1,a\n2,b\n", "text/csv")
    })
    assert too_many_rows.status_code == 400
    assert "maximum is 1 rows" in too_many_rows.json()["detail"]