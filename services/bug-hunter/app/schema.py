
from pydantic import BaseModel
from typing import Literal


class BugFinding(BaseModel):
    severity:       Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    line_start:     int
    line_end:       int
    file_path:      str
    description:    str
    fix_suggestion: str
    confidence:     float
    category:       str = "logic_error"
    finding_type:   str = "bug"


class BugReviewResponse(BaseModel):
    findings:    list[BugFinding]
    cost_usd:    float
    latency_ms:  float
    tokens_used: int


class HealthResponse(BaseModel):
    status:  str = "healthy"
    service: str = "bug-hunter"
