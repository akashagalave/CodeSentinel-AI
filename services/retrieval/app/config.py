
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  
    chromadb_path: str = "./artifacts/chroma_db"
    chromadb_collection: str = "codebase"

    
    embedding_model: str = "all-MiniLM-L6-v2"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    
    dense_top_k: int = 20
    sparse_top_k: int = 20
    hybrid_alpha: float = 0.6   
    rerank_top_k: int = 5

   
    bm25_index_path: str = "./artifacts/bm25_index.pkl"

    class Config:
        env_file = ".env"

settings = Settings()
