"""EXTENSION: turn the query result into a grounded plain-English answer."""
import json

from core.llm import make_chain
from prompts.answer_prompt import ANSWER_PROMPT


def frame_to_table_payload(query_frame, row_limit: int = 100) -> dict:
    if query_frame is None:
        return {"columns": [], "rows": []}
    table_payload = json.loads(
        query_frame.head(row_limit).to_json(orient="split", index=False, date_format="iso"))
    return {"columns": [str(column) for column in table_payload["columns"]],
            "rows": table_payload["data"]}


class AnswerGenerator:
    def __init__(self, llm):
        self.chain = make_chain(ANSWER_PROMPT, llm)

    def generate(self, question: str, sql: str, query_result) -> str:
        query_result_csv = query_result.head(50).to_csv(index=False) if len(query_result) else "(no rows)"
        return self.chain.invoke({
            "question": question,
            "sql": sql,
            "query_result": query_result_csv,
        })
