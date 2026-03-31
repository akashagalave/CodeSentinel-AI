
import os
import sys
from pathlib import Path
from prometheus_client import Histogram, Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger

logger = get_logger("perf_cost_tracker")

cost_histogram     = Histogram("llm_cost_usd", "LLM cost", ["service"],
                               buckets=[0.001, 0.005, 0.01, 0.02, 0.05, 0.10])
tokens_in_counter  = Counter("llm_tokens_in_total",  "Input tokens",  ["service"])
tokens_out_counter = Counter("llm_tokens_out_total", "Output tokens", ["service"])

PRICES = {
    "gpt-4o":      {"in": 0.0025,  "out": 0.010},
    "gpt-4o-mini": {"in": 0.00015, "out": 0.0006},
}


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def compute_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    p = PRICES.get(model, PRICES["gpt-4o-mini"])
    return (tokens_in * p["in"] + tokens_out * p["out"]) / 1000


def log_cost(service_name: str, tokens_in: int, tokens_out: int, model: str) -> float:
    cost = compute_cost(tokens_in, tokens_out, model)
    cost_histogram.labels(service=service_name).observe(cost)
    tokens_in_counter.labels(service=service_name).inc(tokens_in)
    tokens_out_counter.labels(service=service_name).inc(tokens_out)
    try:
        from langfuse import Langfuse
        lf = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com"),
        )
        lf.score(name="cost_usd", value=cost, comment=service_name)
    except Exception:
        pass
    logger.info(f"Cost: {service_name} | ${cost:.5f} | in={tokens_in} out={tokens_out}")
    return cost


def compress_if_needed(text: str, max_tokens: int = 4000, model: str = "gpt-4o-mini") -> str:
    current = count_tokens(text, model)
    if current <= max_tokens:
        return text
    lines = text.split("\n")
    result_lines, total = [], 0
    for line in lines:
        lt = count_tokens(line, model)
        if total + lt > max_tokens:
            break
        result_lines.append(line)
        total += lt
    return "\n".join(result_lines)