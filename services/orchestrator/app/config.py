
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    
    retrieval_url:        str = "http://localhost:8002"
    bug_hunter_url:       str = "http://localhost:8003"
    security_scanner_url: str = "http://localhost:8004"
    perf_advisor_url:     str = "http://localhost:8005"
    github_client_url:    str = "http://localhost:8006"

 
    agent_timeout_seconds:     int = 45
    retrieval_timeout_seconds: int = 10

   
    context_chunks_k:     int = 5      
    min_confidence:       float = 0.75

    class Config:
        env_file = ".env"


settings = Settings()
