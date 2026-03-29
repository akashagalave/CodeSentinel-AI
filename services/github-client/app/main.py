# services/github-client/app/main.py
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.github_client.app.schema import (
    PostReviewRequest, PostReviewResponse, HealthResponse
)
from services.github_client.app.pr_commenter import post_pr_comment
from services.github_client.app.check_run import create_check_run

logger = get_logger("github_client_main")

reviews_posted  = Counter("github_client_posted_total",  "Reviews posted to GitHub")
reviews_blocked = Counter("github_client_blocked_total", "Reviews with CRITICAL — merge blocked")
reviews_failed  = Counter("github_client_failed_total",  "Failed to post review")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GitHub Client starting...")
    logger.info("GitHub Client ready!")
    yield


app = FastAPI(
    title="CodeSentinel GitHub Client",
    description="Posts review comments + check-runs to GitHub PRs",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/post-review", response_model=PostReviewResponse)
async def post_review(request: PostReviewRequest):
    """
    Post review results to GitHub PR.
    1. Post markdown comment on PR
    2. Create Check-run (green tick or red X)
    """
    try:
        # Post PR comment
        comment_url = post_pr_comment(
            repo=              request.repo,
            pr_number=         request.pr_number,
            findings_markdown= request.findings_markdown,
        )

        # Create Check-run
        check_run_id = create_check_run(
            repo=              request.repo,
            head_sha=          request.head_sha,
            has_critical=      request.has_critical,
            total_findings=    len(request.findings),
            total_cost_usd=    request.total_cost_usd,
            review_latency_ms= request.review_latency_ms,
        )

        reviews_posted.inc()
        if request.has_critical:
            reviews_blocked.inc()
            logger.warning(
                f"MERGE BLOCKED: {request.repo}#{request.pr_number} "
                f"has CRITICAL findings"
            )

        return PostReviewResponse(
            success=      bool(comment_url or check_run_id),
            comment_url=  comment_url,
            check_run_id= check_run_id,
        )

    except Exception as e:
        reviews_failed.inc()
        logger.error(f"Failed to post review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", service="github-client")


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
