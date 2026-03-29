# services/orchestrator/app/graph.py
"""
LangGraph StateGraph — the orchestration brain.

Graph structure:
  START → retrieve_context → parallel_review → aggregate → post_review → END

parallel_review fires all 3 agents simultaneously using asyncio.gather.
Each node reads from ReviewState and writes back to it.
"""
import asyncio
import sys
import time
from pathlib import Path

import httpx
from langgraph.graph import StateGraph, START, END

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.orchestrator.app.state import ReviewState
from services.orchestrator.app.aggregator import aggregate_findings
from services.orchestrator.app.config import settings

logger = get_logger("orchestrator_graph")


# ── Node 1: Retrieve context ────────────────────────────────────

async def retrieve_context(state: ReviewState) -> ReviewState:
    """
    Call Retrieval Service to get top-5 similar code chunks.
    These chunks go to all 3 agents as context.
    """
    try:
        async with httpx.AsyncClient(
            timeout=settings.retrieval_timeout_seconds
        ) as client:
            resp = await client.post(
                f"{settings.retrieval_url}/search",
                json={
                    "query":      state["diff"][:1000],
                    "k":          settings.context_chunks_k,
                    "session_id": state["session_id"],
                },
            )
            data = resp.json()
            state["context_chunks"]   = data.get("chunks", [])
            state["context_metadata"] = data.get("metadata", [])
            logger.info(
                f"Retrieved {len(state['context_chunks'])} chunks "
                f"in {data.get('latency_ms', 0):.0f}ms"
            )
    except Exception as e:
        logger.error(f"Retrieval failed: {e} — continuing with empty context")
        state["context_chunks"]   = []
        state["context_metadata"] = []
        state["errors"].append(f"retrieval_error: {str(e)}")

    return state


# ── Node 2: Parallel review ─────────────────────────────────────

async def call_agent(
    client:      httpx.AsyncClient,
    url:         str,
    state:       ReviewState,
    agent_name:  str,
) -> tuple[str, list[dict], float]:
    """
    Call a single agent service.
    Returns (agent_name, findings, cost_usd).
    """
    try:
        resp = await client.post(
            f"{url}/review",
            json={
                "diff":           state["diff"],
                "context_chunks": state["context_chunks"],
                "session_id":     state["session_id"],
                "pr_number":      state["pr_number"],
                "repo":           state["repo"],
            },
        )

        if resp.status_code == 200:
            data     = resp.json()
            findings = data.get("findings", [])
            cost     = data.get("cost_usd", 0.0)
            logger.info(
                f"{agent_name}: {len(findings)} findings | "
                f"${cost:.4f} | {data.get('latency_ms', 0):.0f}ms"
            )
            return agent_name, findings, cost
        else:
            logger.error(f"{agent_name} returned HTTP {resp.status_code}")
            return agent_name, [], 0.0

    except httpx.TimeoutException:
        logger.error(f"{agent_name} timed out after {settings.agent_timeout_seconds}s")
        return agent_name, [], 0.0
    except Exception as e:
        logger.error(f"{agent_name} failed: {e}")
        return agent_name, [], 0.0


async def parallel_review(state: ReviewState) -> ReviewState:
    """
    Fire all 3 agents SIMULTANEOUSLY using asyncio.gather.

    Why asyncio.gather not sequential?
    Sequential: Bug Hunter 15s + Security 20s + Perf 10s = 45s total
    Parallel:   max(Bug Hunter 15s, Security 20s, Perf 10s) = 20s total
    Saves 25 seconds per review.
    """
    start = time.time()
    logger.info(f"Starting parallel review: {state['repo']}#{state['pr_number']}")

    async with httpx.AsyncClient(timeout=settings.agent_timeout_seconds) as client:
        # Fire all 3 simultaneously — asyncio.gather waits for ALL to complete
        results = await asyncio.gather(
            call_agent(client, settings.bug_hunter_url,       state, "bug-hunter"),
            call_agent(client, settings.security_scanner_url, state, "security-scanner"),
            call_agent(client, settings.perf_advisor_url,     state, "perf-advisor"),
            return_exceptions=True,   # Don't crash if one agent fails
        )

    total_cost = 0.0
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Agent exception: {result}")
            continue

        agent_name, findings, cost = result
        total_cost += cost

        if agent_name == "bug-hunter":
            state["bug_findings"] = findings
        elif agent_name == "security-scanner":
            state["security_findings"] = findings
        elif agent_name == "perf-advisor":
            state["perf_findings"] = findings

    state["total_cost_usd"]    = total_cost
    state["review_latency_ms"] = (time.time() - start) * 1000

    logger.info(
        f"Parallel review done: "
        f"{len(state['bug_findings'])} bugs + "
        f"{len(state['security_findings'])} security + "
        f"{len(state['perf_findings'])} perf | "
        f"${total_cost:.4f} | "
        f"{state['review_latency_ms']:.0f}ms"
    )
    return state


# ── Node 3: Aggregate ───────────────────────────────────────────

async def aggregate(state: ReviewState) -> ReviewState:
    """Merge + dedup + sort + build markdown."""
    result = aggregate_findings(
        bug_findings=state.get("bug_findings", []),
        security_findings=state.get("security_findings", []),
        perf_findings=state.get("perf_findings", []),
        repo=state["repo"],
        pr_number=state["pr_number"],
    )
    state["all_findings"]      = result["all_findings"]
    state["findings_markdown"] = result["findings_markdown"]
    state["has_critical"]      = result["has_critical"]
    return state


# ── Node 4: Post review ─────────────────────────────────────────

async def post_review(state: ReviewState) -> ReviewState:
    """Send final findings to GitHub Client Service."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.github_client_url}/post-review",
                json={
                    "repo":              state["repo"],
                    "pr_number":         state["pr_number"],
                    "head_sha":          state["head_sha"],
                    "findings":          state["all_findings"],
                    "findings_markdown": state["findings_markdown"],
                    "has_critical":      state["has_critical"],
                    "total_cost_usd":    state["total_cost_usd"],
                    "review_latency_ms": state["review_latency_ms"],
                    "session_id":        state["session_id"],
                },
            )
            data = resp.json()
            state["post_success"] = data.get("success", False)
            state["comment_url"]  = data.get("comment_url", "")
            state["check_run_id"] = data.get("check_run_id", 0)
            logger.info(
                f"Review posted: {state['repo']}#{state['pr_number']} | "
                f"comment={state['comment_url']} | "
                f"has_critical={state['has_critical']}"
            )
    except Exception as e:
        logger.error(f"Failed to post review: {e}")
        state["post_success"] = False
        state["errors"].append(f"post_error: {str(e)}")

    return state


# ── Build the LangGraph ─────────────────────────────────────────

def build_review_graph() -> StateGraph:
    """
    Build and compile the LangGraph StateGraph.
    Returns compiled graph ready to invoke.
    """
    graph = StateGraph(ReviewState)

    # Add nodes
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("parallel_review",  parallel_review)
    graph.add_node("aggregate",        aggregate)
    graph.add_node("post_review",      post_review)

    # Add edges — linear flow
    graph.add_edge(START,              "retrieve_context")
    graph.add_edge("retrieve_context", "parallel_review")
    graph.add_edge("parallel_review",  "aggregate")
    graph.add_edge("aggregate",        "post_review")
    graph.add_edge("post_review",      END)

    return graph.compile()


# Module-level compiled graph — built once at startup
review_graph = build_review_graph()
