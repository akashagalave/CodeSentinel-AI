# services/bug-hunter/app/main.py
import time
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from shared.schemas import AgentReviewRequest, BugReviewResponse
from services.bug_hunter.app.agent import run_bug_hunter
from services.bug_hunter.app.cache import initialize_cache
from services.bug_hunter.app.schema import HealthResponse

logger = get_logger("bug_hunter_main")

# ── Prometheus ──────────────────────────────────────────────────
agent_latency = Histogram(
    "bug_hunter_latency_seconds",
    "Bug Hunter agent latency",
    buckets=[1, 5, 10, 20, 30, 45, 60],
)
findings_counter = Counter(
    "bug_hunter_findings_total",
    "Total bug findings by severity",
    ["severity"],
)
reviews_total  = Counter("bug_hunter_reviews_total",  "Total reviews processed")
reviews_failed = Counter("bug_hunter_reviews_failed",  "Total failed reviews")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Bug Hunter Service starting...")
    initialize_cache()   # GPTCache setup
    logger.info("Bug Hunter Service ready!")
    yield
    logger.info("Bug Hunter Service shutting down...")


app = FastAPI(
    title="CodeSentinel Bug Hunter",
    description="GPT-4o powered bug detection agent",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/review", response_model=BugReviewResponse)
async def review(request: AgentReviewRequest):
    """
    Receive diff + context from Orchestrator.
    Run Bug Hunter agent.
    Return structured BugFindings.
    """
    reviews_total.inc()
    start = time.time()

    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="Diff cannot be empty")

    findings, cost, tokens = run_bug_hunter(
        diff=request.diff,
        context_chunks=request.context_chunks,
    )

    latency_ms = (time.time() - start) * 1000
    agent_latency.observe(latency_ms / 1000)

    for f in findings:
        findings_counter.labels(severity=f.severity).inc()

    if not findings and cost == 0.0:
        reviews_failed.inc()

    logger.info(
        f"Review done: {len(findings)} findings | "
        f"repo={request.repo} pr={request.pr_number} | "
        f"${cost:.4f} | {latency_ms:.0f}ms"
    )

    return BugReviewResponse(
        findings=findings,
        cost_usd=cost,
        latency_ms=latency_ms,
        tokens_used=tokens,
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", service="bug-hunter")


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
