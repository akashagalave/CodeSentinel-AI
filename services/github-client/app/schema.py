
from pydantic import BaseModel


class PostReviewRequest(BaseModel):
    repo:              str
    pr_number:         int
    head_sha:          str
    findings:          list[dict]
    findings_markdown: str
    has_critical:      bool
    total_cost_usd:    float
    review_latency_ms: float
    session_id:        str = ""


class PostReviewResponse(BaseModel):
    success:      bool
    comment_url:  str = ""
    check_run_id: int = 0


class HealthResponse(BaseModel):
    status:  str = "healthy"
    service: str = "github-client"
