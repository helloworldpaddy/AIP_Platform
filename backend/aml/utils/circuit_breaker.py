"""Simple circuit breaker for remote A2A stage calls (Sprint 5)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and calls are fast-failed."""


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_seconds: float = 60.0


class CircuitBreaker:
    """Count consecutive failures; open circuit until recovery window elapses."""

    def __init__(self, *, name: str, config: CircuitBreakerConfig) -> None:
        self._name = name
        self._config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def allow_request(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if self._opened_at is None:
                return False
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._config.recovery_seconds:
                self._state = CircuitState.HALF_OPEN
                log.info(
                    "circuit.half_open name=%s after=%.1fs",
                    self._name,
                    elapsed,
                )
                return True
            return False
        # half_open: allow one probe
        return True

    def ensure_allow(self) -> None:
        if not self.allow_request():
            raise CircuitOpenError(
                f"circuit open for {self._name!r}; "
                f"retry after {self._config.recovery_seconds}s"
            )

    def record_success(self) -> None:
        if self._state != CircuitState.CLOSED:
            log.info("circuit.closed name=%s", self._name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._state == CircuitState.HALF_OPEN:
            self._trip()
            return
        if self._failure_count >= self._config.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        if self._state != CircuitState.OPEN:
            log.warning(
                "circuit.open name=%s failures=%s threshold=%s",
                self._name,
                self._failure_count,
                self._config.failure_threshold,
            )
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None
