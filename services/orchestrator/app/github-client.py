import requests
import os
import logging

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

def post_github_comment(repo: str, pr_number: int, comment: str):
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    payload = {
        "body": comment
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 201:
        logger.info(f" Comment posted on PR #{pr_number}")
    else:
        logger.error(f" Failed to post comment: {response.text}")