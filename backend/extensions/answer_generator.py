"""EXTENSION: turn the query result into a grounded plain-English answer."""
import json

from core.llm import make_chain
from prompts.answer_prompt import ANSWER_PROMPT


def df_to_json(df, limit: int = 100) -> dict:
    """DataFrame -> {'columns': [...], 'rows': [[...]]}, with NaN turned into null."""
    if df is None:
        return {"columns": [], "rows": []}
    d = json.loads(df.head(limit).to_json(orient="split", index=False, date_format="iso"))
    return {"columns": [str(c) for c in d["columns"]], "rows": d["data"]}


class AnswerGenerator:
    def __init__(self, llm):
        self.chain = make_chain(ANSWER_PROMPT, llm)

    def generate(self, question: str, sql: str, result) -> str:
        shown = result.head(50).to_csv(index=False) if len(result) else "(no rows)"
        return self.chain.invoke({"question": question, "sql": sql, "result": shown})
