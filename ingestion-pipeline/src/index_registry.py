import os
import sys
from pathlib import Path

import dagshub
import mlflow
from mlflow.tracking import MlflowClient
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.logger import get_logger

load_dotenv()
logger = get_logger("index_registry")

REGISTERED_MODEL_NAME = "codesentinel-index"


def init_mlflow():

    dagshub.init(
        repo_owner=os.getenv("DAGSHUB_REPO_OWNER", "akashagalaveaaa1"),
        repo_name=os.getenv("DAGSHUB_REPO_NAME", "CodeSentinel-AI"),
        mlflow=True,
    )


def get_client() -> MlflowClient:
    init_mlflow()
    return MlflowClient()


def register_index(run_id: str, ragas_scores: dict) -> str:
   
    client = get_client()

    try:
        client.create_registered_model(REGISTERED_MODEL_NAME)
        logger.info(f"Created registered model: {REGISTERED_MODEL_NAME}")
    except Exception:
        pass  

    model_uri = f"runs:/{run_id}/artifacts"
    mv = mlflow.register_model(model_uri, REGISTERED_MODEL_NAME)

    client.set_model_version_tag(
        REGISTERED_MODEL_NAME, mv.version,
        "ragas_faithfulness",
        str(ragas_scores.get("faithfulness", 0)),
    )
    client.set_model_version_tag(
        REGISTERED_MODEL_NAME, mv.version,
        "ragas_precision",
        str(ragas_scores.get("context_precision", 0)),
    )

    logger.info(f"Registered index version: {mv.version}")
    return mv.version


def transition_to_production(version: str):

    client = get_client()
    client.transition_model_version_stage(
        name=REGISTERED_MODEL_NAME,
        version=version,
        stage="Production",
        archive_existing_versions=True,
    )
    logger.info(f"Index version {version} → Production ✓")


def transition_to_staging(version: str):
   
    client = get_client()
    client.transition_model_version_stage(
        name=REGISTERED_MODEL_NAME,
        version=version,
        stage="Staging",
    )
    logger.info(f"Index version {version} → Staging")


def get_production_version() -> str | None:
  
    client = get_client()
    try:
        versions = client.get_latest_versions(
            REGISTERED_MODEL_NAME, stages=["Production"]
        )
        if versions:
            return versions[0].version
        return None
    except Exception:
        return None