"""Agent 3 — Due Diligence.

Pre-flight check enforces the spec contract: this agent refuses to run
unless every recorded party has been marked verified by an analyst.
The orchestrator's gate also enforces this — the in-agent check is
defence-in-depth in case a future operator re-routes triggers.
"""

from __future__ import annotations

import json

from .base import AgentContext, AgentResult
from .llm_agent_base import LlmDrivenAgent
from .prompts import DUE_DILIGENCE_INSTRUCTION
from ..models.enums import AgentName
from ..models.state import TokenUsage


class DueDiligenceAgent(LlmDrivenAgent):
    name = AgentName.DUE_DILIGENCE
    instruction = DUE_DILIGENCE_INSTRUCTION
    tool_names = ["kyc_lookup", "external_search", "record_evidence"]

    async def run(self, ctx: AgentContext) -> AgentResult:
        unverified = [p for p in ctx.state.parties if not p.verified]
        if unverified:
            # Short-circuit — return a structured "aborted" output so the
            # orchestrator still records a clean run.
            names = ", ".join(p.party_name for p in unverified[:5])
            return AgentResult(
                output_payload={
                    "aborted": True,
                    "reason": "unverified_parties_present",
                    "unverified_count": len(unverified),
                    "sample_party_names": names,
                },
                reasoning=(
                    "Pre-flight check: detected unverified parties. Refusing "
                    "to proceed.  Analyst must clear PARTIES_VERIFIED gate."
                ),
                reasoning_summary="aborted: unverified parties present",
                tokens=TokenUsage(),
                requires_review=True,
            )
        return await super().run(ctx)

    def build_user_prompt(self, ctx: AgentContext) -> str:
        case = ctx.state.case
        verified_parties = [
            {
                "party_id": str(p.id),
                "party_external_id": p.party_external_id,
                "party_name": p.party_name,
                "party_type": p.party_type.value,
                "hop_distance": p.hop_distance,
                "relationship": p.relationship,
                "risk_indicators": p.risk_indicators,
            }
            for p in ctx.state.parties
        ]
        ia_run = ctx.state.latest_run(AgentName.INITIAL_ASSESSMENT)
        ia_output = ia_run.output_payload if ia_run else None

        return (
            f"Case: {case.case_number}\n"
            f"Subject: {case.subject_party_name} (id={case.subject_party_id})\n\n"
            "Initial Assessment summary:\n"
            f"```json\n{json.dumps(ia_output, indent=2, default=str)}\n```\n\n"
            "Verified parties to investigate:\n"
            f"```json\n{json.dumps(verified_parties, indent=2, default=str)}\n```\n\n"
            "Run KYC lookup + external search per party.  Record each result "
            "as evidence with the appropriate type (KYC_RECORD, ADVERSE_MEDIA, "
            "SANCTIONS_HIT).  Output strict JSON per the schema."
        )
