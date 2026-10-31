from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class ProviderError(Exception):
    """Error from a market data provider. `retryable` marks transient failures (timeouts, 429, 5xx)."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 0.5
    max_delay: float = 8.0


def is_retryable(exc: Exception) -> bool:
    if isinstance(exc, ProviderError):
        return exc.retryable
    return isinstance(exc, (TimeoutError, ConnectionError))


def call_with_retry(
    fn: Callable[[], T],
    policy: RetryPolicy = RetryPolicy(),
    *,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
) -> tuple[T, int]:
    """Call `fn`, retrying transient failures with exponential backoff and full jitter:
    delay = U(0, min(max_delay, base * 2**attempt)). Returns (result, retries_used).
    Non-retryable errors and the final failure propagate unchanged."""
    retries = 0
    for attempt in range(policy.max_attempts):
        try:
            return fn(), retries
        except Exception as exc:
            if not is_retryable(exc) or attempt == policy.max_attempts - 1:
                exc.retries_used = retries  # type: ignore[attr-defined]  # so callers can still count them
                raise
            retries += 1
            sleep(rng() * min(policy.max_delay, policy.base_delay * 2**attempt))
    raise RuntimeError("unreachable")  # pragma: no cover


class RateLimiter:
    """Enforces a minimum spacing between provider calls (requests per second)."""

    def __init__(self, per_second: float, clock=time.monotonic, sleep=time.sleep) -> None:
        self.interval = 1.0 / per_second if per_second > 0 else 0.0
        self._clock, self._sleep = clock, sleep
        self._next = 0.0

    def acquire(self) -> None:
        now = self._clock()
        if now < self._next:
            self._sleep(self._next - now)
            now = self._next
        self._next = now + self.interval
