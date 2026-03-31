import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    
    github_token: str = ""
    github_webhook_secret: str = ""

    
    orchestrator_url: str = "http://orchestrator-svc:8001"

    class Config:
        env_file = ".env"

settings = Settings()
