"""[Summarization Prompt] -> [LLM] -> [Table/SQL Summary] (offline).

Produces the text that gets embedded:
  - one summary per table   (metadata + the logged queries that use it)
  - one description per logged SQL query
"""
import re

from core.llm import make_chain
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser
from prompts.schemas import QueryDescriptions, TableSummary
from prompts.summarization_prompt import (
    SQL_SUMMARY_PROMPT,
    SQL_SUMMARY_STRUCTURED_PROMPT,
    TABLE_SUMMARY_FALLBACK_PROMPT,
    TABLE_SUMMARY_PROMPT,
)


class Summarizer:
    def __init__(self, llm):
        self.table_fallback_chain = make_chain(TABLE_SUMMARY_FALLBACK_PROMPT, llm)
        self.table_parser = PydanticOutputParser(pydantic_object=TableSummary)
        self.table_chain = (TABLE_SUMMARY_PROMPT.partial(
            format_instructions=self.table_parser.get_format_instructions()) | llm | self.table_parser)
        self.sql_fallback_chain = make_chain(SQL_SUMMARY_PROMPT, llm)
        self.query_parser = PydanticOutputParser(pydantic_object=QueryDescriptions)
        self.sql_chain = (SQL_SUMMARY_STRUCTURED_PROMPT.partial(
            format_instructions=self.query_parser.get_format_instructions()) | llm | self.query_parser)

    def summarise_queries(self, query_log: list) -> None:
        """Fill in query_log[i]['description'] with one LLM call for all queries."""
        if not query_log:
            return
        numbered = "\n\n".join(
            f"{query_number}. {query['sql']}"
            for query_number, query in enumerate(query_log, start=1))
        try:
            query_descriptions = self.sql_chain.invoke({"queries": numbered})
        except OutputParserException:
            fallback_descriptions = self.sql_fallback_chain.invoke({"queries": numbered})
            self._apply_text_descriptions(fallback_descriptions, query_log)
        else:
            for description in query_descriptions.queries:
                query_index = description.query_number - 1
                if 0 <= query_index < len(query_log):
                    query_log[query_index]["description"] = description.description.strip()
        for query in query_log:
            if not query["description"]:
                query["description"] = "Query on " + ", ".join(query["tables"])

    def summarise_tables(self, summary_inputs: list[dict],
                         on_table_done=lambda: None) -> list[TableSummary]:
        table_summaries = [None] * len(summary_inputs)
        # as_completed (not batch) so progress can be reported per finished table.
        for input_index, summary in self.table_chain.batch_as_completed(
                summary_inputs, config={"max_concurrency": 5},  # hyperparameter
                return_exceptions=True):
            if isinstance(summary, OutputParserException):
                # Malformed JSON: ask again for plain text, without example questions.
                summary = TableSummary(
                    summary=self.table_fallback_chain.invoke(summary_inputs[input_index]),
                    example_questions=[])
            elif isinstance(summary, Exception):
                raise summary
            table_summaries[input_index] = summary
            on_table_done()
        return table_summaries

    @staticmethod
    def _apply_text_descriptions(fallback_descriptions: str, query_log: list) -> None:
        pattern = r"(?m)^\s*(\d+)[\.\)]\s*(.+)$"
        for description_match in re.finditer(pattern, fallback_descriptions):
            query_index = int(description_match.group(1)) - 1
            if 0 <= query_index < len(query_log) and not query_log[query_index]["description"]:
                query_log[query_index]["description"] = description_match.group(2).strip()
