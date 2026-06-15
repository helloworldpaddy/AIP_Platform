"""AML investigation host agent — A2A front door to the orchestrator (Sprint 7)."""

from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.a2a.converters.request_converter import A2A_METADATA_KEY

from agents.rag_agent.config.settings import get_settings

from ..adk_runner import build_llm_agent
from .analyst_context import reset_bound_analyst_context, set_analyst_context
from .host_tools import HOST_AGENT_TOOLS
from .metadata import parse_analyst_id_from_metadata

log = logging.getLogger(__name__)

AML_HOST_INSTRUCTION = """
You are the AML Investigation Assistant — the analyst's conversational front door
to the production workflow orchestrator.

Rules (non-negotiable):
- NEVER invent case facts, run statuses, or gate outcomes. Call tools for truth.
- ALL workflow mutations go through the provided tools — you do not change state
  directly. The orchestrator enforces gates, idempotency, and audit trails.
- Every mutating tool requires analyst identity in A2A metadata (`aml.analyst_id`).
- Hub-and-spoke only: you trigger stages via the orchestrator; do not call stage
  agents directly.

Stages (use exact enum values with `trigger_workflow_stage`):
  INITIAL_ASSESSMENT, TRANSACTION_ENRICHMENT, DUE_DILIGENCE, CASE_ANALYSIS

Typical flow:
1. `get_case_state` when the analyst asks about progress or blockers.
2. `trigger_workflow_stage` to run the next appropriate stage.
3. If `requires_review` is true, summarise output and wait for approval intent.
4. Prefer `approve_awaiting_review_run(case_number, stage)` for HITL — do not
   truncate run IDs. Use `approve_agent_run` only with the full 36-char run_id
   from `get_case_state` or `trigger_workflow_stage` tool responses.
5. `reject_agent_run` for rejections (full run_id only).
6. `verify_case_party` then `resolve_human_gate` when parties must be verified.

When a trigger is gate-blocked, explain the blocking gate and suggest the analyst
action (verify parties, resolve gate, etc.) using the structured error fields.
If approve fails because the run is already APPROVED, call `get_case_state` and
confirm success — the analyst may have approved via the case UI already.
Be terse, factual, and cite run ids / gate ids from tool responses.
""".strip()


async def bind_analyst_from_a2a_metadata(
    callback_context: CallbackContext,
) -> None:
    """Read analyst identity from A2A request metadata into task-local context."""
    inv = callback_context.get_invocation_context()
    custom = inv.run_config.custom_metadata or {}
    a2a_meta = custom.get(A2A_METADATA_KEY)
    analyst_id = parse_analyst_id_from_metadata(a2a_meta)
    if analyst_id is None:
        log.warning("aml.host missing analyst_id in A2A metadata")
        return
    set_analyst_context(analyst_id)


async def reset_analyst_from_a2a_metadata(
    callback_context: CallbackContext,
) -> None:
    reset_bound_analyst_context()


def build_aml_host_agent() -> LlmAgent:
    """Construct the AML host agent (orchestrator tools only, no stage LLM tools)."""
    return build_llm_agent(
        name="aml_host",
        instruction=AML_HOST_INSTRUCTION,
        model=get_settings().gemini.generation_model,
        tools=list(HOST_AGENT_TOOLS),
        temperature=0.1,
        description="AML Investigation Assistant — orchestrator front door (A2A).",
        before_agent_callback=bind_analyst_from_a2a_metadata,
        after_agent_callback=reset_analyst_from_a2a_metadata,
    )
