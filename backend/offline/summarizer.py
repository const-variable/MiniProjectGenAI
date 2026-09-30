"""[Summarization Prompt] -> [LLM] -> [Table/SQL Summary] (offline).

Produces the text that gets embedded:
  - one summary per table   (metadata + the logged queries that use it)
  - one description per logged SQL query
"""
import logging
import re

from core.llm import make_chain
from prompts.schemas import QueryDescriptions, TableSummary
from prompts.summarization_prompt import (
    SQL_SUMMARY_PROMPT,
    SQL_SUMMARY_STRUCTURED_PROMPT,
    TABLE_SUMMARY_FALLBACK_PROMPT,
    TABLE_SUMMARY_PROMPT,
)

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, llm):
        self.table_fallback_chain = make_chain(TABLE_SUMMARY_FALLBACK_PROMPT, llm)
        try:
            self.table_chain = TABLE_SUMMARY_PROMPT | llm.with_structured_output(TableSummary)
            self.table_chain = self.table_chain.with_fallbacks([self.table_fallback_chain])
        except (AttributeError, NotImplementedError, TypeError):
            self.table_chain = self.table_fallback_chain
        self.sql_fallback_chain = make_chain(SQL_SUMMARY_PROMPT, llm)
        try:
            self.sql_chain = SQL_SUMMARY_STRUCTURED_PROMPT | llm.with_structured_output(QueryDescriptions)
            self.sql_chain = self.sql_chain.with_fallbacks([self.sql_fallback_chain])
        except (AttributeError, NotImplementedError, TypeError):
            self.sql_chain = self.sql_fallback_chain

    def summarise_queries(self, query_log: list) -> None:
        """Fill in query_log[i]['description'] with one LLM call for all queries."""
        if not query_log:
            return
        numbered = "\n\n".join(f"{i + 1}. {query['sql']}" for i, query in enumerate(query_log))
        try:
            output = self.sql_chain.invoke({"queries": numbered})
            if isinstance(output, QueryDescriptions):
                for item in output.queries:
                    index = item.index - 1
                    if 0 <= index < len(query_log):
                        query_log[index]["description"] = item.description.strip()
            elif isinstance(output, dict) and isinstance(output.get("queries"), list):
                for item in output["queries"]:
                    index = int(item["index"]) - 1
                    if 0 <= index < len(query_log):
                        query_log[index]["description"] = str(item["description"]).strip()
            else:
                self._apply_text_descriptions(str(output), query_log)
        except Exception as error:
            logger.warning("SQL query summarization failed (%s); using table names", type(error).__name__)
        for query in query_log:
            if not query["description"]:
                query["description"] = "Query on " + ", ".join(query["tables"])

    @staticmethod
    def _apply_text_descriptions(text: str, query_log: list) -> None:
        for match in re.finditer(r"(?m)^\s*(\d+)[\.\)]\s*(.+)$", text):
            index = int(match.group(1)) - 1
            if 0 <= index < len(query_log) and not query_log[index]["description"]:
                query_log[index]["description"] = match.group(2).strip()
