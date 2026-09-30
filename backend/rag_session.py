"""One uploaded dataset = one TableRAGSession.

On creation it runs the OFFLINE pipeline once; each question runs the ONLINE pipeline.
"""
import re

from core.data_store import DataStore
from core.llm import make_chain
from offline.build_index import build_offline_index
from online.pipeline import OnlinePipeline
from extensions.answer_generator import df_to_json
from prompts.answer_prompt import OVERVIEW_PROMPT, SUGGEST_PROMPT


class TableRAGSession:
    def __init__(self, tables: dict, llm, embedding_model, notes: dict | None = None,
                 raw_queries: list | None = None):
        self.tables = tables
        self.data_store = DataStore(tables)                                   # the rows, for SQL
        self.index = build_offline_index(tables, llm, embedding_model,        # OFFLINE
                                         notes, raw_queries)
        self.online = OnlinePipeline(llm, self.index, self.data_store, tables)  # ONLINE

        self._overview_chain = make_chain(OVERVIEW_PROMPT, llm)
        self._suggest_chain = make_chain(SUGGEST_PROMPT, llm)
        try:
            self.summary = self._overview_chain.invoke({"profile": self.profile_text()})
        except Exception:
            self.summary = f"Loaded {len(tables)} table(s): " + ", ".join(
                f"{t} ({len(df)} rows)" for t, df in tables.items())
        self._suggestions = None

    # -------------------------------------------------------------- questions
    def ask(self, question: str) -> dict:
        return self.online.run(question)

    # -------------------------------------------------------------- info for the UI
    @property
    def query_log(self) -> list:
        return self.index.query_log

    def profile_text(self) -> str:
        return "\n\n".join(f'Table "{t}" ({len(self.tables[t])} rows): {s}'
                           for t, s in self.index.table_summaries.items())

    def tables_info(self) -> list:
        types = self.index.metadata_store.types
        return [{"name": t, "rows": int(len(df)), "summary": self.index.table_summaries[t],
                 "columns": [{"name": c, "type": types[t][c]} for c in df.columns]}
                for t, df in self.tables.items()]

    def suggestions(self) -> list:
        if self._suggestions is None:
            try:
                text = self._suggest_chain.invoke({"profile": self.profile_text()})
                lines = [re.sub(r"^[\s\-\*\d\.\)]+", "", ln).strip() for ln in text.splitlines()]
                self._suggestions = [ln for ln in lines if ln.endswith("?")][:4]
            except Exception:
                self._suggestions = []
        return self._suggestions

    def preview(self, limit: int = 20) -> list:
        return [{"name": t, **df_to_json(self.data_store.query(f'SELECT * FROM "{t}" LIMIT {int(limit)}'), limit)}
                for t in self.tables]
