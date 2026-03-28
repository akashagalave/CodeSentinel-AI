# services/gateway/app/webhook_handler.py
"""
Validate GitHub webhook + fetch PR diff.

Two responsibilities:
1. Security: verify HMAC-SHA256 signature so only GitHub can trigger reviews
2. Data: fetch the actual PR diff from GitHub API
"""
import hashlib
import hmac
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from shared.schemas import PRReviewJob
from services.gateway.app.config import settings

logger = get_logger("webhook_handler")


def verify_github_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """
    Verify GitHub webhook HMAC-SHA256 signature.

    Why verify?
      Anyone on the internet can POST to your /webhook/github endpoint.
      Without verification, anyone could trigger fake reviews.
      GitHub signs every webhook with your secret — we verify the signature.

    How it works:
      GitHub computes: HMAC-SHA256(secret, payload) → sends as X-Hub-Signature-256
      We compute:      HMAC-SHA256(our_secret, payload)
      If they match → request is from GitHub ✓
      If they differ → reject with 403 ✗
    """
    if not settings.github_webhook_secret:
        # Dev mode — skip verification if no secret configured
        logger.warning("No webhook secret configured — skipping signature verification")
        return True

    secret  = settings.github_webhook_secret.encode("utf-8")
    expected = "sha256=" + hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()

    # compare_digest prevents timing attacks
    # (regular == can leak info via timing differences)
    return hmac.compare_digest(expected, signature_header)


async def fetch_pr_diff(repo: str, pr_number: int) -> str:
    """
    Fetch PR unified diff from GitHub API.

    Why async?
      Network call = I/O bound. async = other requests can run while waiting.
      FastAPI is async — blocking HTTP calls would freeze the server.

    Accept header: application/vnd.github.diff
      This tells GitHub API to return the raw diff format
      (instead of JSON metadata about the PR).
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {settings.github_token}",
        "Accept":        "application/vnd.github.diff",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)

    if response.status_code == 200:
        diff = response.text
        logger.info(f"Fetched diff for {repo}#{pr_number}: {len(diff)} chars")
        return diff
    else:
        logger.error(
            f"Failed to fetch diff for {repo}#{pr_number}: "
            f"HTTP {response.status_code}"
        )
        return ""


def parse_webhook_payload(payload: dict) -> dict:
    """
    Extract relevant fields from GitHub webhook payload.
    Returns clean dict with only what we need.
    """
    pr   = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    return {
        "action":     payload.get("action", ""),
        "pr_number":  payload.get("number", 0),
        "repo":       repo.get("full_name", ""),
        "head_sha":   pr.get("head", {}).get("sha", ""),
        "pr_title":   pr.get("title", ""),
        "pr_author":  pr.get("user", {}).get("login", ""),
    }
