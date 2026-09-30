"""One uploaded dataset = one TableRAGSession.

On creation it runs the OFFLINE pipeline once; each question runs the ONLINE pipeline.
"""
import re

from core.llm import make_chain
from offline.build_index import build_offline_index
from online.pipeline import OnlinePipeline
from extensions.answer_generator import df_to_json
from prompts.answer_prompt import OVERVIEW_PROMPT, SUGGEST_PROMPT


class TableRAGSession:
    def __init__(self, source, llm, embedding_model, notes: dict | None = None,
                 raw_queries: list | None = None):
        self.source = source
        self.index = build_offline_index(source, llm, embedding_model,        # OFFLINE
                                         notes, raw_queries)
        self.online = OnlinePipeline(llm, self.index, source)                 # ONLINE

        self._overview_chain = make_chain(OVERVIEW_PROMPT, llm)
        self._suggest_chain = make_chain(SUGGEST_PROMPT, llm)
        try:
            self.summary = self._overview_chain.invoke({"profile": self.profile_text()})
        except Exception:
            tables = source.list_tables()
            self.summary = f"Loaded {len(tables)} table(s): " + ", ".join(
                f"{table} ({source.row_count(table)} rows)" for table in tables)
        self._suggestions = None

    # -------------------------------------------------------------- questions
    def ask(self, question: str) -> dict:
        return self.online.run(question)

    # -------------------------------------------------------------- info for the UI
    @property
    def query_log(self) -> list:
        return self.index.query_log

    def profile_text(self) -> str:
        return "\n\n".join(f'Table "{table}" ({self.source.row_count(table)} rows): {summary}'
                   for table, summary in self.index.table_summaries.items())

    def tables_info(self) -> list:
        types = self.index.metadata_store.types
        return [{"name": table, "rows": self.source.row_count(table),
             "summary": self.index.table_summaries[table],
             "columns": [{"name": column, "type": types[table][column]}
                     for column in self.source.columns(table)]}
            for table in self.source.list_tables()]

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
        return [{"name": table, **df_to_json(self.source.preview(table, limit), limit)}
                for table in self.source.list_tables()]

    def close(self) -> None:
        self.source.close()
