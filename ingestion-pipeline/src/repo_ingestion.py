# ingestion-pipeline/src/repo_ingestion.py
"""
DVC Stage 1: GitHub repos clone karke source files extract karo.

Input:  params.yaml → ingestion.target_repos
Output: data/raw/{owner}_{repo}/{file_path}.json

Har JSON file mein:
  - source_code: actual Python code
  - file_path: relative path in repo
  - language: python
  - repo: owner/repo string
  - lines: line count
  - sha: file hash (for change detection)

Why GitHub API instead of git clone?
  - git clone = entire repo history download (slow, large)
  - GitHub API = only current files (fast, efficient)
  - Rate limit: 5000 requests/hour with token
"""
import json
import os
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from github import Github, GithubException

# Add project root to path so shared/ can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.logger import get_logger

load_dotenv()
logger = get_logger("repo_ingestion")

# Paths relative to project root (DVC runs from project root)
RAW_DATA_DIR = Path("data/raw")
PARAMS_FILE = Path("ingestion-pipeline/params.yaml")
REPORTS_DIR = Path("reports")


def load_params() -> dict:
    with open(PARAMS_FILE) as f:
        return yaml.safe_load(f)


def repo_name_to_folder(url: str) -> str:
    """
    URL to safe folder name.
    https://github.com/pallets/flask → pallets_flask
    """
    parts = url.rstrip("/").split("/")
    return f"{parts[-2]}_{parts[-1]}"


def should_include_file(file_path: str, params: dict) -> bool:
    """Check if file should be included based on exclude patterns."""
    p = Path(file_path)

    # Check exclude patterns
    for pattern in params["ingestion"]["exclude_patterns"]:
        if p.match(pattern):
            return False

    # Check language
    lang_ext = {"python": ".py", "javascript": ".js"}
    allowed = [
        lang_ext[lang]
        for lang in params["ingestion"]["target_languages"]
        if lang in lang_ext
    ]
    return p.suffix in allowed


def ingest_single_repo(repo_url: str, gh: Github, params: dict) -> dict:
    """
    Single repo se saari files extract karo.
    Returns stats dict.
    """
    folder_name = repo_name_to_folder(repo_url)
    owner_repo = "/".join(repo_url.split("/")[-2:])
    out_dir = RAW_DATA_DIR / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting ingestion: {owner_repo}")
    stats = {
        "repo": owner_repo,
        "files_extracted": 0,
        "files_skipped": 0,
        "total_lines": 0,
        "errors": 0,
    }

    max_bytes = params["ingestion"]["max_file_size_kb"] * 1024

    try:
        repo = gh.get_repo(owner_repo)

        # BFS traversal — get all files
        queue = list(repo.get_contents(""))
        while queue:
            item = queue.pop(0)

            if item.type == "dir":
                try:
                    queue.extend(repo.get_contents(item.path))
                except GithubException:
                    continue
            else:
                # File — check if we want it
                if not should_include_file(item.path, params):
                    stats["files_skipped"] += 1
                    continue

                if item.size > max_bytes:
                    logger.debug(f"  Skipping large file: {item.path} ({item.size} bytes)")
                    stats["files_skipped"] += 1
                    continue

                try:
                    source_code = item.decoded_content.decode("utf-8", errors="ignore")
                    line_count = source_code.count("\n") + 1

                    # Determine language
                    lang = "python" if item.path.endswith(".py") else "javascript"

                    file_data = {
                        "repo": owner_repo,
                        "file_path": item.path,
                        "language": lang,
                        "source_code": source_code,
                        "lines": line_count,
                        "size_bytes": item.size,
                        "sha": item.sha,
                    }

                    # Save as JSON — replace / with __ for safe filename
                    safe_name = item.path.replace("/", "__")
                    out_file = out_dir / f"{safe_name}.json"

                    with open(out_file, "w", encoding="utf-8") as f:
                        json.dump(file_data, f, ensure_ascii=False)

                    stats["files_extracted"] += 1
                    stats["total_lines"] += line_count

                    # Progress log every 50 files
                    if stats["files_extracted"] % 50 == 0:
                        logger.info(
                            f"  {owner_repo}: {stats['files_extracted']} files extracted..."
                        )

                    # Rate limiting — be gentle with GitHub API
                    time.sleep(0.1)

                except Exception as e:
                    logger.warning(f"  Failed to extract {item.path}: {e}")
                    stats["errors"] += 1

    except GithubException as e:
        logger.error(f"GitHub API error for {owner_repo}: {e}")
        stats["errors"] += 1

    logger.info(
        f"Done {owner_repo}: "
        f"{stats['files_extracted']} files, "
        f"{stats['total_lines']:,} lines, "
        f"{stats['files_skipped']} skipped"
    )
    return stats


def main():
    logger.info("=" * 60)
    logger.info("DVC Stage 1: Repository Ingestion")
    logger.info("=" * 60)

    params = load_params()

    # GitHub token required
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN not set in environment!")
        logger.error("Create .env file with: GITHUB_TOKEN=ghp_your_token")
        sys.exit(1)

    gh = Github(token)

    # Verify token works
    try:
        user = gh.get_user()
        logger.info(f"GitHub authenticated as: {user.login}")
    except Exception as e:
        logger.error(f"GitHub authentication failed: {e}")
        sys.exit(1)

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    target_repos = params["ingestion"]["target_repos"]
    logger.info(f"Target repos: {len(target_repos)}")

    all_stats = []
    total_files = 0
    total_lines = 0

    for repo_url in target_repos:
        try:
            stats = ingest_single_repo(repo_url, gh, params)
            all_stats.append(stats)
            total_files += stats["files_extracted"]
            total_lines += stats["total_lines"]

            # Sleep between repos — avoid rate limit
            time.sleep(2)

        except Exception as e:
            logger.error(f"Failed to ingest {repo_url}: {e}")
            continue

    # Save ingestion report
    report = {
        "repos_ingested": len(all_stats),
        "total_files_extracted": total_files,
        "total_lines_of_code": total_lines,
        "repo_stats": all_stats,
    }

    report_path = REPORTS_DIR / "ingestion_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("=" * 60)
    logger.info("Stage 1 Complete!")
    logger.info(f"  Repos processed:  {len(all_stats)}/{len(target_repos)}")
    logger.info(f"  Total files:      {total_files:,}")
    logger.info(f"  Total lines:      {total_lines:,}")
    logger.info(f"  Report saved:     {report_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
