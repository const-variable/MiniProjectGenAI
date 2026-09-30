"""[Text2SQL Prompt] (online, green).

Inputs in the diagram: Data Analytical Question + Top K Tables + Table Metadata Store
(+ similar past queries retrieved from the vector store).
Output (after the LLM): Generated SQL.
"""
from langchain_core.prompts import ChatPromptTemplate

# Note: inside templates, { } marks a variable. Don't add other braces.
COMMON_SQL_RULES = """You write read-only SQL queries that answer questions about the tables below.
Rules:
- Write ONE read-only SELECT query (WITH ... SELECT is fine). Use only the tables and columns listed.
- Quote identifiers exactly as listed (case-sensitive).
- The query MUST read from the tables (FROM <table>). Never type the answer as literal values,
  and never answer from your own general knowledge: the answer must come from the data.
- Match category values exactly as they are listed. To search free-text columns, use
  LIKE with wildcards, e.g. WHERE LOWER(text_col) LIKE '%keyword%'.
- 'Latest', 'recent' or 'last quarter' mean the latest period present in the DATA, not today's date.
- For 'why did X change' questions: return X for the two latest periods, broken down by the most
  relevant category column, with a change column (latest minus previous), ordered by change.
- Return at most 50 rows. Round results to 2 decimals.

SQL dialect: {dialect}
Dialect-specific rules:
{dialect_rules}

{dataset_context}
Tables (from the Table Metadata Store):
{schema}

Similar past queries (use as patterns, adapt them to the question):
{examples}"""

DIALECT_RULES = {
    "sqlite": "Dates are TEXT 'YYYY-MM-DD'. Year: strftime('%Y', col). Month: strftime('%Y-%m', col). Quarter: strftime('%Y', col) || '-Q' || ((CAST(strftime('%m', col) AS INTEGER) + 2) / 3).",
    "postgresql": "Use date_trunc('quarter', col), EXTRACT(YEAR FROM col), to_char(col, 'YYYY-MM') and ILIKE for case-insensitive matching.",
}

TEXT2SQL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", COMMON_SQL_RULES + "\nIf the tables cannot answer, set can_answer to false and leave sql empty.\n"
     "Return a structured answer matching this format:\n{format_instructions}"),
    ("human", "{question}"),
])

TEXT2SQL_FALLBACK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", COMMON_SQL_RULES + "\n- If the tables cannot answer, reply exactly NO_ANSWER.\n"
     "- Output only the SQL inside ```sql fences."),
    ("human", "{question}"),
])

# Used by the graph's SQL repair node when a generated query fails.
FIX_SQL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", COMMON_SQL_RULES + "\nIf the tables cannot answer, reply exactly NO_ANSWER."),
    ("human", "{question}"),
    ("ai", "```sql\n{sql}\n```"),
    ("human", "That query failed with this error:\n{error}\nReturn a corrected query."),
])
