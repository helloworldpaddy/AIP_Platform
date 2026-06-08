"""Invoke the production orchestrator from ADK web (all stages)."""

from __future__ import annotations

import json
import logging
from typing import Any

from ...models.enums import AgentName
from ...models.state import AgentRun
from .bootstrap import ensure_runtime_ready
from .case_resolver import load_case_by_number, parse_case_number
from .orchestrator_client import build_runtime_orchestrator

log = logging.getLogger(__name__)


def _normalize_case_number(case_number: str) -> str | None:
    case_number = case_number.strip().upper()
    if parse_case_number(case_number):
        return case_number
    if case_number.startswith("AML-"):
        return case_number
    return None


async def invoke_orchestrator_stage(
    *,
    case_number: str,
    agent_name: AgentName,
    triggered_by: str = "adk_web",
    extra_input: dict[str, Any] | None = None,
) -> AgentRun:
    """Run one AML stage through the orchestrator (in-process or A2A transport)."""
    await ensure_runtime_ready()
    normalized = _normalize_case_number(case_number)
    if normalized is None:
        raise ValueError(f"invalid case_number: {case_number!r}")

    case = await load_case_by_number(normalized)
    payload = {"source": triggered_by, **(extra_input or {})}
    orch = build_runtime_orchestrator()
    run = await orch.trigger_agent(
        case_id=case.id,
        agent_name=agent_name,
        triggered_by=triggered_by,
        extra_input=payload,
    )
    log.info(
        "runtime.orchestrator_invoke.done agent=%s case=%s run_id=%s status=%s",
        agent_name.value,
        normalized,
        run.id,
        run.status.value,
    )
    return run


def format_orchestrator_run_for_chat(run: AgentRun) -> str:
    """User-visible chat text after orchestrator mode (mirrors hybrid output shape)."""
    output = run.output_payload or {}
    reasoning = run.reasoning or ""
    parts: list[str] = []
    if reasoning.strip():
        parts.append(reasoning.strip())
    parts.append(
        f"\n\n**Orchestrator run** `{run.id}` — status `{run.status.value}`"
    )
    if output:
        parts.append(
            "\n```json\n"
            + json.dumps(output, indent=2, default=str)
            + "\n```"
        )
    return "\n".join(parts).strip()
