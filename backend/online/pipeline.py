"""ONLINE TEXT2SQL represented as a named LangGraph state machine.

  Step 1  Data Analytical Question -> Embedding Model -> Question Embeddings
  Step 2  Similarity Search                          -> Top N Tables
  Step 3  Table Selection Prompt + LLM               -> Top K Tables
  Step 4  Text2SQL Prompt (+ Table Metadata Store)   -> LLM -> Generated SQL
  ---- extension beyond the diagram ----
  Step 5  Safety + grounding check, execute, retry   -> Query Result
  Step 6  Answer Prompt + LLM                        -> grounded answer
"""
import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from core.llm import make_chain
from extensions.answer_generator import AnswerGenerator, df_to_json
from extensions.sql_executor import MAX_RETRIES, NO_ANSWER, SQLExecutor, is_no_answer
from online.similarity_search import top_n_tables
from online.table_selection import TableSelector
from online.text2sql import Text2SQL, examples_text, extract_sql
from prompts.answer_prompt import CONDENSE_PROMPT
from prompts.text2sql_prompt import DIALECT_RULES, FIX_SQL_PROMPT

logger = logging.getLogger(__name__)


class PipelineState(TypedDict, total=False):
    question: str
    top_n: list[dict]
    similar: list[dict]
    top_k: list[str]
    selection_reason: str
    schema: str
    examples: str
    sql: str
    sql_explanation: str
    result: Any
    error: str | None
    attempts: int
    answer: str
    score_kind: str
    tables_override: list[str] | None
    history: list[dict]
    standalone_question: str


