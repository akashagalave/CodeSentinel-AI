# services/retrieval/app/main.py
"""
Retrieval Service — FastAPI app.
Single endpoint: POST /search
Called by Orchestrator before running agents.
"""
import time
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.retrieval.app.model_loader import load_all, get_doc_count
from services.retrieval.app.hybrid_search import hybrid_search
from services.retrieval.app.schema import SearchRequest, SearchResponse, HealthResponse

logger = get_logger("retrieval_main")

# ── Prometheus metrics ──────────────────────────────────────────
search_latency = Histogram(
    "retrieval_search_latency_seconds",
    "Hybrid search latency in seconds",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)
search_requests = Counter(
    "retrieval_searches_total",
    "Total search requests received",
)
search_errors = Counter(
    "retrieval_errors_total",
    "Total search errors",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load models at startup, cleanup at shutdown.
    FastAPI lifespan = modern replacement for @app.on_event("startup").
    """
    logger.info("Retrieval Service starting up...")
    load_all()   # Load ChromaDB + BM25 + CrossEncoder ONCE
    logger.info("Retrieval Service ready!")
    yield
    logger.info("Retrieval Service shutting down...")


app = FastAPI(
    title="CodeSentinel Retrieval Service",
    description="Hybrid search: CodeBERT + BM25 + RRF + CrossEncoder rerank",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Hybrid search endpoint.
    Called by Orchestrator with PR diff → returns top-k relevant code chunks.
    """
    search_requests.inc()
    start = time.time()

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        results = hybrid_search(query=request.query, k=request.k)

        latency_ms = (time.time() - start) * 1000
        search_latency.observe(latency_ms / 1000)

        return SearchResponse(
            chunks=[r["content"] for r in results],
            metadata=[r["metadata"] for r in results],
            latency_ms=latency_ms,
        )

    except Exception as e:
        search_errors.inc()
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check — K8s liveness + readiness probe calls this."""
    return HealthResponse(
        status="healthy",
        service="retrieval",
        docs_count=get_doc_count(),
    )


@app.get("/metrics")
async def metrics():
    """Prometheus scrapes this endpoint every 15 seconds."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
