# services/orchestrator/app/schema.py
from pydantic import BaseModel
from typing import Optional


class ReviewRequest(BaseModel):
    repo:       str
    pr_number:  int
    diff:       str
    head_sha:   str
    session_id: str = ""


class ReviewResult(BaseModel):
    repo:              str
    pr_number:         int
    session_id:        str
    total_findings:    int
    critical_count:    int
    high_count:        int
    medium_count:      int
    low_count:         int
    has_critical:      bool
    total_cost_usd:    float
    review_latency_ms: float
    findings_markdown: str


class HealthResponse(BaseModel):
    status:  str = "healthy"
    service: str = "orchestrator"
