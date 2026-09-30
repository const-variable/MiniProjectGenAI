"""Prompts for steps beyond the reference diagram (EXTENSION).

The diagram stops at 'Generated SQL'. These prompts turn the executed result
into a plain-English answer, and produce the dataset overview and suggestions.
"""
from langchain_core.prompts import ChatPromptTemplate

ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You explain data query results to a non-technical user.\n"
     "- Use ONLY numbers that appear in the query result. Never invent or estimate numbers.\n"
     "- Give the direct answer first, then a 2-3 line summary of what the query result shows.\n"
     "- For 'why' questions, say which categories drove the change. The data shows WHAT changed, "
     "not real-world causes, so don't claim causes.\n"
     "- If the query result doesn't answer the question, say what is missing."),
    ("human", "Question: {question}\n\nSQL used:\n{sql}\n\nQuery result (CSV):\n{query_result}"),
])

OVERVIEW_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Write a 4-5 line plain-English overview of this dataset: what it is about, its size, "
               "time period and main categories. Use only the facts given. No bullet points."),
    ("human", "Dataset context: {dataset_description}\n\nDataset profile:\n{profile}"),
])

SUGGEST_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Suggest 4 short, useful questions a user could ask about this dataset. Each must be "
               "answerable from the tables given. One question per line, no numbering."),
    ("human", "{profile}"),
])

CONDENSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Rewrite the latest user question as one standalone question using the conversation "
               "turns when needed. Preserve its intent and time references. If it is already standalone, "
               "return it unchanged. Return only the rewritten question."),
    ("human", "Recent turns (oldest first):\n{history}\n\nLatest question: {question}"),
])
