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