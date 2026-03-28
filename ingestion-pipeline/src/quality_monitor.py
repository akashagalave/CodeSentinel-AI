# ingestion-pipeline/src/quality_monitor.py
"""
Monitor false positive rate from user feedback.
Same pattern as drift_detection.py in AutoML Brain.

AutoML Brain: PSI drift > 0.2 → retrain.flag → training-cicd triggered
CodeSentinel: FP rate > 0.25 → reingest.flag → ingest-cicd triggered

FP rate = (thumbs_down ratings) / (total ratings) over last N days
Source: Langfuse user feedback scores
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.logger import get_logger

load_dotenv()
logger = get_logger("quality_monitor")

PARAMS_FILE = Path("ingestion-pipeline/params.yaml")
FLAG_FILE = Path("reingest.flag")


def get_fp_rate_from_langfuse(window_days: int) -> float:
    """
    Query Langfuse for user thumbs feedback.
    Returns false positive rate (0.0 to 1.0).
    """
    try:
        from langfuse import Langfuse

        lf = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )

        since = datetime.utcnow() - timedelta(days=window_days)
        scores = lf.get_scores(name="user_thumbs", from_timestamp=since, limit=500)

        if not scores.data:
            logger.info("No user feedback data found yet — returning 0.0")
            return 0.0

        thumbs_down = sum(1 for s in scores.data if s.value == -1)
        total = len(scores.data)
        fp_rate = thumbs_down / total

        logger.info(f"FP rate: {thumbs_down}/{total} = {fp_rate:.3f} (last {window_days} days)")
        return fp_rate

    except Exception as e:
        logger.warning(f"Langfuse query failed: {e} — returning 0.0")
        return 0.0


def main():
    logger.info("=" * 60)
    logger.info("Quality Monitor: False Positive Rate Check")
    logger.info("=" * 60)

    with open(PARAMS_FILE) as f:
        params = yaml.safe_load(f)

    threshold = params["quality"]["fp_rate_threshold"]
    window_days = params["monitoring"]["fp_rate_window_days"]

    fp_rate = get_fp_rate_from_langfuse(window_days)

    logger.info(f"FP rate:   {fp_rate:.3f}")
    logger.info(f"Threshold: {threshold}")

    if fp_rate > threshold:
        logger.warning(
            f"FP rate {fp_rate:.3f} EXCEEDS threshold {threshold} — "
            f"writing reingest.flag"
        )
        FLAG_FILE.write_text(json.dumps({
            "triggered_at": datetime.utcnow().isoformat(),
            "fp_rate": fp_rate,
            "threshold": threshold,
            "reason": "false_positive_rate_drift",
        }))
        logger.warning("reingest.flag written → ingest-cicd.yaml will trigger re-index")
    else:
        logger.info(f"FP rate healthy — no action needed")
        if FLAG_FILE.exists():
            FLAG_FILE.unlink()
            logger.info("Cleared old reingest.flag")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
