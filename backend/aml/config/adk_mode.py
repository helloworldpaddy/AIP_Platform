"""ADK web runtime mode — hybrid in-process vs full orchestrator path."""

from __future__ import annotations

import os
from enum import Enum


class AdkMode(str, Enum):
    """How ``adk web`` hybrid callbacks execute a stage turn."""

    HYBRID = "hybrid"
    """Default: ADK LLM in-process; callbacks persist via ``run_lifecycle``."""

    ORCHESTRATOR = "orchestrator"
    """Delegate to :class:`Orchestrator.trigger_agent` (respects transport + A2A)."""


def load_adk_mode() -> AdkMode:
    raw = os.getenv("AML_ADK_MODE", AdkMode.HYBRID.value)
    normalized = raw.strip().lower().replace("-", "_")
    try:
        return AdkMode(normalized)
    except ValueError as err:
        raise ValueError(
            f"invalid AML_ADK_MODE {raw!r}; expected hybrid or orchestrator"
        ) from err
