# services/gateway/app/config.py
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""

    # Orchestrator URL — gateway calls this after webhook received
    orchestrator_url: str = "http://orchestrator-svc:8001"

    class Config:
        env_file = ".env"

settings = Settings()
