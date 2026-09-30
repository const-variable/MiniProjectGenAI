"""[Table Selection Prompt] (online, green).

Inputs in the diagram: Data Analytical Question + Top N Tables.
Output (after the LLM): Top K Tables.
"""
from langchain_core.prompts import ChatPromptTemplate

# Note: inside templates, { } marks a variable. Don't add other braces.
TABLE_SELECTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You pick the tables needed to answer a question. Choose at most {k} tables from the "
     "candidates, including any table needed for a join. Reply with only a JSON list of table "
     "names, for example [\"orders\", \"products\"]."),
    ("human", "Question: {question}\n\nCandidate tables:\n{candidates}"),
])
