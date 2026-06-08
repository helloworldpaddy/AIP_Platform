"""Unit tests for A2A circuit breaker (Sprint 5)."""

from __future__ import annotations

import time

import pytest

from backend.aml.agents.adapters.a2a_resilience import (
    circuit_breaker_for,
    load_a2a_circuit_config,
    reset_a2a_circuit_breakers,
)
from backend.aml.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
)


@pytest.fixture(autouse=True)
def _reset_breakers():
    reset_a2a_circuit_breakers()
    yield
    reset_a2a_circuit_breakers()


def test_circuit_opens_after_threshold():
    breaker = CircuitBreaker(
        name="test",
        config=CircuitBreakerConfig(failure_threshold=3, recovery_seconds=30),
    )
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.ensure_allow()


def test_circuit_recovers_after_timeout():
    breaker = CircuitBreaker(
        name="test",
        config=CircuitBreakerConfig(failure_threshold=1, recovery_seconds=0.01),
    )
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    time.sleep(0.02)
    assert breaker.allow_request() is True
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


def test_load_circuit_config_from_env(monkeypatch):
    monkeypatch.setenv("AML_A2A_CIRCUIT_FAILURE_THRESHOLD", "2")
    monkeypatch.setenv("AML_A2A_CIRCUIT_RECOVERY_SECONDS", "45")
    cfg = load_a2a_circuit_config()
    assert cfg.failure_threshold == 2
    assert cfg.recovery_seconds == 45.0


def test_registry_reuses_breaker_per_url():
    a = circuit_breaker_for("http://ia:8101/.well-known/agent-card.json")
    b = circuit_breaker_for("http://ia:8101/.well-known/agent-card.json")
    assert a is b
