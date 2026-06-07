"""Agent 2 — Transaction Enrichment.

Always opens the `PARTIES_VERIFIED` gate so Due Diligence cannot start
until an analyst has reviewed the parties this agent identified.
"""

from __future__ import annotations

import json
from typing import Any

from .base import AgentContext, GateSpec
from .llm_agent_base import LlmDrivenAgent
from .prompts import TRANSACTION_ENRICHMENT_INSTRUCTION
from .stages.transaction_enrichment.agent import TOOL_NAMES, root_agent as _root_agent
from ..models.enums import AgentName


class TransactionEnrichmentAgent(LlmDrivenAgent):
    name = AgentName.TRANSACTION_ENRICHMENT
    instruction = TRANSACTION_ENRICHMENT_INSTRUCTION
    tool_names = TOOL_NAMES
    root_agent = _root_agent

    def build_user_prompt(self, ctx: AgentContext) -> str:
        case = ctx.state.case
        ia_run = ctx.state.latest_run(AgentName.INITIAL_ASSESSMENT)
        ia_output = ia_run.output_payload if ia_run else None

        return (
            f"Case: {case.case_number}\n"
            f"Subject: {case.subject_party_name} (id={case.subject_party_id})\n"
            f"Alert type: {case.alert_type}\n\n"
            "Initial Assessment output (use it to scope your search):\n"
            f"```json\n{json.dumps(ia_output, indent=2, default=str)}\n```\n\n"
            "Run hop-1 then hop-2 graph traversals.  Record every retrieved "
            "neighbor as evidence (GRAPH_RELATION) and persist each unique "
            "party with `record_party`.  Conclude with the strict JSON schema."
        )

    def next_gates(
        self, ctx: AgentContext, output: dict[str, Any]
    ) -> list[GateSpec]:
        # Always block Due Diligence on analyst verification of parties.
        return [
            GateSpec(
                name="PARTIES_VERIFIED",
                blocks_agent=AgentName.DUE_DILIGENCE,
                notes="Verify each counter-party identified by the Transaction Enrichment agent.",
            )
        ]
