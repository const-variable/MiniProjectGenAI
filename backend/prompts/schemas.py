"""Structured model outputs used by the online pipeline and table summarizer."""
from pydantic import BaseModel, Field


class TableChoice(BaseModel):
    tables: list[str] = Field(description="Tables needed, including join tables")
    reason: str = Field(description="One sentence: why these tables")


class SQLAnswer(BaseModel):
    can_answer: bool
    sql: str = Field(description="One read-only SELECT, empty if can_answer is false")
    explanation: str = Field(description="One sentence on what the query does")


class TableSummary(BaseModel):
    summary: str = Field(description="A concise 3-5 sentence summary of this table")
    example_questions: list[str] = Field(description="Five business questions this table helps answer")


class QueryDescription(BaseModel):
    query_number: int = Field(description="The 1-based position of this SQL query in the input")
    description: str = Field(description="A concise plain-English description of the query")


class QueryDescriptions(BaseModel):
    queries: list[QueryDescription]