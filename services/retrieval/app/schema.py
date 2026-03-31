
from pydantic import BaseModel


class SearchRequest(BaseModel):
    query:      str
    k:          int = 5
    session_id: str = ""


class SearchResponse(BaseModel):
    chunks:     list[str]
    metadata:   list[dict]
    latency_ms: float


class HealthResponse(BaseModel):
    status:  str = "healthy"
    service: str = "retrieval"
    docs_count: int = 0
