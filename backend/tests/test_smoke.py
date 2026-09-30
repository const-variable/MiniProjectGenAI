from pathlib import Path

from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from rag_session import TableRAGSession
from sources.upload_source import UploadSource

ROOT = Path(__file__).resolve().parents[2]


def test_session_indexes_all_sample_tables_without_network():
    files = [(path.name, path.read_bytes()) for path in (ROOT / "sample_data").glob("*.csv")]
    source = UploadSource(files)
    session = TableRAGSession(
        source,
        FakeListChatModel(responses=["A sample table summary."]),
        DeterministicFakeEmbedding(size=64),
    )
    try:
        assert len(session.tables_info()) == 4
    finally:
        session.close()

def test_session_build_reports_each_stage_in_order():
    files = [(path.name, path.read_bytes()) for path in (ROOT / "sample_data").glob("*.csv")]
    progress_updates = []
    session = TableRAGSession(
        UploadSource(files),
        FakeListChatModel(responses=["A sample table summary."]),
        DeterministicFakeEmbedding(size=64),
        on_progress=lambda stage, done, total: progress_updates.append((stage, done, total)),
    )
    try:
        stages = list(dict.fromkeys(stage for stage, _, _ in progress_updates))
        assert stages == ["Profiling tables", "Summarising tables",
                          "Building the search index", "Writing the dataset overview"]
        summarised = [done for stage, done, _ in progress_updates if stage == "Summarising tables"]
        assert summarised == [0, 1, 2, 3, 4]
    finally:
        session.close()
