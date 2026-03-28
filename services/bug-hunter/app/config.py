# services/bug-hunter/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key:      str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host:       str = "https://us.cloud.langfuse.com"

    llm_model:               str   = "gpt-4o"
    max_tokens_per_call:     int   = 6000
    confidence_threshold:    float = 0.75
    cache_similarity:        float = 0.92
    llmlingua_target_ratio:  float = 0.6

    class Config:
        env_file = ".env"

settings = Settings()
