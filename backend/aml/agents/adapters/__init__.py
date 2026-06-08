"""Agent execution adapters — switch in-process vs A2A without changing orchestrator phases."""

from .a2a import A2aAdapter, A2aAdapterError, A2aCircuitOpenError
from .factory import build_execution_ports
from .in_process import InProcessAdapter

__all__ = [
    "A2aAdapter",
    "A2aAdapterError",
    "A2aCircuitOpenError",
    "InProcessAdapter",
    "build_execution_ports",
]
