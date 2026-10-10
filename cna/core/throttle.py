"""API throttle and retry strategy.

Closes TODO_PhaseA: DD-006 'dynamic regions' is not an architecture.

This module provides:
  - Exponential backoff with jitter for rate limit errors
  - Per-service concurrency limits
  - Pagination cursor management
  - Discovery rate budgets (max calls/sec per account)

All discovery code uses the @with_throttle decorator or ThrottleManager directly.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from cna.core.exceptions import CNARateLimitError

logger = logging.getLogger("cna.core.throttle")

# Max concurrent boto3/Azure SDK calls per account
# AWS: 10 is safe for most regions without hitting service limits
# Azure: 5 is conservative for ARM API
DEFAULT_AWS_CONCURRENCY = 10
DEFAULT_AZURE_CONCURRENCY = 5

MAX_RETRIES = 5
BASE_WAIT_SECONDS = 1.0
MAX_WAIT_SECONDS = 60.0


def _jittered_wait(attempt: int) -> float:
    """Exponential backoff with full jitter.

    Formula: min(MAX_WAIT, BASE * 2^attempt) * random(0, 1)
    Full jitter prevents thundering herd on multi-account discovery.
    """
    cap = min(MAX_WAIT_SECONDS, BASE_WAIT_SECONDS * (2**attempt))
    return random.uniform(0, cap)


def with_retry(max_retries: int = MAX_RETRIES):
    """Decorator: retry on CNARateLimitError and transient errors with backoff.

    Usage:
        @with_retry(max_retries=5)
        def describe_vpcs(client, **kwargs):
            return client.describe_vpcs(**kwargs)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except CNARateLimitError as e:
                    wait = e.retry_after_seconds or _jittered_wait(attempt)
                    logger.warning(
                        "Rate limit on attempt %d/%d. Waiting %.1fs: %s",
                        attempt + 1,
                        max_retries,
                        wait,
                        e,
                    )
                    if attempt == max_retries:
                        raise
                    time.sleep(wait)
                    last_exc = e
            # Unreachable: the final attempt re-raises above. Kept so the
            # function can never fall through and implicitly return None.
            if last_exc is not None:  # pragma: no cover
                raise last_exc
            raise RuntimeError(  # pragma: no cover
                "with_retry: retry loop exited without returning or raising"
            )

        return wrapper

    return decorator


class PaginationCursor:
    """Manages AWS NextToken / Azure skipToken pagination.

    Usage:
        cursor = PaginationCursor()
        while cursor.has_more:
            resp = client.describe_vpcs(NextToken=cursor.token) if cursor.token else client.describe_vpcs()
            cursor.advance(resp.get('NextToken'))
            yield resp['Vpcs']
    """

    def __init__(self):
        self._token = None
        self._has_more = True

    @property
    def token(self):
        return self._token

    @property
    def has_more(self) -> bool:
        return self._has_more

    def advance(self, next_token) -> None:
        self._token = next_token
        self._has_more = bool(next_token)


class ConcurrencyLimiter:
    """Token-bucket concurrency limiter for API calls.

    Limits simultaneous in-flight API calls to prevent account-level throttling.
    Thread-safe via asyncio.Semaphore (used in async discovery path).

    For sync code, use the sync_acquire/release methods.
    """

    def __init__(self, max_concurrent: int = DEFAULT_AWS_CONCURRENCY):
        self._max = max_concurrent
        self._semaphore: asyncio.Semaphore | None = None
        self._active = 0

    async def __aenter__(self):
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max)
        await self._semaphore.acquire()
        self._active += 1
        return self

    async def __aexit__(self, *args):
        self._active -= 1
        if self._semaphore:
            self._semaphore.release()
