# services/gateway/app/main.py
import time
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from shared.schemas import PRReviewJob, WebhookResponse, HealthResponse
from services.gateway.app.config import settings
from services.gateway.app.webhook_handler import (
    verify_github_signature,
    fetch_pr_diff,
    parse_webhook_payload,
)

logger = get_logger("gateway_main")

# ── Prometheus metrics ──────────────────────────────────────────
webhooks_received = Counter("gateway_webhooks_total", "Total webhooks received", ["action"])
webhooks_queued   = Counter("gateway_queued_total", "Webhooks sent to orchestrator")
webhooks_skipped  = Counter("gateway_skipped_total", "Webhooks skipped (wrong action)")
webhooks_failed   = Counter("gateway_failed_total", "Webhooks failed")
webhook_latency   = Histogram(
    "gateway_webhook_latency_seconds",
    "Time to process webhook and queue review",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0],
)


async def run_review_background(job: PRReviewJob):
    """
    Background task — calls Orchestrator with the PR job.
    Runs AFTER gateway already returned 200 to GitHub.
    GitHub doesn't wait for this — it already got its response.
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.orchestrator_url}/review",
                json={
                    "repo":       job.repo,
                    "pr_number":  job.pr_number,
                    "diff":       job.diff,
                    "head_sha":   job.head_sha,
                    "session_id": job.session_id,
                },
            )
            if response.status_code == 200:
                logger.info(f"Orchestrator accepted: {job.repo}#{job.pr_number}")
            else:
                logger.error(
                    f"Orchestrator rejected {job.repo}#{job.pr_number}: "
                    f"HTTP {response.status_code}"
                )
    except Exception as e:
        webhooks_failed.inc()
        logger.error(f"Failed to reach orchestrator for {job.repo}#{job.pr_number}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Gateway Service starting...")
    logger.info(f"Orchestrator URL: {settings.orchestrator_url}")
    logger.info("Gateway Service ready!")
    yield
    logger.info("Gateway Service shutting down...")


app = FastAPI(
    title="CodeSentinel Gateway",
    description="Receives GitHub webhooks, validates them, queues PR reviews",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/webhook/github", response_model=WebhookResponse)
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Main entry point — receives GitHub PR webhook.

    Flow:
    1. Read raw body (needed for HMAC verification)
    2. Verify HMAC signature (security)
    3. Parse payload → extract PR info
    4. Filter: only process opened/synchronize/reopened
    5. Fetch PR diff from GitHub API
    6. Return 200 immediately ← GitHub gets this fast
    7. BackgroundTask calls Orchestrator (async, GitHub doesn't wait)
    """
    start = time.time()
    payload_bytes = await request.body()

    # ── Security: verify signature ──────────────────────────────
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(payload_bytes, signature):
        webhooks_failed.inc()
        logger.warning("Webhook rejected: invalid signature")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    # ── Parse payload ───────────────────────────────────────────
    payload = await request.json()
    pr_info = parse_webhook_payload(payload)
    action  = pr_info["action"]

    webhooks_received.labels(action=action).inc()

    # ── Filter: only review on these actions ────────────────────
    # opened     = new PR
    # synchronize = new commits pushed to existing PR
    # reopened   = PR was closed and reopened
    reviewable_actions = {"opened", "synchronize", "reopened"}
    if action not in reviewable_actions:
        webhooks_skipped.inc()
        logger.info(f"Skipped: action='{action}' not in {reviewable_actions}")
        return WebhookResponse(
            status="skipped",
            message=f"Action '{action}' does not trigger review",
        )

    repo      = pr_info["repo"]
    pr_number = pr_info["pr_number"]
    head_sha  = pr_info["head_sha"]

    if not repo or not pr_number:
        webhooks_failed.inc()
        raise HTTPException(status_code=400, detail="Missing repo or pr_number in payload")

    # ── Fetch PR diff ───────────────────────────────────────────
    diff = await fetch_pr_diff(repo, pr_number)
    if not diff:
        logger.warning(f"Empty diff for {repo}#{pr_number} — skipping")
        return WebhookResponse(
            status="skipped",
            pr_number=pr_number,
            repo=repo,
            message="Empty diff — nothing to review",
        )

    # ── Build job ───────────────────────────────────────────────
    session_id = f"{repo}#{pr_number}#{head_sha[:8]}"
    job = PRReviewJob(
        repo=repo,
        pr_number=pr_number,
        diff=diff,
        head_sha=head_sha,
        session_id=session_id,
    )

    # ── Queue background task ───────────────────────────────────
    background_tasks.add_task(run_review_background, job)
    webhooks_queued.inc()

    latency = time.time() - start
    webhook_latency.observe(latency)

    logger.info(
        f"Queued review: {repo}#{pr_number} | "
        f"session={session_id} | "
        f"diff={len(diff)} chars | "
        f"latency={latency:.3f}s"
    )

    # ── Return 200 immediately ──────────────────────────────────
    # GitHub receives this fast — doesn't wait for actual review
    return WebhookResponse(
        status="queued",
        pr_number=pr_number,
        repo=repo,
        message=f"Review queued for {repo}#{pr_number}",
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """K8s liveness + readiness probe."""
    return HealthResponse(status="healthy", service="gateway")


@app.get("/metrics")
async def metrics():
    """Prometheus scrapes this every 15 seconds."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)



