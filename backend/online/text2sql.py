"""[Question] + [Top K Tables] + [Table Metadata Store] -> [Text2SQL Prompt] -> [LLM] -> [Generated SQL]."""
import re

from core.llm import make_chain
from prompts.text2sql_prompt import DIALECT_RULES, TEXT2SQL_PROMPT


def extract_sql(text: str) -> str:
    """Take the SQL out of the LLM's reply (it is asked to use ```sql fences)."""
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip().rstrip(";").strip()


def examples_text(similar_queries: list) -> str:
    if not similar_queries:
        return "(none)"
    return "\n\n".join(f"-- {q['description']}\n{q['sql']}" for q in similar_queries)


class Text2SQL:
    def __init__(self, llm):
        self.chain = make_chain(TEXT2SQL_PROMPT, llm)

    def generate(self, question: str, schema: str, examples: str, dialect: str = "sqlite") -> str:
        rules = DIALECT_RULES.get(dialect, "Use standard SQL supported by this database dialect.")
        reply = self.chain.invoke({"schema": schema, "examples": examples, "question": question,
                                   "dialect": dialect, "dialect_rules": rules})
        return extract_sql(reply)
