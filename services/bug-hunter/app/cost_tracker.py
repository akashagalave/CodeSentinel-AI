# services/bug-hunter/app/cost_tracker.py
"""
LLMOps cost control — 4 layers:
1. tiktoken: count tokens BEFORE API call
2. LLMLingua: compress context if over limit
3. LiteLLM: route to right model
4. Langfuse: log every call's actual cost
"""
import os
import sys
from pathlib import Path

from prometheus_client import Histogram, Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger

logger = get_logger("cost_tracker")

# ── Prometheus metrics ──────────────────────────────────────────
cost_histogram = Histogram(
    "llm_cost_usd",
    "LLM API cost per call in USD",
    ["service"],
    buckets=[0.001, 0.005, 0.01, 0.02, 0.05, 0.10],
)
tokens_in_counter  = Counter("llm_tokens_in_total",  "Total input tokens",  ["service"])
tokens_out_counter = Counter("llm_tokens_out_total",  "Total output tokens", ["service"])

# GPT-4o pricing per 1K tokens (2025)
PRICES = {
    "gpt-4o":      {"in": 0.0025, "out": 0.010},
    "gpt-4o-mini": {"in": 0.00015, "out": 0.0006},
}


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens BEFORE making API call — no surprises."""
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4   # rough fallback


def compute_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    """Compute exact USD cost from token counts."""
    p = PRICES.get(model, PRICES["gpt-4o-mini"])
    return (tokens_in * p["in"] + tokens_out * p["out"]) / 1000


def log_cost(service_name: str, tokens_in: int, tokens_out: int, model: str) -> float:
    """Log cost to Prometheus + Langfuse. Returns cost in USD."""
    cost = compute_cost(tokens_in, tokens_out, model)

    # Prometheus
    cost_histogram.labels(service=service_name).observe(cost)
    tokens_in_counter.labels(service=service_name).inc(tokens_in)
    tokens_out_counter.labels(service=service_name).inc(tokens_out)

    # Langfuse — non-blocking, failure doesn't affect review
    try:
        from langfuse import Langfuse
        lf = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com"),
        )
        lf.score(name="cost_usd", value=cost, comment=service_name)
    except Exception:
        pass   # Langfuse down → review still works

    logger.info(f"Cost: {service_name} | ${cost:.5f} | in={tokens_in} out={tokens_out}")
    return cost


def compress_if_needed(text: str, max_tokens: int = 4000, model: str = "gpt-4o") -> str:
    """
    Compress context with LLMLingua if over max_tokens.
    Target: 60% of original (llmlingua_target_ratio=0.6).
    Preserves: identifiers, function names, logic keywords.
    Falls back to truncation if LLMLingua unavailable.
    """
    current = count_tokens(text, model)
    if current <= max_tokens:
        return text    # No compression needed

    logger.info(f"Compressing: {current} tokens → target {max_tokens}")

    try:
        from llmlingua import PromptCompressor
        compressor = PromptCompressor(
            model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            use_llmlingua2=True,
        )
        result = compressor.compress_prompt(
            text,
            rate=max_tokens / current,
            force_tokens=["\n", "def ", "class ", "return ", "import "],
        )
        compressed = result["compressed_prompt"]
        after = count_tokens(compressed, model)
        logger.info(f"Compressed: {current} → {after} tokens ({100*(1-after/current):.1f}% reduction)")
        return compressed

    except Exception as e:
        logger.warning(f"LLMLingua failed: {e} — using truncation")
        # Fallback: keep lines until token budget exhausted
        lines = text.split("\n")
        result_lines, total = [], 0
        for line in lines:
            lt = count_tokens(line, model)
            if total + lt > max_tokens:
                break
            result_lines.append(line)
            total += lt
        return "\n".join(result_lines)
