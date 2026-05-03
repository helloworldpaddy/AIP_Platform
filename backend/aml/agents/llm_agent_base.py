"""Common base for LLM-driven agents (**Google ADK 1.x**).

Concrete subclasses declare:

* ``name`` — :class:`backend.aml.models.enums.AgentName`
* ``instruction`` — system prompt (see ``prompts.py``)
* ``tool_names`` — keys into :data:`backend.aml.agents.tools.ADK_TOOLS`
  (each wrapped as :class:`google.adk.tools.FunctionTool`)
* ``requires_review``, ``build_user_prompt``, optional ``next_gates``

The base class builds one long-lived :class:`google.adk.agents.LlmAgent` per
process (static instruction + tools + model), binds :mod:`agents.context` for
each turn, runs :func:`adk_runner.run_adk_turn`, parses JSON output, and
returns :class:`AgentResult` for the orchestrator.

The orchestrator only sees :class:`base.BaseAgent` — it does not import ADK.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.rag_agent.config.settings import get_settings

from ..models.enums import AgentName
from .adk_runner import (
    AdkTurnResult,
    build_llm_agent,
    extract_json_block,
    run_adk_turn,
)
from .base import AgentContext, AgentResult, BaseAgent, GateSpec
from .context import AgentToolContext, bind_tool_context
from .tools import adk_tools_named

log = logging.getLogger(__name__)


class LlmDrivenAgent(BaseAgent):
    instruction: str = ""
    tool_names: list[str] = []
    requires_review: bool = True
    temperature: float = 0.1

    def __init__(self, model: str | None = None) -> None:
        # If no override given, take the platform-wide default from settings.
        self.model_name = model or get_settings().gemini.generation_model
        # Build the ADK agent eagerly — its declarations / tool schema are
        # static across cases; only the user prompt and per-call context
        # change between invocations.
        self._adk_agent = build_llm_agent(
            name=self.name.value.lower(),
            instruction=self.instruction,
            model=self.model_name,
            tools=adk_tools_named(self.tool_names),
            temperature=self.temperature,
        )

    # ----- to be implemented by subclasses ------------------------------------
    def build_user_prompt(self, ctx: AgentContext) -> str:  # pragma: no cover
        raise NotImplementedError

    def next_gates(
        self, ctx: AgentContext, output: dict[str, Any]
    ) -> list[GateSpec]:
        return []

    def reasoning_summary(
        self, output: dict[str, Any], turn: AdkTurnResult
    ) -> str | None:
        text = turn.final_text.strip()
        return (text[:237] + "…") if len(text) > 240 else text

    def collect_recorded_ids(
        self, turn: AdkTurnResult
    ) -> tuple[list[str], list[str]]:
        """Walk tool calls to harvest evidence_id / party_id values."""
        evidence: list[str] = []
        parties: list[str] = []
        for call in turn.tool_calls:
            r = call.result if isinstance(call.result, dict) else {}
            if call.name == "record_evidence" and "evidence_id" in r:
                evidence.append(r["evidence_id"])
            elif call.name == "record_party" and "party_id" in r:
                parties.append(r["party_id"])
        return evidence, parties

    # ----- main entry point used by the orchestrator -------------------------
    async def run(self, ctx: AgentContext) -> AgentResult:
        prompt = self.build_user_prompt(ctx)

        tool_ctx = AgentToolContext(
            case_id=ctx.state.case.id,
            agent_run_id=ctx.run.id,
            actor_id=self.name.value,
            repos=ctx.repos,
        )
        with bind_tool_context(tool_ctx):
            turn = await run_adk_turn(
                adk_agent=self._adk_agent,
                user_prompt=prompt,
            )

        try:
            output = extract_json_block(turn.final_text)
        except (ValueError, Exception) as err:
            # Surface as a structured error in the output payload — the
            # orchestrator will mark the run completed-with-review-required
            # so an analyst sees the parse failure.
            log.warning("agent.parse.failed agent=%s err=%s", self.name.value, err)
            output = {
                "error": "failed_to_parse_output",
                "detail": f"{err.__class__.__name__}: {err}",
                "raw_text": turn.final_text,
            }

        evidence_ids, party_ids = self.collect_recorded_ids(turn)

        from uuid import UUID  # local import; lightweight

        return AgentResult(
            output_payload=output,
            reasoning=turn.reasoning_log,
            reasoning_summary=self.reasoning_summary(output, turn),
            tokens=turn.tokens,
            requires_review=self.requires_review,
            new_evidence_ids=[UUID(e) for e in evidence_ids],
            new_party_ids=[UUID(p) for p in party_ids],
            next_gates=self.next_gates(ctx, output),
        )

    # The orchestrator hashes this for idempotency.  Subclasses may override
    # to widen / narrow the input fingerprint.
    def idempotency_input(self, ctx_extra: dict[str, Any]) -> dict[str, Any]:
        return {"agent": self.name.value, "extra": ctx_extra}
