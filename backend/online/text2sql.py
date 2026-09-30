"""[Question] + [Top K Tables] + [Table Metadata Store] -> [Text2SQL Prompt] -> [LLM] -> [Generated SQL]."""
import re

from core.llm import make_chain
from extensions.sql_executor import NO_ANSWER
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser
from prompts.schemas import SQLAnswer
from prompts.text2sql_prompt import DIALECT_RULES, TEXT2SQL_FALLBACK_PROMPT, TEXT2SQL_PROMPT


def extract_sql(model_reply: str) -> str:
    fenced_sql = re.search(r"```(?:sql)?\s*(.*?)```", model_reply, re.S | re.I)
    return (fenced_sql.group(1) if fenced_sql else model_reply).strip().rstrip(";").strip()


def examples_text(similar_queries: list) -> str:
    if not similar_queries:
        return "(none)"
    return "\n\n".join(
        f"-- {query['description']}\n{query['sql']}" for query in similar_queries)


def dialect_context(dialect: str, dataset_description: str) -> dict:
    """Prompt variables shared by SQL generation and the SQL repair step."""
    description = dataset_description.strip()
    return {
        "dialect": dialect,
        "dialect_rules": DIALECT_RULES.get(dialect, "Use standard SQL supported by this database dialect."),
        "dataset_context": f"Dataset context: {description}\n" if description else "",
    }


class Text2SQL:
    def __init__(self, llm):
        self.parser = PydanticOutputParser(pydantic_object=SQLAnswer)
        self.fallback_chain = make_chain(TEXT2SQL_FALLBACK_PROMPT, llm)
        self.chain = (TEXT2SQL_PROMPT.partial(
            format_instructions=self.parser.get_format_instructions()) | llm | self.parser)

    def generate(self, question: str, schema: str, examples: str, dialect: str = "sqlite",
                 dataset_description: str = "") -> tuple[str, str]:
        prompt_values = {"schema": schema, "examples": examples, "question": question,
                         **dialect_context(dialect, dataset_description)}
        try:
            sql_answer = self.chain.invoke(prompt_values)
        except OutputParserException:
            fallback_sql = self.fallback_chain.invoke(prompt_values)
            return extract_sql(fallback_sql), "Generated from the selected table schema and examples."
        return (extract_sql(sql_answer.sql) if sql_answer.can_answer else NO_ANSWER), sql_answer.explanation
