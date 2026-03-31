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

    if not settings.github_webhook_secret:
       
        logger.warning("No webhook secret configured — skipping signature verification")
        return True

    secret  = settings.github_webhook_secret.encode("utf-8")
    expected = "sha256=" + hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected, signature_header)


async def fetch_pr_diff(repo: str, pr_number: int) -> str:

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
