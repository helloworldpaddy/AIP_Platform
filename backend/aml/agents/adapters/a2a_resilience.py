"""A2A resilience settings and per-endpoint circuit breakers."""

from __future__ import annotations

import os

from ...config.agent_transport import AgentTransportConfig
from ...utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

_breakers: dict[str, CircuitBreaker] = {}


def load_a2a_circuit_config() -> CircuitBreakerConfig:
    threshold_raw = os.getenv("AML_A2A_CIRCUIT_FAILURE_THRESHOLD", "5")
    recovery_raw = os.getenv("AML_A2A_CIRCUIT_RECOVERY_SECONDS", "60")
    try:
        threshold = max(1, int(threshold_raw))
    except ValueError:
        threshold = 5
    try:
        recovery = max(1.0, float(recovery_raw))
    except ValueError:
        recovery = 60.0
    return CircuitBreakerConfig(
        failure_threshold=threshold,
        recovery_seconds=recovery,
    )


def circuit_breaker_for(agent_card_url: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
    cfg = config or load_a2a_circuit_config()
    key = agent_card_url.strip()
    breaker = _breakers.get(key)
    if breaker is None:
        breaker = CircuitBreaker(name=key, config=cfg)
        _breakers[key] = breaker
    return breaker


def reset_a2a_circuit_breakers() -> None:
    """Test helper — clear cached breakers."""
    _breakers.clear()


def a2a_timeout_seconds(transport_config: AgentTransportConfig | None = None) -> float:
    if transport_config is not None:
        return transport_config.a2a_timeout_seconds
    from ...config.agent_transport import load_agent_transport_config

    return load_agent_transport_config().a2a_timeout_seconds
