"""ONLINE TEXT2SQL: the bottom half of the diagram, step by step.

  Step 1  Data Analytical Question -> Embedding Model -> Question Embeddings
  Step 2  Similarity Search                          -> Top N Tables
  Step 3  Table Selection Prompt + LLM               -> Top K Tables
  Step 4  Text2SQL Prompt (+ Table Metadata Store)   -> LLM -> Generated SQL
  ---- extension beyond the diagram ----
  Step 5  Safety + grounding check, execute, retry   -> Query Result
  Step 6  Answer Prompt + LLM                        -> grounded answer
"""
from extensions.answer_generator import AnswerGenerator, df_to_json
from extensions.sql_executor import NO_ANSWER, SQLExecutor
from online.similarity_search import top_n_tables
from online.table_selection import TableSelector
from online.text2sql import Text2SQL, examples_text


class OnlinePipeline:
    def __init__(self, llm, index, data_store, tables: dict):
        self.index = index
        self.selector = TableSelector(llm)
        self.text2sql = Text2SQL(llm)
        self.executor = SQLExecutor(llm, data_store, tables)
        self.answerer = AnswerGenerator(llm)

    def run(self, question: str) -> dict:
        # Steps 1 + 2: question embedding -> similarity search -> Top N tables
        top_n, similar = top_n_tables(self.index.vector_store, self.index.query_log, question)

        # Step 3: Table Selection Prompt -> LLM -> Top K tables
        top_k = self.selector.select(question, top_n, self.index.table_summaries,
                                     self.index.metadata_store)

        # Step 4: Text2SQL Prompt (question + Top K metadata + similar past queries) -> Generated SQL
        schema = self.index.metadata_store.schema_for(top_k)
        examples = examples_text(similar)
        sql = self.text2sql.generate(question, schema, examples)

        # Step 5 (extension): check, execute, retry
        result, sql, error = self.executor.run_with_retry(question, sql, schema, examples)

        # Step 6 (extension): grounded answer
        if error == NO_ANSWER:
            answer = ("The uploaded data doesn't contain the information needed to answer this, "
                      "so I haven't answered from general knowledge.")
            sql = "-- no query: the data can't answer this question"
        elif error:
            answer = f"I couldn't calculate this from the data. The last error was: {error}"
        else:
            answer = self.answerer.generate(question, sql, result)

        return {
            "answer": answer,
            "sql": sql,
            "top_n_tables": top_n,
            "selected_tables": top_k,
            "similar_queries": [{"description": q["description"], "sql": q["sql"]} for q in similar],
            "result": df_to_json(result),
            "error": error,
        }
