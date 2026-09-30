"""[Top N Tables] + [Question] -> [Table Selection Prompt] -> [LLM] -> [Top K Tables] (online)."""
import json
import os
import re

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser

from core.llm import make_chain
from prompts.schemas import TableChoice
from prompts.table_selection_prompt import TABLE_SELECTION_FALLBACK_PROMPT, TABLE_SELECTION_PROMPT


class TableSelector:
    def __init__(self, llm):
        self.parser = PydanticOutputParser(pydantic_object=TableChoice)
        self.fallback_chain = make_chain(TABLE_SELECTION_FALLBACK_PROMPT, llm)
        self.chain = (TABLE_SELECTION_PROMPT.partial(
            format_instructions=self.parser.get_format_instructions()) | llm | self.parser)

    def select(self, question: str, candidate_tables: list, table_summaries: dict, metadata_store,
               k: int | None = None) -> tuple[list, str]:
        if k is None:
            k = int(os.getenv("TOP_K", "3"))  # hyperparameter
        candidate_names = [candidate["name"] for candidate in candidate_tables]
        if len(candidate_names) <= 1:
            selection_reason = ("Only one candidate table was available." if candidate_names
                                else "No candidate tables were available.")
            return candidate_names, selection_reason

        candidates = "\n".join(
            f"- {table_name}: {table_summaries[table_name]}" for table_name in candidate_names)
        joins = metadata_store.joins_among(candidate_names)
        if joins:
            candidates += "\nJoin keys: " + "; ".join(joins)

        try:
            table_choice = self.chain.invoke({"question": question, "candidates": candidates, "k": k})
            selected_tables = [name for name in table_choice.tables if name in candidate_names][:k]
            if selected_tables:
                return selected_tables, table_choice.reason
        except OutputParserException:
            fallback_text = self.fallback_chain.invoke({
                "question": question,
                "candidates": candidates,
                "k": k,
            })
            json_list = re.search(r"\[.*?\]", fallback_text, re.S)
            if json_list:
                try:
                    selected_tables = [name for name in json.loads(json_list.group(0))
                                       if name in candidate_names][:k]
                except json.JSONDecodeError:
                    selected_tables = []
                if selected_tables:
                    return selected_tables, "Selected from the candidate summaries."
        return candidate_names[:k], "Selected the highest-ranked candidate tables."
