
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    results_file = Path("reports/ragas_results.json")

    if not results_file.exists():
        print("No ragas_results.json found — skipping auto-promotion")
        sys.exit(0)

    with open(results_file) as f:
        report = json.load(f)

    if not report.get("passed", False):
        print("RAGAS quality gate failed — NOT promoting to Production")
        print(f"Failures: {report.get('failures', [])}")
        sys.exit(0)

    scores = report.get("ragas_scores", {})
    print(f"RAGAS passed: faithfulness={scores.get('faithfulness', 0):.3f}")

  
    try:
        import dagshub
        import mlflow
        from mlflow.tracking import MlflowClient

        dagshub.init(
            repo_owner=os.getenv("DAGSHUB_REPO_OWNER", "akashagalaveaaa1"),
            repo_name=os.getenv("DAGSHUB_REPO_NAME", "CodeSentinel-AI"),
            mlflow=True,
        )

        client = MlflowClient()
        model_name = "codesentinel-index"

        versions = client.get_latest_versions(model_name, stages=["Staging"])
        if not versions:
            print("No Staging version found — nothing to promote")
            return

        version = versions[0].version
        client.transition_model_version_stage(
            name=model_name,
            version=version,
            stage="Production",
            archive_existing_versions=True,
        )
        print(f"Promoted index version {version} → Production ✓")

    except Exception as e:
        print(f"Auto-promotion failed: {e}")
        print("Run manually: python scripts/promote_index.py")


if __name__ == "__main__":
    main()