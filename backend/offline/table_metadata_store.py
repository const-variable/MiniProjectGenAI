"""[Table Metadata Store] (red cylinder, right side).

Holds the full schema of every table: columns, types, ranges, category values.
In the diagram it feeds two places:
  - the Summarization Prompt (offline)
  - the Text2SQL Prompt (online), for the Top K tables only
"""
import pandas as pd

from core.loader import clean_name


def _format_number(number) -> str:
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def describe_column(column_name: str, column_values: pd.Series, column_type: str, note: str = "",
                    dialect: str = "sqlite", native_type: str = "") -> str:
    nonnull_values = column_values.dropna()
    if column_type == "number" and len(nonnull_values):
        description = (f"number; min {_format_number(nonnull_values.min())}, "
                       f"max {_format_number(nonnull_values.max())}, "
                       f"average {_format_number(nonnull_values.mean())}")
    elif column_type == "date" and len(nonnull_values):
        # Uploads store dates as TEXT in SQLite; real databases keep their native type.
        date_type = "TEXT 'YYYY-MM-DD'" if dialect == "sqlite" else (native_type or "DATE/TIMESTAMP")
        description = (f"date ({date_type}); from {nonnull_values.min().date()} "
                       f"to {nonnull_values.max().date()}")
    elif column_type == "category":
        value_counts = nonnull_values.astype(str).value_counts()
        truncated_note = f" (30 most common of {len(value_counts)})" if len(value_counts) > 30 else ""
        description = f"category; values{truncated_note}: {', '.join(value_counts.index[:30])}"
    else:
        description = (f"{column_type}; {nonnull_values.nunique()} distinct, "
                       f"e.g. {', '.join(nonnull_values.astype(str).head(3))}")
    missing_share = column_values.isna().mean()
    if missing_share:
        description += f"; {missing_share:.0%} missing"
    if note:
        description += f"; meaning: {note}"
    return f"{column_name}: {description}"


def parse_notes(text: str) -> dict:
    """User descriptions, one per line: 'column: meaning' or 'table.column: meaning'."""
    notes = {}
    for line in (text or "").splitlines():
        if ":" in line:
            column_key, meaning = line.split(":", 1)
            if meaning.strip():
                notes[clean_name(column_key)] = meaning.strip()
    return notes


class TableMetadataStore:
    def __init__(self, source, types: dict, notes: dict | None = None,
                 dataset_description: str = ""):
        notes = notes or {}
        self.source = source
        self.types = types
        self.metadata = {}
        for table in source.list_tables():
            frame = source.profile_frame(table)
            row_count = source.row_count(table)
            sample_note = (f" (stats from a sample of {len(frame):,} rows)"
                           if source.is_sampled(table) else "")
            lines = [f'Table "{table}" ({row_count:,} rows){sample_note}. Columns:']
            native_types = source.column_types(table)
            for column in frame.columns:
                note = notes.get(f"{table}_{column}") or notes.get(column, "")
                lines.append("- " + describe_column(
                    column, frame[column], types[table][column], note,
                    source.dialect, native_types.get(column, "")))
            self.metadata[table] = "\n".join(lines)
        self.join_keys = source.join_keys()
        self.dataset_description = dataset_description

    def get(self, table: str) -> str:
        return self.metadata[table]

    def joins_among(self, names: list) -> list:
        return [f"{table_a}.{column_a} = {table_b}.{column_b}"
                for table_a, column_a, table_b, column_b in self.join_keys
                if table_a in names and table_b in names]

    def schema_for(self, names: list) -> str:
        """Full metadata for the given tables: what the Text2SQL prompt receives."""
        schema_parts = [self.metadata[table] for table in names]
        joins = self.joins_among(names)
        if joins:
            schema_parts.append("Join keys: " + "; ".join(joins))
        return "\n\n".join(schema_parts)
