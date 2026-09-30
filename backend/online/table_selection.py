"""[Top N Tables] + [Question] -> [Table Selection Prompt] -> [LLM] -> [Top K Tables] (online)."""
import json
import re

from core.llm import make_chain
from prompts.table_selection_prompt import TABLE_SELECTION_PROMPT

K_SELECTED = 3


class TableSelector:
    def __init__(self, llm):
        self.chain = make_chain(TABLE_SELECTION_PROMPT, llm)

    def select(self, question: str, top_n: list, table_summaries: dict, metadata_store,
               k: int = K_SELECTED) -> list:
        names = [c["name"] for c in top_n]
        if len(names) <= 1:                       # nothing to choose between
            return names

        candidates = "\n".join(f"- {n}: {table_summaries[n]}" for n in names)
        joins = metadata_store.joins_among(names)
        if joins:
            candidates += "\nJoin keys: " + "; ".join(joins)

        try:
            text = self.chain.invoke({"question": question, "candidates": candidates, "k": k})
            picked = []
            m = re.search(r"\[.*?\]", text, re.S)
            if m:
                try:
                    picked = [str(p) for p in json.loads(m.group(0))]
                except json.JSONDecodeError:
                    pass
            if not picked:     # model ignored the JSON format: take table names it mentioned
                picked = [n for n in names if re.search(rf"\b{re.escape(n)}\b", text)]
            picked = [p for p in picked if p in names][:k]
            if picked:
                return picked
        except Exception:
            pass
        return names[:k]      # fallback: best-ranked tables from similarity search
