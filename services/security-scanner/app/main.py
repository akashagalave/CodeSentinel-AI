# services/security-scanner/app/main.py
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
from services.security_scanner.app.agent import run_security_scanner
from services.security_scanner.app.schema import SecurityReviewResponse, HealthResponse

logger = get_logger("security_main")

agent_latency    = Histogram("security_latency_seconds", "Security Scanner latency",
                             buckets=[1, 5, 10, 20, 30, 45, 60])
findings_counter = Counter("security_findings_total", "Security findings", ["severity"])
reviews_total    = Counter("security_reviews_total", "Total reviews")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Security Scanner starting...")
    logger.info("Security Scanner ready!")
    yield


app = FastAPI(
    title="CodeSentinel Security Scanner",
    description="Semgrep OWASP + GPT-4o security analysis",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/review", response_model=SecurityReviewResponse)
async def review(request: AgentReviewRequest):
    reviews_total.inc()
    start = time.time()

    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="Diff cannot be empty")

    findings, cost, tokens = run_security_scanner(
        diff=request.diff,
        context_chunks=request.context_chunks,
    )

    latency_ms = (time.time() - start) * 1000
    agent_latency.observe(latency_ms / 1000)

    for f in findings:
        findings_counter.labels(severity=f.severity).inc()

    return SecurityReviewResponse(
        findings=findings,
        cost_usd=cost,
        latency_ms=latency_ms,
        tokens_used=tokens,
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", service="security-scanner")


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
