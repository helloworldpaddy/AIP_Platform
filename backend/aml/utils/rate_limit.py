"""Rate-limit / retry helpers (spec §3.C — Performance & Reliability).

Wraps any async callable in:

    * Exponential backoff with full jitter
    * A bounded retry budget
    * Recognition of provider-specific rate-limit signals
        - google.api_core.exceptions.ResourceExhausted
        - google.api_core.exceptions.ServiceUnavailable / DeadlineExceeded
        - HTTP 429 / 503 (any object exposing `.status_code`)
        - Generic `RateLimitError` (some SDKs)

The retry decision is centralised in `is_retryable_error` so adding a new
provider only changes one place.
"""

from __future__ import annotations

import asyncio
import logging
import random
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


def _classify(err: BaseException) -> bool:
    cls_name = err.__class__.__name__
    if cls_name in {
        "ResourceExhausted",
        "ServiceUnavailable",
        "DeadlineExceeded",
        "TooManyRequests",
        "RateLimitError",
    }:
        return True
    status = getattr(err, "status_code", None) or getattr(err, "code", None)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    cls_module = getattr(err.__class__, "__module__", "")
    if cls_module.startswith("httpx") and cls_name in {
        "TimeoutException",
        "ConnectError",
        "ReadError",
        "NetworkError",
        "RemoteProtocolError",
    }:
        return True
    return False


def is_retryable_error(err: BaseException) -> bool:
    """True if `err` represents a transient failure worth retrying."""
    return _classify(err)


class RetryExhausted(RuntimeError):
    def __init__(self, attempts: int, last_error: BaseException) -> None:
        super().__init__(
            f"retries exhausted after {attempts} attempts: "
            f"{last_error.__class__.__name__}: {last_error}"
        )
        self.attempts = attempts
        self.last_error = last_error


async def call_with_retry(
    fn: Callable[..., Awaitable[T]],
    /,
    *args: Any,
    max_attempts: int = 5,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 30.0,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
    **kwargs: Any,
) -> T:
    """Invoke `fn(*args, **kwargs)` with exponential backoff + jitter.

    Non-retryable exceptions propagate immediately; retryable ones surface as
    `RetryExhausted` only after `max_attempts` failed tries.
    """
    last: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as err:  # noqa: BLE001 — we re-classify below
            last = err
            if not is_retryable_error(err) or attempt == max_attempts:
                if not is_retryable_error(err):
                    raise
                break
            # full-jitter exponential backoff
            cap = min(max_delay_seconds, base_delay_seconds * (2 ** (attempt - 1)))
            delay = random.uniform(0, cap)
            if on_retry is not None:
                on_retry(attempt, err, delay)
            else:
                log.warning(
                    "retry attempt=%d delay=%.2fs error=%s: %s",
                    attempt,
                    delay,
                    err.__class__.__name__,
                    err,
                )
            await asyncio.sleep(delay)

    assert last is not None
    raise RetryExhausted(max_attempts, last)


def retryable(
    *,
    max_attempts: int = 5,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 30.0,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator form of `call_with_retry`."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await call_with_retry(
                fn,
                *args,
                max_attempts=max_attempts,
                base_delay_seconds=base_delay_seconds,
                max_delay_seconds=max_delay_seconds,
                **kwargs,
            )

        return wrapper

    return decorator
