# services/retrieval/app/config.py
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ChromaDB
    chromadb_path: str = "./artifacts/chroma_db"
    chromadb_collection: str = "codebase"

    # Models
    embedding_model: str = "all-MiniLM-L6-v2"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Retrieval
    dense_top_k: int = 20
    sparse_top_k: int = 20
    hybrid_alpha: float = 0.6   # 0=all dense, 1=all sparse
    rerank_top_k: int = 5

    # BM25
    bm25_index_path: str = "./artifacts/bm25_index.pkl"

    class Config:
        env_file = ".env"

settings = Settings()
