"""
QuantEdge AI — Retry + rate limiting helpers
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, TypeVar

from tenacity import retry, stop_after_attempt, wait_exponential

T = TypeVar("T")


def async_retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Simple tenacity-based retry decorator for async functions.
    """

    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=delay, min=delay, max=delay * (backoff ** max_attempts)),
    )


class _SimpleLimiter:
    """
    Minimal async limiter.
    It's intentionally simple (one-slot semaphore), enough to prevent
    unbounded bursts inside a single worker.
    """

    def __init__(self, concurrency: int = 1):
        self._sem = asyncio.Semaphore(concurrency)

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[None]:
        async with self._sem:
            yield None


# Global limiters used by fetchers
polygon_limiter = _SimpleLimiter(concurrency=1)
alpha_vantage_limiter = _SimpleLimiter(concurrency=1)
finnhub_limiter = _SimpleLimiter(concurrency=2)
fred_limiter = _SimpleLimiter(concurrency=2)
reddit_limiter = _SimpleLimiter(concurrency=1)
news_api_limiter = _SimpleLimiter(concurrency=1)

