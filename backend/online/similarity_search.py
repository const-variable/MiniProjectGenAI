"""[Question Embeddings] -> [Similarity Search] -> [Top N Tables] (online).

The vector store holds both table summaries and SQL summaries. A hit on either
counts toward the tables it mentions; each table keeps its best (lowest) distance.
Hits on SQL summaries are also returned as similar past queries.
"""
N_CANDIDATES = 5
MAX_EXAMPLES = 3


def top_n_tables(vector_store, query_log: list, question: str, n: int = N_CANDIDATES):
    hits = vector_store.similarity_search(question, k=10)

    best, similar_queries = {}, []
    for doc, distance in hits:
        distance = float(distance)
        for t in doc.metadata["tables"]:
            if t not in best or distance < best[t]:
                best[t] = distance
        if doc.metadata["kind"] == "sql" and len(similar_queries) < MAX_EXAMPLES:
            similar_queries.append(query_log[doc.metadata["log"]])

    ranked = sorted(best.items(), key=lambda kv: kv[1])[:n]
    return [{"name": t, "score": round(d, 4)} for t, d in ranked], similar_queries
