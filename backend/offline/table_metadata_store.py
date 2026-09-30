"""[Table Metadata Store] (red cylinder, right side).

Holds the full schema of every table: columns, types, ranges, category values.
In the diagram it feeds two places:
  - the Summarization Prompt (offline)
  - the Text2SQL Prompt (online), for the Top K tables only
"""
import pandas as pd

from core.loader import clean_name


def _fmt(x) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def describe_column(col: str, s: pd.Series, ctype: str, note: str = "",
                    dialect: str = "sqlite", native_type: str = "") -> str:
    nonnull = s.dropna()
    if ctype == "number" and len(nonnull):
        body = (f"number; min {_fmt(nonnull.min())}, max {_fmt(nonnull.max())}, "
                f"average {_fmt(nonnull.mean())}")
    elif ctype == "date" and len(nonnull):
        date_type = "TEXT 'YYYY-MM-DD'" if dialect == "sqlite" else (native_type or "DATE/TIMESTAMP")
        body = f"date ({date_type}); from {nonnull.min().date()} to {nonnull.max().date()}"
    elif ctype == "category":
        counts = nonnull.astype(str).value_counts()
        more = f" (30 most common of {len(counts)})" if len(counts) > 30 else ""
        body = f"category; values{more}: {', '.join(counts.index[:30])}"
    else:
        body = f"{ctype}; {nonnull.nunique()} distinct, e.g. {', '.join(nonnull.astype(str).head(3))}"
    missing = s.isna().mean()
    if missing:
        body += f"; {missing:.0%} missing"
    if note:
        body += f"; meaning: {note}"
    return f"{col}: {body}"


def parse_notes(text: str) -> dict:
    """User descriptions, one per line: 'column: meaning' or 'table.column: meaning'."""
    notes = {}
    for line in (text or "").splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            if val.strip():
                notes[clean_name(key)] = val.strip()
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
        parts = [self.metadata[t] for t in names]
        joins = self.joins_among(names)
        if joins:
            parts.append("Join keys: " + "; ".join(joins))
        return "\n\n".join(parts)
