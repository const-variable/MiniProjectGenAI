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


def describe_column(col: str, s: pd.Series, ctype: str, note: str = "") -> str:
    nonnull = s.dropna()
    if ctype == "number" and len(nonnull):
        body = (f"number; min {_fmt(nonnull.min())}, max {_fmt(nonnull.max())}, "
                f"average {_fmt(nonnull.mean())}")
    elif ctype == "date" and len(nonnull):
        body = f"date (TEXT 'YYYY-MM-DD'); from {nonnull.min().date()} to {nonnull.max().date()}"
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
    def __init__(self, tables: dict, types: dict, notes: dict | None = None):
        notes = notes or {}
        self.tables = tables
        self.types = types
        self.metadata = {}
        for t, df in tables.items():
            lines = [f'Table "{t}" ({len(df)} rows). Columns:']
            for c in df.columns:
                note = notes.get(f"{t}_{c}") or notes.get(c, "")
                lines.append("- " + describe_column(c, df[c], types[t][c], note))
            self.metadata[t] = "\n".join(lines)

        # join keys: the same column name in two tables
        self.join_keys, names = [], list(tables)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                for c in sorted(set(tables[a].columns) & set(tables[b].columns)):
                    self.join_keys.append((a, b, c))

    def get(self, table: str) -> str:
        return self.metadata[table]

    def joins_among(self, names: list) -> list:
        return [f"{a}.{c} = {b}.{c}" for a, b, c in self.join_keys if a in names and b in names]

    def schema_for(self, names: list) -> str:
        """Full metadata for the given tables: what the Text2SQL prompt receives."""
        parts = [self.metadata[t] for t in names]
        joins = self.joins_among(names)
        if joins:
            parts.append("Join keys: " + "; ".join(joins))
        return "\n\n".join(parts)
