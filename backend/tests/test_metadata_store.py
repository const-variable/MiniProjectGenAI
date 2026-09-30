from core.loader import classify_columns
from offline.table_metadata_store import TableMetadataStore
from sources.upload_source import UploadSource


def test_metadata_notes_join_formatting_and_sample_annotation(monkeypatch):
    source = UploadSource([
        ("students.csv", b"student_id,name,score\n1,Ari,95\n2,Mina,88\n"),
        ("classes.csv", b"student_id,subject\n1,Math\n2,Science\n"),
    ])
    try:
        monkeypatch.setattr(source, "is_sampled", lambda table: table == "students")
        types = {table: classify_columns(source.profile_frame(table)) for table in source.list_tables()}
        metadata = TableMetadataStore(
            source,
            types,
            notes={"score": "exam mark", "students_student_id": "school identifier"},
        )
        assert metadata.dataset_description == ""
        assert "students.student_id = classes.student_id" in metadata.schema_for(source.list_tables())
        assert "school identifier" in metadata.get("students")
        assert "exam mark" in metadata.get("students")
        assert "stats from a sample of 2 rows" in metadata.get("students")
    finally:
        source.close()