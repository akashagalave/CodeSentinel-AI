# ragas_eval.py
# Root-level RAGAS quality gate — called by ingest-cicd.yaml
# Same as ingestion-pipeline/src/index_evaluation.py
# but runnable from project root

import json
import sys
from pathlib import Path

RESULTS_FILE = Path("reports/ragas_results.json")


def main():
    if not RESULTS_FILE.exists():
        print("ERROR: reports/ragas_results.json not found")
        print("Run: cd ingestion-pipeline && dvc repro")
        sys.exit(1)

    with open(RESULTS_FILE) as f:
        report = json.load(f)

    scores  = report.get("ragas_scores", {})
    passed  = report.get("passed", False)
    failures = report.get("failures", [])

    print("RAGAS Evaluation Results:")
    print(f"  faithfulness:      {scores.get('faithfulness', 0):.3f}")
    print(f"  context_precision: {scores.get('context_precision', 0):.3f}")
    print(f"  context_recall:    {scores.get('context_recall', 0):.3f}")
    print(f"  docs_indexed:      {scores.get('docs_indexed', 0):,}")

    if not passed:
        print("\nQUALITY GATE FAILED:")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)

    print("\n✓ Quality gate passed — index ready for production")


if __name__ == "__main__":
    main()