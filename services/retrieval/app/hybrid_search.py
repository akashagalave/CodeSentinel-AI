# services/retrieval/app/hybrid_search.py
"""
Hybrid search pipeline:
  Dense (CodeBERT) + Sparse (BM25) + RRF fusion + CrossEncoder rerank

Why each step:
  Dense:       "authenticate_user" → finds "verify_credentials" (semantic)
  BM25:        "authenticate_user" → finds exact function named authenticate_user
  RRF fusion:  combines both rankings mathematically — no manual weight tuning
  CrossEncoder: scores (query, doc) pairs together — much better than bi-encoder alone

alpha = 0.6 → 60% weight to BM25 (identifiers matter more in code)
"""
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
    """
    Same tokenizer as index_builder.py — MUST match for BM25 to work.
    If index built with one tokenizer and query uses another → poor recall.
    """
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
    """
    Reciprocal Rank Fusion score.
    k=60 is the standard RRF constant (from the original RRF paper).
    Higher rank (lower number) = higher score.
    rank=0 → 1/(60+0) = 0.0167 (best)
    rank=19 → 1/(60+19) = 0.0127 (worst in top-20)
    """
    return 1.0 / (k + rank)


def hybrid_search(query: str, k: int = 5) -> list[dict]:
    """
    Full hybrid retrieval pipeline.

    Args:
        query: PR diff text or search query
        k: number of results to return (default 5)

    Returns:
        List of dicts with 'content' and 'metadata' keys
        Sorted by relevance (most relevant first)
    """
    start = time.time()

    collection    = get_collection()
    bm25_data     = get_bm25()
    cross_encoder = get_cross_encoder()
    alpha         = settings.hybrid_alpha   # 0.6
    dense_top_k   = settings.dense_top_k    # 20

    # ── Step 1: Dense retrieval (ChromaDB + CodeBERT) ──────────
    dense_raw = collection.query(
        query_texts=[query],
        n_results=dense_top_k,
        include=["documents", "metadatas", "ids"],
    )

    dense_ids   = dense_raw["ids"][0]
    dense_docs  = dense_raw["documents"][0]
    dense_metas = dense_raw["metadatas"][0]

    # Map id → (document, metadata) for later lookup
    id_to_doc = {
        id_: {"content": doc, "metadata": meta}
        for id_, doc, meta in zip(dense_ids, dense_docs, dense_metas)
    }

    # Dense rank: id → rank position (0 = most relevant)
    dense_rank = {id_: rank for rank, id_ in enumerate(dense_ids)}

    # ── Step 2: Sparse retrieval (BM25) ────────────────────────
    query_tokens = tokenize_query(query)
    bm25         = bm25_data["bm25"]
    doc_ids      = bm25_data["doc_ids"]

    bm25_scores = bm25.get_scores(query_tokens)

    # BM25 rank: id → rank position (0 = highest BM25 score)
    sorted_bm25 = sorted(
        range(len(bm25_scores)),
        key=lambda i: bm25_scores[i],
        reverse=True,
    )[:dense_top_k]

    sparse_rank = {doc_ids[i]: rank for rank, i in enumerate(sorted_bm25)}

    # ── Step 3: RRF Fusion ─────────────────────────────────────
    # Combine all candidate IDs from both strategies
    all_ids = set(dense_rank.keys()) | set(sparse_rank.keys())

    rrf_scores = {}
    for id_ in all_ids:
        # Dense contribution (40% weight = 1-alpha = 1-0.6 = 0.4)
        d_rank = dense_rank.get(id_, dense_top_k + 100)
        dense_contribution = (1 - alpha) * rrf_score(d_rank)

        # Sparse contribution (60% weight = alpha = 0.6)
        s_rank = sparse_rank.get(id_, dense_top_k + 100)
        sparse_contribution = alpha * rrf_score(s_rank)

        rrf_scores[id_] = dense_contribution + sparse_contribution

    # Sort by RRF score → take top dense_top_k
    top_fused = sorted(
        rrf_scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:dense_top_k]

    # Collect documents for reranking
    candidates = []
    for id_, _ in top_fused:
        if id_ in id_to_doc:
            candidates.append({
                "id":       id_,
                "content":  id_to_doc[id_]["content"],
                "metadata": id_to_doc[id_]["metadata"],
            })

    if not candidates:
        logger.warning(f"No candidates after RRF fusion for query: {query[:50]}")
        return []

    # ── Step 4: CrossEncoder Reranking ─────────────────────────
    # CrossEncoder scores (query, document) TOGETHER
    # Much better than bi-encoder because it sees both at once
    pairs  = [(query, c["content"][:512]) for c in candidates]
    scores = cross_encoder.predict(pairs)

    # Sort by CrossEncoder score → take top k
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
