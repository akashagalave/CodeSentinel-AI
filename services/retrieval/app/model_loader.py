# services/retrieval/app/model_loader.py
"""
Load ALL heavy models ONCE at startup — shared across all requests.

Why singletons?
  CodeBERT = 500MB. ChromaDB index = 1-2GB.
  Loading per-request = 30+ seconds per review.
  Module-level singletons = load once at startup,
  serve thousands of requests from memory.
"""
import pickle
import sys
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from sentence_transformers import CrossEncoder

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.retrieval.app.config import settings

logger = get_logger("model_loader")

# Module-level singletons — None until load_all() called
_collection   = None
_bm25_data    = None
_cross_encoder = None
_loaded       = False


def load_all():
    """
    Load ChromaDB + BM25 + CrossEncoder at FastAPI startup.
    Called ONCE from lifespan context manager in main.py.
    """
    global _collection, _bm25_data, _cross_encoder, _loaded

    if _loaded:
        return  # Already loaded — don't reload

    logger.info("Loading models at startup (one-time only)...")

    # ── ChromaDB ────────────────────────────────────────────────
    logger.info(f"  Loading ChromaDB from: {settings.chromadb_path}")
    client = chromadb.PersistentClient(path=settings.chromadb_path)
    embed_fn = SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model
    )
    _collection = client.get_collection(
        name=settings.chromadb_collection,
        embedding_function=embed_fn,
    )
    doc_count = _collection.count()
    logger.info(f"  ChromaDB loaded: {doc_count:,} documents")

    # ── BM25 ────────────────────────────────────────────────────
    logger.info(f"  Loading BM25 from: {settings.bm25_index_path}")
    with open(settings.bm25_index_path, "rb") as f:
        _bm25_data = pickle.load(f)
    logger.info(f"  BM25 loaded: {_bm25_data['corpus_size']:,} documents")

    # ── CrossEncoder ─────────────────────────────────────────────
    logger.info(f"  Loading CrossEncoder: {settings.rerank_model}")
    _cross_encoder = CrossEncoder(settings.rerank_model)
    logger.info("  CrossEncoder loaded")

    _loaded = True
    logger.info("All models loaded successfully!")


def get_collection():
    if not _loaded:
        raise RuntimeError("Call load_all() first at startup")
    return _collection


def get_bm25():
    if not _loaded:
        raise RuntimeError("Call load_all() first at startup")
    return _bm25_data


def get_cross_encoder():
    if not _loaded:
        raise RuntimeError("Call load_all() first at startup")
    return _cross_encoder


def get_doc_count() -> int:
    if not _loaded:
        return 0
    return _collection.count()
