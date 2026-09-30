"""[Summarization Prompt] (offline, green).

Inputs in the diagram: SQL Query Logs + Table Metadata Store.
Output (after the LLM): Table/SQL Summary.
"""
from langchain_core.prompts import ChatPromptTemplate

# One summary per table, built from its metadata and the logged queries that use it.
TABLE_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You summarise one database table for a search index. In 3-5 sentences, say what the table "
     "contains, what its important columns mean, and which kinds of questions it can answer. "
     "If example queries are given, also describe how the table is typically queried. "
     "Use only the information given."),
    ("human", "Table metadata:\n{metadata}\n\nExample queries that use this table:\n{queries}"),
])

# One plain-English line per logged SQL query (all queries in a single call).
SQL_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "For each numbered SQL query, write one short plain-English line describing the question it "
     "answers. Reply with exactly one line per query, formatted as '<number>. <description>'."),
    ("human", "{queries}"),
])
