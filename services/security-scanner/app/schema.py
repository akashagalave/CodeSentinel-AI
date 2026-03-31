
from pydantic import BaseModel
from typing import Literal


class SecurityFinding(BaseModel):
    severity:       Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    line_start:     int
    line_end:       int
    file_path:      str
    description:    str
    fix_suggestion: str
    confidence:     float
    owasp_category: str = ""   
    cwe_id:         str = ""   
    finding_type:   str = "security"


class SecurityReviewResponse(BaseModel):
    findings:    list[SecurityFinding]
    cost_usd:    float
    latency_ms:  float
    tokens_used: int


class HealthResponse(BaseModel):
    status:  str = "healthy"
    service: str = "security-scanner"
