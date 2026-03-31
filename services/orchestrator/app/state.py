
from typing import TypedDict, Optional


class ReviewState(TypedDict):
    
    repo:       str
    pr_number:  int
    diff:       str
    head_sha:   str
    session_id: str

    context_chunks: list[str]
    context_metadata: list[dict]

    bug_findings:      list[dict]
    security_findings: list[dict]
    perf_findings:     list[dict]

    all_findings:       list[dict]
    findings_markdown:  str
    has_critical:       bool
    total_cost_usd:     float
    review_latency_ms:  float

    post_success:    bool
    comment_url:     str
    check_run_id:    int

    
    errors: list[str]
