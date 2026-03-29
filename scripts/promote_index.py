# scripts/promote_index.py
# Manual CLI to promote a specific index version
# Usage: python scripts/promote_index.py --version 3

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="Promote index version to Production")
    parser.add_argument("--version", required=True, help="Version number to promote")
    parser.add_argument("--stage", default="Production", help="Target stage")
    args = parser.parse_args()

    try:
        import dagshub
        import mlflow
        from mlflow.tracking import MlflowClient

        dagshub.init(
            repo_owner=os.getenv("DAGSHUB_REPO_OWNER", "akashagalaveaaa1"),
            repo_name=os.getenv("DAGSHUB_REPO_NAME", "CodeSentinel-AI"),
            mlflow=True,
        )

        client   = MlflowClient()
        model_name = "codesentinel-index"

        client.transition_model_version_stage(
            name=model_name,
            version=args.version,
            stage=args.stage,
            archive_existing_versions=True,
        )
        print(f"Index version {args.version} → {args.stage} ✓")

    except Exception as e:
        print(f"Promotion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()