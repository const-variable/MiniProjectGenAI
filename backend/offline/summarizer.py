"""[Summarization Prompt] -> [LLM] -> [Table/SQL Summary] (offline).

Produces the text that gets embedded:
  - one summary per table   (metadata + the logged queries that use it)
  - one description per logged SQL query
"""
import re

from core.llm import make_chain
from prompts.summarization_prompt import SQL_SUMMARY_PROMPT, TABLE_SUMMARY_PROMPT


class Summarizer:
    def __init__(self, llm):
        self.table_chain = make_chain(TABLE_SUMMARY_PROMPT, llm)
        self.sql_chain = make_chain(SQL_SUMMARY_PROMPT, llm)

    def summarise_queries(self, query_log: list) -> None:
        """Fill in query_log[i]['description'] with one LLM call for all queries."""
        if not query_log:
            return
        numbered = "\n\n".join(f"{i + 1}. {q['sql']}" for i, q in enumerate(query_log))
        try:
            text = self.sql_chain.invoke({"queries": numbered})
            for m in re.finditer(r"(?m)^\s*(\d+)[\.\)]\s*(.+)$", text):
                i = int(m.group(1)) - 1
                if 0 <= i < len(query_log) and not query_log[i]["description"]:
                    query_log[i]["description"] = m.group(2).strip()
        except Exception:
            pass
        for q in query_log:                                   # fallback if the LLM skipped one
            if not q["description"]:
                q["description"] = "Query on " + ", ".join(q["tables"])

    def summarise_table(self, table: str, metadata: str, query_log: list, fallback: str) -> str:
        queries = [q["sql"] for q in query_log if table in q["tables"]][:10]
        try:
            return self.table_chain.invoke({
                "metadata": metadata,
                "queries": "\n\n".join(queries) or "(no query logs provided)",
            }).strip()
        except Exception:
            return fallback
