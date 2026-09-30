"""[Question] + [Top K Tables] + [Table Metadata Store] -> [Text2SQL Prompt] -> [LLM] -> [Generated SQL]."""
import re

from core.llm import make_chain
from prompts.schemas import SQLAnswer
from prompts.text2sql_prompt import DIALECT_RULES, TEXT2SQL_FALLBACK_PROMPT, TEXT2SQL_PROMPT

NO_ANSWER = "NO_ANSWER"


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
        self.fallback_chain = make_chain(TEXT2SQL_FALLBACK_PROMPT, llm)
        try:
            self.chain = TEXT2SQL_PROMPT | llm.with_structured_output(SQLAnswer)
            self.chain = self.chain.with_fallbacks([self.fallback_chain])
        except (AttributeError, NotImplementedError, TypeError):
            self.chain = self.fallback_chain

    def generate(self, question: str, schema: str, examples: str, dialect: str = "sqlite",
                 dataset_description: str = "") -> tuple[str, str]:
        rules = DIALECT_RULES.get(dialect, "Use standard SQL supported by this database dialect.")
        dataset_context = f"Dataset context: {dataset_description.strip()}\n" if dataset_description.strip() else ""
        reply = self.chain.invoke({"schema": schema, "examples": examples, "question": question,
                                   "dialect": dialect, "dialect_rules": rules,
                                   "dataset_context": dataset_context})
        if isinstance(reply, SQLAnswer):
            return (extract_sql(reply.sql) if reply.can_answer else NO_ANSWER), reply.explanation
        if isinstance(reply, dict):
            return (extract_sql(reply.get("sql", "")) if reply.get("can_answer") else NO_ANSWER,
                    reply.get("explanation", ""))
        return extract_sql(str(reply)), "Generated from the selected table schema and examples."
