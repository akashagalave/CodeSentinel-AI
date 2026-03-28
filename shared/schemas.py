# shared/schemas.py
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, field_validator


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"


class BugFinding(BaseModel):
    severity:       Severity
    line_start:     int
    line_end:       int
    file_path:      str
    description:    str
    fix_suggestion: str
    confidence:     float
    category:       str = "logic_error"
    finding_type:   str = "bug"

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class SecurityFinding(BaseModel):
    severity:       Severity
    line_start:     int
    line_end:       int
    file_path:      str
    description:    str
    fix_suggestion: str
    confidence:     float
    owasp_category: str = ""
    cwe_id:         str = ""
    finding_type:   str = "security"

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class PerfFinding(BaseModel):
    severity:         Severity
    line_start:       int
    line_end:         int
    file_path:        str
    description:      str
    fix_suggestion:   str
    confidence:       float
    estimated_impact: str = "medium"
    finding_type:     str = "performance"

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class SearchRequest(BaseModel):
    query:      str
    k:          int = 5
    session_id: str = ""


class SearchResponse(BaseModel):
    chunks:     list[str]
    metadata:   list[dict]
    latency_ms: float


class AgentReviewRequest(BaseModel):
    diff:           str
    context_chunks: list[str]
    session_id:     str = ""
    pr_number:      int = 0
    repo:           str = ""


class BugReviewResponse(BaseModel):
    findings:    list[BugFinding]
    cost_usd:    float
    latency_ms:  float
    tokens_used: int


class SecurityReviewResponse(BaseModel):
    findings:    list[SecurityFinding]
    cost_usd:    float
    latency_ms:  float
    tokens_used: int


class PerfReviewResponse(BaseModel):
    findings:    list[PerfFinding]
    cost_usd:    float
    latency_ms:  float
    tokens_used: int


class PostReviewRequest(BaseModel):
    repo:              str
    pr_number:         int
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


class PRReviewJob(BaseModel):
    repo:       str
    pr_number:  int
    diff:       str
    head_sha:   str
    session_id: str = ""


class WebhookResponse(BaseModel):
    status:    str
    pr_number: int = 0
    repo:      str = ""
    message:   str = ""


class HealthResponse(BaseModel):
    status:  str = "healthy"
    service: str = ""
    version: str = "1.0.0"