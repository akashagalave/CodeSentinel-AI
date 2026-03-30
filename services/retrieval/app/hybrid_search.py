# services/retrieval/app/hybrid_search.py
import re
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.retrieval.app.model_loader import (
    get_collection, get_bm25, get_cross_encoder
)
from services.retrieval.app.config import settings

logger = get_logger("hybrid_search")


def tokenize_query(text: str) -> list[str]:
    tokens = re.split(
        r'[\s\(\)\[\]{},\.\:;\'\"<>!@#$%^&*+=|/\\-]+',
        text.lower()
    )
    stopwords = {
        "def", "return", "if", "else", "elif", "for", "while",
        "import", "from", "class", "self", "cls", "true", "false",
        "none", "pass", "break", "continue", "and", "or", "not",
        "in", "is", "try", "except", "finally", "with", "as",
    }
    return [t for t in tokens if len(t) > 1 and t not in stopwords]


def rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def hybrid_search(query: str, k: int = 5) -> list[dict]:
    start = time.time()

    collection    = get_collection()
    bm25_data     = get_bm25()
    cross_encoder = get_cross_encoder()
    alpha         = settings.hybrid_alpha
    dense_top_k   = settings.dense_top_k

    # ── Step 1: Dense retrieval ─────────────────────────────────
    dense_raw = collection.query(
        query_texts=[query],
        n_results=dense_top_k,
        include=["documents", "metadatas"],
    )

    dense_docs  = dense_raw["documents"][0]
    dense_metas = dense_raw["metadatas"][0]
    dense_ids   = [f"doc_{i}" for i in range(len(dense_docs))]

    id_to_doc = {
        id_: {"content": doc, "metadata": meta}
        for id_, doc, meta in zip(dense_ids, dense_docs, dense_metas)
    }

    dense_rank = {id_: rank for rank, id_ in enumerate(dense_ids)}

    # ── Step 2: Sparse retrieval (BM25) ─────────────────────────
    query_tokens = tokenize_query(query)
    bm25         = bm25_data["bm25"]
    doc_ids      = bm25_data["doc_ids"]

    bm25_scores = bm25.get_scores(query_tokens)

    sorted_bm25 = sorted(
        range(len(bm25_scores)),
        key=lambda i: bm25_scores[i],
        reverse=True,
    )[:dense_top_k]

    sparse_rank = {doc_ids[i]: rank for rank, i in enumerate(sorted_bm25)}

    # ── Step 3: RRF Fusion ───────────────────────────────────────
    all_ids = set(dense_rank.keys()) | set(sparse_rank.keys())

    rrf_scores = {}
    for id_ in all_ids:
        d_rank = dense_rank.get(id_, dense_top_k + 100)
        dense_contribution = (1 - alpha) * rrf_score(d_rank)

        s_rank = sparse_rank.get(id_, dense_top_k + 100)
        sparse_contribution = alpha * rrf_score(s_rank)

        rrf_scores[id_] = dense_contribution + sparse_contribution

    top_fused = sorted(
        rrf_scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:dense_top_k]

    candidates = []
    for id_, _ in top_fused:
        if id_ in id_to_doc:
            candidates.append({
                "id":       id_,
                "content":  id_to_doc[id_]["content"],
                "metadata": id_to_doc[id_]["metadata"],
            })

    if not candidates:
        logger.warning(f"No candidates for query: {query[:50]}")
        return []

    # ── Step 4: CrossEncoder Reranking ──────────────────────────
    pairs  = [(query, c["content"][:512]) for c in candidates]
    scores = cross_encoder.predict(pairs)

    reranked = sorted(
        zip(candidates, scores),
        key=lambda x: x[1],
        reverse=True,
    )

    results = [c for c, _ in reranked[:k]]

    latency_ms = (time.time() - start) * 1000
    logger.info(
        f"Hybrid search: {len(results)} results | "
        f"{latency_ms:.1f}ms | query='{query[:40]}...'"
    )

    return results