
import json
import os
import time
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger
from services.bug_hunter.app.prompts import BUG_SYSTEM, BUG_HUMAN
from services.bug_hunter.app.schema import BugFinding
from services.bug_hunter.app.cost_tracker import log_cost, compress_if_needed, count_tokens
from services.bug_hunter.app.config import settings

logger = get_logger("bug_hunter_agent")


def run_bug_hunter(
    diff: str,
    context_chunks: list[str],
) -> tuple[list[BugFinding], float, int]:

    start = time.time()

    if context_chunks:
        context = "\n\n--- Similar function from codebase ---\n\n".join(
            context_chunks[:5]
        )
    else:
        context = "No similar functions found in codebase."

  
    context = compress_if_needed(
        context,
        max_tokens=settings.max_tokens_per_call,
        model=settings.llm_model,
    )


    diff_tokens    = count_tokens(diff[:3000], settings.llm_model)
    context_tokens = count_tokens(context, settings.llm_model)
    logger.info(f"Pre-flight: diff={diff_tokens} context={context_tokens} tokens")

  
    prompt = ChatPromptTemplate.from_messages([
        ("system", BUG_SYSTEM),
        ("human", BUG_HUMAN),
    ])

  
    llm = ChatOpenAI(
        model=settings.llm_model,
        temperature=0.1,       
        api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY"),
    )

    try:
        response = (prompt | llm).invoke({
            "diff":    diff[:3000],   
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
                f = BugFinding(**item)
                if f.confidence >= settings.confidence_threshold:
                    findings.append(f)
            except Exception as e:
                logger.warning(f"Invalid finding format: {e} — skipping")

        usage      = response.response_metadata.get("token_usage", {})
        tokens_in  = usage.get("prompt_tokens", diff_tokens + context_tokens)
        tokens_out = usage.get("completion_tokens", 100)
        cost       = log_cost("bug-hunter", tokens_in, tokens_out, settings.llm_model)

        latency_ms = (time.time() - start) * 1000
        logger.info(
            f"Bug Hunter: {len(findings)} findings | "
            f"${cost:.5f} | {latency_ms:.0f}ms"
        )
        return findings, cost, tokens_in + tokens_out

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error from GPT-4o: {e}\nResponse: {content[:200]}")
        return [], 0.0, 0

    except Exception as e:
        logger.error(f"Bug Hunter agent failed: {e}")
        return [], 0.0, 0
