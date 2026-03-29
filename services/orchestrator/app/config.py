# services/orchestrator/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Agent service URLs — internal K8s DNS in prod, localhost in dev
    retrieval_url:        str = "http://localhost:8002"
    bug_hunter_url:       str = "http://localhost:8003"
    security_scanner_url: str = "http://localhost:8004"
    perf_advisor_url:     str = "http://localhost:8005"
    github_client_url:    str = "http://localhost:8006"

    # Timeouts
    agent_timeout_seconds:     int = 45
    retrieval_timeout_seconds: int = 10

    # Behaviour
    context_chunks_k:     int = 5      # top-5 from retrieval
    min_confidence:       float = 0.75

    class Config:
        env_file = ".env"


settings = Settings()
