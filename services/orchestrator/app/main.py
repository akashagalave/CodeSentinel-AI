
import time
import uuid
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.orchestrator.app.schema import ReviewRequest, ReviewResult, HealthResponse
from services.orchestrator.app.graph import review_graph
from services.orchestrator.app.state import ReviewState

logger = get_logger("orchestrator_main")

# ── Prometheus ──────────────────────────────────────────────────
review_latency  = Histogram(
    "orchestrator_review_latency_seconds",
    "End-to-end PR review latency",
    buckets=[5, 10, 20, 30, 45, 60, 90],
)
review_total    = Counter("orchestrator_reviews_total",  "Total reviews started")
review_failed   = Counter("orchestrator_reviews_failed", "Total reviews failed")
cost_per_review = Histogram(
    "orchestrator_cost_usd",
    "Total cost per review USD",
    buckets=[0.01, 0.02, 0.05, 0.10, 0.20],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Orchestrator starting...")
    logger.info("LangGraph compiled and ready")
    yield
    logger.info("Orchestrator shutting down...")


app = FastAPI(
    title="CodeSentinel Orchestrator",
    description="LangGraph coordination of 3 parallel agents",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/review", response_model=ReviewResult)
async def review(request: ReviewRequest):

    review_total.inc()
    start = time.time()

    
    session_id = request.session_id or f"{request.repo}#{request.pr_number}#{uuid.uuid4().hex[:8]}"

    
    initial_state: ReviewState = {
        "repo":               request.repo,
        "pr_number":          request.pr_number,
        "diff":               request.diff,
        "head_sha":           request.head_sha,
        "session_id":         session_id,
        "context_chunks":     [],
        "context_metadata":   [],
        "bug_findings":       [],
        "security_findings":  [],
        "perf_findings":      [],
        "all_findings":       [],
        "findings_markdown":  "",
        "has_critical":       False,
        "total_cost_usd":     0.0,
        "review_latency_ms":  0.0,
        "post_success":       False,
        "comment_url":        "",
        "check_run_id":       0,
        "errors":             [],
    }

    try:
        
        final_state = await review_graph.ainvoke(initial_state)

        latency_s = time.time() - start
        review_latency.observe(latency_s)
        cost_per_review.observe(final_state.get("total_cost_usd", 0))

        findings = final_state.get("all_findings", [])

        if final_state.get("errors"):
            logger.warning(f"Review completed with errors: {final_state['errors']}")

        logger.info(
            f"Review complete: {request.repo}#{request.pr_number} | "
            f"{len(findings)} findings | "
            f"${final_state.get('total_cost_usd', 0):.4f} | "
            f"{latency_s:.1f}s"
        )

        return ReviewResult(
            repo=request.repo,
            pr_number=request.pr_number,
            session_id=session_id,
            total_findings=len(findings),
            critical_count=sum(1 for f in findings if f.get("severity") == "CRITICAL"),
            high_count=sum(1 for f in findings if f.get("severity") == "HIGH"),
            medium_count=sum(1 for f in findings if f.get("severity") == "MEDIUM"),
            low_count=sum(1 for f in findings if f.get("severity") == "LOW"),
            has_critical=final_state.get("has_critical", False),
            total_cost_usd=final_state.get("total_cost_usd", 0.0),
            review_latency_ms=latency_s * 1000,
            findings_markdown=final_state.get("findings_markdown", ""),
        )

    except Exception as e:
        review_failed.inc()
        logger.error(f"Review pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", service="orchestrator")


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
