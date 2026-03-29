# services/orchestrator/app/state.py
"""
ReviewState — shared state object passed through LangGraph nodes.
Every node reads from and writes to this state.
TypedDict keeps it type-safe.
"""
from typing import TypedDict, Optional


class ReviewState(TypedDict):
    # Input — set by Orchestrator at start
    repo:       str
    pr_number:  int
    diff:       str
    head_sha:   str
    session_id: str

    # Set by retrieve_context node
    context_chunks: list[str]
    context_metadata: list[dict]

    # Set by parallel_review node
    bug_findings:      list[dict]
    security_findings: list[dict]
    perf_findings:     list[dict]

    # Set by aggregate node
    all_findings:       list[dict]
    findings_markdown:  str
    has_critical:       bool
    total_cost_usd:     float
    review_latency_ms:  float

    # Set by post_review node
    post_success:    bool
    comment_url:     str
    check_run_id:    int

    # Error tracking
    errors: list[str]
