"""[Top N Tables] + [Question] -> [Table Selection Prompt] -> [LLM] -> [Top K Tables] (online)."""
import os
import re

from core.llm import make_chain
from prompts.schemas import TableChoice
from prompts.table_selection_prompt import TABLE_SELECTION_FALLBACK_PROMPT, TABLE_SELECTION_PROMPT

K_SELECTED = int(os.getenv("TOP_K", "3"))


class TableSelector:
    def __init__(self, llm):
        self.fallback_chain = make_chain(TABLE_SELECTION_FALLBACK_PROMPT, llm)
        try:
            self.chain = TABLE_SELECTION_PROMPT | llm.with_structured_output(TableChoice)
            self.chain = self.chain.with_fallbacks([self.fallback_chain])
        except (AttributeError, NotImplementedError, TypeError):
            self.chain = self.fallback_chain

    def select(self, question: str, top_n: list, table_summaries: dict, metadata_store,
               k: int | None = None) -> tuple[list, str]:
        k = int(os.getenv("TOP_K", str(K_SELECTED))) if k is None else k
        names = [c["name"] for c in top_n]
        if len(names) <= 1:                       # nothing to choose between
            reason = "Only one candidate table was available." if names else "No candidate tables were available."
            return names, reason

        candidates = "\n".join(f"- {n}: {table_summaries[n]}" for n in names)
        joins = metadata_store.joins_among(names)
        if joins:
            candidates += "\nJoin keys: " + "; ".join(joins)

        try:
            output = self.chain.invoke({"question": question, "candidates": candidates, "k": k})
            if isinstance(output, TableChoice):
                picked, reason = output.tables, output.reason
            elif isinstance(output, dict):
                picked, reason = output.get("tables", []), output.get("reason", "")
            else:
                text = str(output)
                picked = []
                match = re.search(r"\[.*?\]", text, re.S)
                if match:
                    import json
                    try:
                        picked = [str(value) for value in json.loads(match.group(0))]
                    except json.JSONDecodeError:
                        pass
                if not picked:
                    picked = [name for name in names if re.search(rf"\b{re.escape(name)}\b", text)]
                reason = "Selected from the candidate summaries."
            picked = [p for p in picked if p in names][:k]
            if picked:
                return picked, reason or "Selected from the candidate summaries."
        except Exception:
            pass
        return names[:k], "Selected the highest-ranked candidate tables."  # retrieval fallback
