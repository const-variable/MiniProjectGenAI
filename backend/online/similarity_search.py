"""[Question Embeddings] -> [Similarity Search] -> [Top N Tables] (online).

The vector store holds both table summaries and SQL summaries. A hit on either
counts toward the tables it mentions; each table keeps its best (lowest) distance.
Hits on SQL summaries are also returned as similar past queries.
"""
import os

MAX_EXAMPLES = 3  # hyperparameter


def top_n_tables(vector_store, query_log: list, question: str,
                 candidate_limit: int | None = None):
    if candidate_limit is None:
        candidate_limit = int(os.getenv("TOP_N", "5"))  # hyperparameter
    # Over-fetch so every table can be scored even when SQL-log hits crowd the results.
    search_limit = max(10, candidate_limit * 3)  # hyperparameter
    if vector_store.retriever_kind == "hybrid":
        hits = vector_store.as_retriever(search_limit).invoke(question)
        scored_hits = [(document, 1 / (rank + 1)) for rank, document in enumerate(hits)]
        score_kind = "rank"
    else:
        scored_hits = vector_store.similarity_search(question, k=search_limit)
        score_kind = "distance"

    best_table_scores, similar_queries = {}, []
    for document, score in scored_hits:
        score = float(score)
        for table_name in document.metadata["tables"]:
            is_better_score = (table_name not in best_table_scores
                               or (score > best_table_scores[table_name]
                                   if score_kind == "rank" else score < best_table_scores[table_name]))
            if is_better_score:
                best_table_scores[table_name] = score
        if document.metadata["kind"] == "sql" and len(similar_queries) < MAX_EXAMPLES:
            similar_queries.append(query_log[document.metadata["log"]])

    ranked = sorted(best_table_scores.items(), key=lambda item: item[1],
                    reverse=score_kind == "rank")[:candidate_limit]
    return ([{"name": table, "score": round(score, 4)} for table, score in ranked],
            similar_queries, score_kind)
