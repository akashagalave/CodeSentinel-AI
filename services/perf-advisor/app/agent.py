
import json
import os
import time
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.perf_advisor.app.prompts import PERF_SYSTEM, PERF_HUMAN
from services.perf_advisor.app.schema import PerfFinding
from services.perf_advisor.app.cost_tracker import (
    log_cost, compress_if_needed, count_tokens
)
from services.perf_advisor.app.config import settings

logger = get_logger("perf_agent")


def run_perf_advisor(
    diff: str,
    context_chunks: list[str],
) -> tuple[list[PerfFinding], float, int]:

    start = time.time()

    context = "\n\n---\n\n".join(context_chunks[:3]) if context_chunks else ""
    context = compress_if_needed(
        context,
        max_tokens=settings.max_tokens_per_call,
        model=settings.llm_model,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", PERF_SYSTEM),
        ("human", PERF_HUMAN),
    ])

    
    llm = ChatOpenAI(
        model=settings.llm_model,    
        temperature=0.1,
        api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY"),
    )

    try:
        response = (prompt | llm).invoke({
            "diff":    diff[:2500],
            "context": context,
        })

        content = response.content.strip()

        if content.startswith("```"):
            parts = content.split("```")
            content = parts[1]
            if content.startswith("json"):
                content = content[4:].strip()

        raw = json.loads(content)
        if isinstance(raw, dict):
            raw = raw.get("findings", [])

        findings = []
        for item in raw:
            try:
                f = PerfFinding(**item)
                if f.confidence >= settings.confidence_threshold:
                    findings.append(f)
            except Exception as e:
                logger.warning(f"Invalid finding: {e}")

        usage      = response.response_metadata.get("token_usage", {})
        tokens_in  = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        cost       = log_cost("perf-advisor", tokens_in, tokens_out, settings.llm_model)

        latency_ms = (time.time() - start) * 1000
        logger.info(f"Perf Advisor: {len(findings)} findings | ${cost:.5f} | {latency_ms:.0f}ms")
        return findings, cost, tokens_in + tokens_out

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return [], 0.0, 0
    except Exception as e:
        logger.error(f"Perf Advisor failed: {e}")
        return [], 0.0, 0