class OnlinePipeline:
    def __init__(self, llm, index, source):
        self.index = index
        self.source = source
        self.selector = TableSelector(llm)
        self.text2sql = Text2SQL(llm)
        self.dataset_description = getattr(index.metadata_store, "dataset_description", "")
        self.executor = SQLExecutor(source)
        self.fix_chain = make_chain(FIX_SQL_PROMPT, llm)
        self.condense_chain = make_chain(CONDENSE_PROMPT, llm)
        self.answerer = AnswerGenerator(llm)
        self.graph = self._build_graph()
        self.last_state: PipelineState = {}

    def _build_graph(self):
        graph = StateGraph(PipelineState)
        graph.add_node("condense", self.condense)
        graph.add_node("retrieve", self.retrieve)
        graph.add_node("select_tables", self.select_tables)
        graph.add_node("generate_sql", self.generate_sql)
        graph.add_node("check_and_execute", self.check_and_execute)
        graph.add_node("fix_sql", self.fix_sql)
        graph.add_node("answer", self.answer)
        graph.add_conditional_edges(START, self.start_route, {
            "condense": "condense",
            "retrieve": "retrieve",
            "generate_sql": "generate_sql",
        })
        graph.add_conditional_edges("condense", self.after_condense_route, {
            "retrieve": "retrieve",
            "generate_sql": "generate_sql",
        })
        graph.add_edge("retrieve", "select_tables")
        graph.add_edge("select_tables", "generate_sql")
        graph.add_edge("generate_sql", "check_and_execute")
        graph.add_conditional_edges("check_and_execute", self.execution_route, {
            "answer": "answer",
            "fix_sql": "fix_sql",
        })
        graph.add_edge("fix_sql", "check_and_execute")
        graph.add_edge("answer", END)
        return graph.compile()

    @staticmethod
    def start_route(state: PipelineState) -> str:
        if state.get("history"):
            return "condense"
        return "generate_sql" if state.get("tables_override") is not None else "retrieve"

    @staticmethod
    def after_condense_route(state: PipelineState) -> str:
        return "generate_sql" if state.get("tables_override") is not None else "retrieve"

    def condense(self, state: PipelineState) -> dict:
        turns = state.get("history", [])[-3:]
        history_text = "\n".join(
            f"User: {turn['question']}\nSQL: {turn['sql']}\nAssistant: {turn['answer']}"
            for turn in turns)
        try:
            standalone = self.condense_chain.invoke({
                "history": history_text,
                "question": state["question"],
            }).strip()
        except Exception as error:
            logger.warning("Follow-up question condensation failed (%s)", type(error).__name__)
            standalone = state["question"]
        return {"standalone_question": standalone or state["question"]}

    @staticmethod
    def execution_route(state: PipelineState) -> str:
        error = state.get("error")
        if not error or error == NO_ANSWER or state.get("attempts", 0) >= MAX_RETRIES:
            return "answer"
        return "fix_sql"

    def retrieve(self, state: PipelineState) -> dict:
        # Steps 1 + 2: question embedding -> similarity search -> Top N tables
        top_n, similar, score_kind = top_n_tables(
            self.index.vector_store, self.index.query_log, self.effective_question(state))
        return {"top_n": top_n, "similar": similar, "score_kind": score_kind}

    def select_tables(self, state: PipelineState) -> dict:
        # Step 3: Table Selection Prompt -> LLM -> Top K tables
        top_k, reason = self.selector.select(
            self.effective_question(state), state.get("top_n", []), self.index.table_summaries,
            self.index.metadata_store)
        return {"top_k": top_k, "selection_reason": reason}

    def generate_sql(self, state: PipelineState) -> dict:
        # Step 4: Text2SQL Prompt (question + Top K metadata + similar queries) -> SQL
        top_k = state.get("top_k")
        if top_k is None:
            top_k = state.get("tables_override") or []
        similar = state.get("similar", [])
        schema = self.index.metadata_store.schema_for(top_k)
        examples = examples_text(similar)
        sql, explanation = self.text2sql.generate(
            self.effective_question(state), schema, examples, self.source.dialect,
            self.dataset_description)
        if state.get("tables_override") is not None and "selection_reason" not in state:
            reason = "Table selection bypassed using the explicit table override."
        else:
            reason = state.get("selection_reason", "")
        return {"top_k": top_k, "schema": schema, "examples": examples,
                "sql": sql, "sql_explanation": explanation,
                "selection_reason": reason}

    @staticmethod
    def effective_question(state: PipelineState) -> str:
        return state.get("standalone_question") or state["question"]

    def check_and_execute(self, state: PipelineState) -> dict:
        # Step 5: safety + grounding checks and query execution
        if is_no_answer(state.get("sql", "")):
            return {"result": None, "error": NO_ANSWER}
        try:
            return {"result": self.executor.run(state["sql"]), "error": None}
        except Exception as error:
            logger.warning("SQL check or execution failed (%s)", type(error).__name__)
            return {"result": None, "error": str(error)}

    def fix_sql(self, state: PipelineState) -> dict:
        # Step 5b: repair SQL and return to the execution guard
        rules = DIALECT_RULES.get(
            self.source.dialect, "Use standard SQL supported by this database dialect.")
        reply = self.fix_chain.invoke({
            "schema": state.get("schema", ""),
            "examples": state.get("examples", "(none)"),
            "question": self.effective_question(state),
            "sql": state.get("sql", ""),
            "error": state.get("error", ""),
            "dialect": self.source.dialect,
            "dialect_rules": rules,
            "dataset_context": (f"Dataset context: {self.dataset_description.strip()}\n"
                                if self.dataset_description.strip() else ""),
        })
        return {"sql": extract_sql(reply), "attempts": state.get("attempts", 0) + 1}

    def answer(self, state: PipelineState) -> dict:
        # Step 6: grounded answer, with explicit no-answer and failure paths
        error = state.get("error")
        if error == NO_ANSWER:
            answer = ("The dataset doesn't contain the information needed to answer this, "
                      "so I haven't answered from general knowledge.")
            sql = "-- no query: the data can't answer this question"
        elif error:
            answer = f"I couldn't calculate this from the data. The last error was: {error}"
            sql = state.get("sql", "")
        else:
            answer = self.answerer.generate(
                self.effective_question(state), state["sql"], state.get("result"))
            sql = state["sql"]
        return {"answer": answer, "sql": sql}

    def run(self, question: str, tables_override: list[str] | None = None,
            history: list[dict] | None = None) -> dict:
        state = self.graph.invoke({
            "question": question,
            "attempts": 0,
            "tables_override": tables_override,
            "top_n": [],
            "similar": [],
            "score_kind": "distance",
            "history": history or [],
        })
        self.last_state = state
        return {
            "answer": state["answer"],
            "sql": state["sql"],
            "top_n_tables": state.get("top_n", []),
            "selected_tables": state.get("top_k", []),
            "similar_queries": [{"description": query["description"], "sql": query["sql"]}
                                for query in state.get("similar", [])],
            "result": df_to_json(state.get("result")),
            "error": state.get("error"),
            "selection_reason": state.get("selection_reason"),
            "sql_explanation": state.get("sql_explanation"),
            "score_kind": state.get("score_kind", "distance"),
            "standalone_question": (state.get("standalone_question")
                                    if state.get("standalone_question") != question else None),
        }