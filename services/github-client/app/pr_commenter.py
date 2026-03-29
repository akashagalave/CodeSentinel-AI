# services/github-client/app/pr_commenter.py
"""
Post inline PR comment using PyGithub.

Posts ONE comment with the full markdown report at the PR level.
(Not inline line-level comments — those require specifying exact
commit SHAs per line which is complex. PR-level comment is simpler
and shows everything in one place.)
"""
import sys
from pathlib import Path

from github import Github, GithubException

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.github_client.app.config import settings

logger = get_logger("pr_commenter")

# Bot comment marker — used to find and UPDATE existing comment
# (avoids duplicate comments on re-reviews of same PR)
BOT_MARKER = "<!-- CodeSentinel AI Review -->"


def post_pr_comment(
    repo:              str,
    pr_number:         int,
    findings_markdown: str,
) -> str:
    """
    Post or UPDATE CodeSentinel review comment on PR.
    Returns comment URL.
    """
    if not settings.github_token:
        logger.warning("No GITHUB_TOKEN — skipping comment post")
        return ""

    full_comment = f"{BOT_MARKER}\n{findings_markdown}"

    try:
        gh     = Github(settings.github_token)
        gh_repo = gh.get_repo(repo)
        pr      = gh_repo.get_pull(pr_number)

        # Check if we already have a comment on this PR
        # If yes — UPDATE it (not create duplicate)
        existing_comment = None
        for comment in pr.get_issue_comments():
            if BOT_MARKER in comment.body:
                existing_comment = comment
                break

        if existing_comment:
            existing_comment.edit(full_comment)
            comment_url = existing_comment.html_url
            logger.info(f"Updated existing comment: {comment_url}")
        else:
            new_comment = pr.create_issue_comment(full_comment)
            comment_url = new_comment.html_url
            logger.info(f"Created new comment: {comment_url}")

        return comment_url

    except GithubException as e:
        logger.error(f"GitHub API error posting comment: {e}")
        return ""
    except Exception as e:
        logger.error(f"Unexpected error posting comment: {e}")
        return ""
