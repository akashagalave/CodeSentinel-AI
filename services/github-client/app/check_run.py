# services/github-client/app/check_run.py
"""
GitHub Check-run — the green tick or red X on the PR.

When CodeSentinel finds CRITICAL issues:
  → Check-run status = failure
  → Merge button shows red X
  → Developer CANNOT merge until they fix critical issues

When no critical issues:
  → Check-run status = success
  → Merge button shows green tick
  → Developer can merge
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

from github import Github, GithubException

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.github_client.app.config import settings

logger = get_logger("check_run")


def create_check_run(
    repo:              str,
    head_sha:          str,
    has_critical:      bool,
    total_findings:    int,
    total_cost_usd:    float,
    review_latency_ms: float,
) -> int:
    """
    Create GitHub Check-run on the PR commit.
    Returns check_run_id (0 if failed).
    """
    if not settings.github_token:
        logger.warning("No GITHUB_TOKEN — skipping check run")
        return 0

    # Determine status based on findings
    if has_critical:
        conclusion = "failure"
        title      = "CodeSentinel: CRITICAL issues found — merge blocked"
        summary    = "Critical security or bug issues must be fixed before merging."
    elif total_findings > 0:
        conclusion = "neutral"
        title      = f"CodeSentinel: {total_findings} issue(s) found"
        summary    = "Review findings posted as PR comment. No critical issues blocking merge."
    else:
        conclusion = "success"
        title      = "CodeSentinel: No issues found ✅"
        summary    = "Clean code review. All checks passed."

    try:
        gh      = Github(settings.github_token)
        gh_repo = gh.get_repo(repo)

        check_run = gh_repo.create_check_run(
            name=       "CodeSentinel AI Review",
            head_sha=   head_sha,
            status=     "completed",
            conclusion= conclusion,
            completed_at=datetime.now(timezone.utc),
            output={
                "title":   title,
                "summary": summary,
                "text": (
                    f"**Review Summary**\n\n"
                    f"- Total findings: {total_findings}\n"
                    f"- Review cost: ${total_cost_usd:.4f}\n"
                    f"- Review time: {review_latency_ms:.0f}ms\n"
                    f"- Status: {'🔴 BLOCKED' if has_critical else '✅ PASSED'}"
                ),
            },
        )

        logger.info(
            f"Check run created: {repo} | {conclusion} | "
            f"id={check_run.id}"
        )
        return check_run.id

    except GithubException as e:
        logger.error(f"GitHub API error creating check run: {e}")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error creating check run: {e}")
        return 0
