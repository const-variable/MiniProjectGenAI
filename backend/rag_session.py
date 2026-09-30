"""One uploaded dataset = one TableRAGSession.

On creation it runs the OFFLINE pipeline once; each question runs the ONLINE pipeline.
"""
import re
import logging

from core.llm import make_chain
from offline.build_index import build_offline_index
from online.pipeline import OnlinePipeline
from extensions.answer_generator import frame_to_table_payload
from prompts.answer_prompt import OVERVIEW_PROMPT, SUGGEST_PROMPT

logger = logging.getLogger(__name__)


class TableRAGSession:
    def __init__(self, source, llm, embedding_model, notes: dict | None = None,
                 raw_queries: list | None = None, dataset_description: str = "",
                 on_progress=lambda stage, done, total: None):
        self.source = source
        self.dataset_description = dataset_description.strip()
        self.history: list[dict[str, str]] = []
        self.index = build_offline_index(
            source, llm, embedding_model, notes, raw_queries, self.dataset_description, on_progress)
        self.online = OnlinePipeline(llm, self.index, source)

        self._overview_chain = make_chain(OVERVIEW_PROMPT, llm)
        self._suggest_chain = make_chain(SUGGEST_PROMPT, llm)
        on_progress("Writing the dataset overview", 0, 1)
        try:
            self.summary = self._overview_chain.invoke({
                "profile": self.profile_text(),
                "dataset_description": self.dataset_description or "(not provided)",
            })
        except Exception as error:
            logger.warning("Dataset overview generation failed (%s)", type(error).__name__)
            tables = source.list_tables()
            self.summary = f"Loaded {len(tables)} table(s): " + ", ".join(
                f"{table} ({source.row_count(table)} rows)" for table in tables)
        self._suggestions = None

    def ask(self, question: str) -> dict:
        answer_payload = self.online.run(question, history=self.history[-3:])
        self.history.append({"question": question, "sql": answer_payload["sql"],
                     "answer": answer_payload["answer"][:300]})
        self.history = self.history[-3:]
        return answer_payload

    @property
    def query_log(self) -> list:
        return self.index.query_log

    def profile_text(self) -> str:
        dataset_profile = "\n\n".join(
            f'Table "{table}" ({self.source.row_count(table)} rows): {summary}'
            for table, summary in self.index.table_summaries.items())
        relationships = [f"{table_a}.{column_a} -> {table_b}.{column_b}"
                         for table_a, column_a, table_b, column_b in self.source.join_keys()]
        if relationships:
            dataset_profile += "\n\nRelationships: " + "; ".join(relationships)
        if self.dataset_description:
            dataset_profile = f"Dataset context: {self.dataset_description}\n\n{dataset_profile}"
        return dataset_profile

    def tables_info(self) -> list:
        column_types_by_table = self.index.metadata_store.types
        return [
            {
                "name": table,
                "rows": self.source.row_count(table),
                "summary": self.index.table_summaries[table],
                "example_questions": self.index.table_example_questions.get(table, []),
                "columns": [
                    {"name": column, "type": column_types_by_table[table][column]}
                    for column in self.source.columns(table)
                ],
            }
            for table in self.source.list_tables()
        ]

    def suggestions(self) -> list:
        if self._suggestions is None:
            try:
                suggestion_text = self._suggest_chain.invoke({"profile": self.profile_text()})
                suggestion_lines = [
                    re.sub(r"^[\s\-\*\d\.\)]+", "", line).strip()
                    for line in suggestion_text.splitlines()]
                self._suggestions = [line for line in suggestion_lines if line.endswith("?")][:4]
            except Exception as error:
                logger.warning("Question suggestion generation failed (%s)", type(error).__name__)
                self._suggestions = []
        return self._suggestions

    def preview(self, limit: int = 20) -> list:
        return [{"name": table, **frame_to_table_payload(self.source.preview(table, limit), limit)}
                for table in self.source.list_tables()]

    def close(self) -> None:
        self.history.clear()
        self.source.close()
