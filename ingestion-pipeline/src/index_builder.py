import json
import os
import pickle
import re
import sys
import time
from pathlib import Path

import mlflow
import yaml
from chromadb import PersistentClient
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.logger import get_logger
from code_chunker import build_documents

load_dotenv()
logger = get_logger("index_builder")

PROJECT_ROOT  = Path(__file__).parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
PARAMS_FILE   = PROJECT_ROOT / "ingestion-pipeline" / "params.yaml"
REPORTS_DIR   = PROJECT_ROOT / "reports"


def init_mlflow():
    try:
        import dagshub
        dagshub.init(
            repo_owner=os.getenv("DAGSHUB_REPO_OWNER", "akashagalaveaaa1"),
            repo_name=os.getenv("DAGSHUB_REPO_NAME", "CodeSentinel-AI"),
            mlflow=True,
        )
        logger.info("DagsHub MLflow initialized")
    except Exception as e:
        logger.warning(f"DagsHub init failed: {e} — using local mlruns/")
        mlflow.set_tracking_uri("mlruns")


def tokenize_for_bm25(text: str) -> list[str]:
    tokens = re.split(r'[\s\(\)\[\]{},\.\:;\'\"<>!@#$%^&*+=|/\\-]+', text.lower())
    stopwords = {
        "def", "return", "if", "else", "elif", "for", "while",
        "import", "from", "class", "self", "cls", "true", "false",
        "none", "pass", "break", "continue", "and", "or", "not",
        "in", "is", "try", "except", "finally", "with", "as",
        "raise", "yield", "lambda", "global", "nonlocal",
    }
    return [t for t in tokens if len(t) > 1 and t not in stopwords]


def main():
    logger.info("=" * 60)
    logger.info("DVC Stage 3: Index Building")
    logger.info("=" * 60)

    with open(PARAMS_FILE) as f:
        params = yaml.safe_load(f)

    embed_model    = params["indexing"]["embedding_model"]
    collection_name = params["indexing"]["chromadb_collection"]
    batch_size     = params["indexing"]["embedding_batch_size"]

    functions_file = PROCESSED_DIR / "all_functions.jsonl"
    if not functions_file.exists():
        logger.error(f"Not found: {functions_file} — run ast_parser.py first")
        sys.exit(1)

    functions = []
    with open(functions_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                functions.append(json.loads(line))
    logger.info(f"Loaded {len(functions):,} functions")

    docs = build_documents(functions)
    logger.info(f"Built {len(docs):,} documents")

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    init_mlflow()

    run_id = None
    try:
        mlflow.set_experiment("codesentinel-index-building")
        active_run = mlflow.start_run(run_name=f"index-build-{time.strftime('%Y%m%d-%H%M')}")
        run_id = active_run.info.run_id
        mlflow.log_params({
            "embedding_model":  embed_model,
            "total_documents":  len(docs),
            "total_functions":  len(functions),
            "batch_size":       batch_size,
        })
        logger.info(f"MLflow run started: {run_id}")
    except Exception as e:
        logger.warning(f"MLflow tracking disabled: {e}")
        active_run = None

    try:
  
        logger.info(f"Loading model: {embed_model}")
        chroma_path = str(ARTIFACTS_DIR / "chroma_db")
        client = PersistentClient(path=chroma_path)

        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

        embed_fn   = SentenceTransformerEmbeddingFunction(model_name=embed_model)
        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(f"Embedding {len(docs):,} docs in batches of {batch_size}...")
        embed_start = time.time()

        for i in range(0, len(docs), batch_size):
            batch       = docs[i:i + batch_size]
            batch_ids   = [f"func_{i + j}" for j in range(len(batch))]
            batch_texts = [d.page_content for d in batch]
            batch_metas = [d.metadata for d in batch]
            collection.add(ids=batch_ids, documents=batch_texts, metadatas=batch_metas)

            if (i // batch_size) % 5 == 0:
                pct = min(i + batch_size, len(docs))
                logger.info(f"  Embedded {pct:,}/{len(docs):,}")

        embed_time = time.time() - embed_start
        logger.info(f"ChromaDB done in {embed_time:.0f}s")

    
        logger.info("Building BM25...")
        bm25_start       = time.time()
        tokenized_corpus = [tokenize_for_bm25(d.page_content) for d in docs]
        bm25             = BM25Okapi(tokenized_corpus)
        bm25_path        = ARTIFACTS_DIR / "bm25_index.pkl"

        with open(bm25_path, "wb") as f:
            pickle.dump({
                "bm25":        bm25,
                "doc_ids":     [f"func_{i}" for i in range(len(docs))],
                "corpus_size": len(docs),
            }, f)

        bm25_time = time.time() - bm25_start

        chroma_size_mb = sum(
            f.stat().st_size for f in Path(chroma_path).rglob("*") if f.is_file()
        ) / 1e6

        if active_run:
            try:
                mlflow.log_metrics({
                    "embedding_time_seconds": embed_time,
                    "bm25_build_time_seconds": bm25_time,
                    "index_size_mb":  chroma_size_mb,
                    "total_indexed":  len(docs),
                })
                mlflow.log_artifact(str(bm25_path))
            except Exception as e:
                logger.warning(f"MLflow logging failed: {e}")

        logger.info("=" * 60)
        logger.info("Stage 3 Complete!")
        logger.info(f"  Model:    {embed_model}")
        logger.info(f"  Indexed:  {len(docs):,} functions")
        logger.info(f"  ChromaDB: {chroma_size_mb:.1f} MB")
        logger.info(f"  BM25:     {bm25_path}")
        logger.info(f"  Time:     {embed_time:.0f}s embed + {bm25_time:.0f}s BM25")
        logger.info("=" * 60)

    finally:
        if active_run:
            try:
                mlflow.end_run()
            except Exception:
                pass


if __name__ == "__main__":
    main()