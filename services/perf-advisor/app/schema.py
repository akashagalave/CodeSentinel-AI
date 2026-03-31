
from pydantic import BaseModel
from typing import Literal


class PerfFinding(BaseModel):
    severity:         Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    line_start:       int
    line_end:         int
    file_path:        str
    description:      str
    fix_suggestion:   str
    confidence:       float
    estimated_impact: str = "medium"  
    finding_type:     str = "performance"


class PerfReviewResponse(BaseModel):
    findings:    list[PerfFinding]
    cost_usd:    float
    latency_ms:  float
    tokens_used: int


class HealthResponse(BaseModel):
    status:  str = "healthy"
    service: str = "perf-advisor"
