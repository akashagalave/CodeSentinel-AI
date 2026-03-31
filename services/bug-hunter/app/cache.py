import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from shared.logger import get_logger

logger = get_logger("bug_hunter_cache")

_cache: dict = {}
_hits = 0
_misses = 0


def initialize_cache(similarity_threshold: float = 0.92, max_size: int = 500):
    logger.info("Simple in-memory cache initialized")


def get_cached(key: str) -> dict | None:
    global _hits, _misses
    h = hashlib.md5(key.encode()).hexdigest()
    if h in _cache:
        _hits += 1
        logger.info(f"Cache HIT — hits={_hits} misses={_misses}")
        return _cache[h]
    _misses += 1
    return None


def set_cached(key: str, value: dict):
    h = hashlib.md5(key.encode()).hexdigest()
    _cache[h] = value
    if len(_cache) % 50 == 0:
        logger.info(f"Cache size: {len(_cache)}")