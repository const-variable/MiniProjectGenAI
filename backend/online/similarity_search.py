"""[Question Embeddings] -> [Similarity Search] -> [Top N Tables] (online).

The vector store holds both table summaries and SQL summaries. A hit on either
counts toward the tables it mentions; each table keeps its best (lowest) distance.
Hits on SQL summaries are also returned as similar past queries.
"""
import os

N_CANDIDATES = int(os.getenv("TOP_N", "5"))
MAX_EXAMPLES = 3


def top_n_tables(vector_store, query_log: list, question: str, n: int | None = None):
    n = N_CANDIDATES if n is None else n
    k = max(10, n * 3)
    if vector_store.retriever_kind == "hybrid":
        hits = vector_store.as_retriever(k).invoke(question)
        scored_hits = [(document, 1 / (rank + 1)) for rank, document in enumerate(hits)]
        score_kind = "rank"
    else:
        scored_hits = vector_store.similarity_search(question, k=k)
        score_kind = "distance"

    best, similar_queries = {}, []
    for doc, score in scored_hits:
        score = float(score)
        for t in doc.metadata["tables"]:
            better = t not in best or (score > best[t] if score_kind == "rank" else score < best[t])
            if better:
                best[t] = score
        if doc.metadata["kind"] == "sql" and len(similar_queries) < MAX_EXAMPLES:
            similar_queries.append(query_log[doc.metadata["log"]])

    ranked = sorted(best.items(), key=lambda item: item[1], reverse=score_kind == "rank")[:n]
    return ([{"name": table, "score": round(score, 4)} for table, score in ranked],
            similar_queries, score_kind)
