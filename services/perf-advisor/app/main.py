# services/perf-advisor/app/main.py
import time
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from shared.schemas import AgentReviewRequest
from services.perf_advisor.app.agent import run_perf_advisor
from services.perf_advisor.app.schema import PerfReviewResponse, HealthResponse

logger = get_logger("perf_main")

agent_latency    = Histogram("perf_latency_seconds", "Perf Advisor latency",
                             buckets=[0.5, 2, 5, 10, 20, 30, 45])
findings_counter = Counter("perf_findings_total", "Perf findings", ["severity"])
reviews_total    = Counter("perf_reviews_total",  "Total reviews")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Perf Advisor starting...")
    logger.info("Perf Advisor ready!")
    yield


app = FastAPI(
    title="CodeSentinel Perf Advisor",
    description="GPT-4o-mini performance pattern detection",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/review", response_model=PerfReviewResponse)
async def review(request: AgentReviewRequest):
    reviews_total.inc()
    start = time.time()

    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="Diff cannot be empty")

    findings, cost, tokens = run_perf_advisor(
        diff=request.diff,
        context_chunks=request.context_chunks,
    )

    latency_ms = (time.time() - start) * 1000
    agent_latency.observe(latency_ms / 1000)
    for f in findings:
        findings_counter.labels(severity=f.severity).inc()

    return PerfReviewResponse(
        findings=findings,
        cost_usd=cost,
        latency_ms=latency_ms,
        tokens_used=tokens,
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", service="perf-advisor")


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
