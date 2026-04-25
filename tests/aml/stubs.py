"""Deterministic stub agents that exercise the orchestrator without an LLM.

Each stub mirrors the public contract of its real counterpart:

* writes one or more `evidence_ledger` rows via `ctx.repos.evidence`
* (Transaction Enrichment) writes `case_parties` and opens the
  `PARTIES_VERIFIED` gate
* (Case Analysis) creates a `narratives` row and echoes its id back in
  `output_payload`
* returns an `AgentResult` with `requires_review=True` so the orchestrator
  parks the run in `AWAITING_REVIEW`, matching production HITL behaviour
"""

from __future__ import annotations

from typing import Any

from backend.aml.agents.base import (
    AgentContext,
    AgentResult,
    BaseAgent,
    GateSpec,
)
from backend.aml.models.enums import (
    AgentName,
    Classification,
    EvidenceType,
    PartyType,
)
from backend.aml.models.state import Citation, TokenUsage


_TOKENS = TokenUsage(prompt=100, completion=50, total=150)


class StubInitialAssessmentAgent(BaseAgent):
    name = AgentName.INITIAL_ASSESSMENT
    model_name = "stub-initial-assessment"

    async def run(self, ctx: AgentContext) -> AgentResult:
        evidence = await ctx.repos.evidence.record(
            case_id=ctx.state.case.id,
            agent_run_id=ctx.run.id,
            evidence_type=EvidenceType.POLICY_RULE,
            source_system="stub",
            source_uri="policy://aml/triage",
            title="Triage rule applied",
            content=(
                "Subject party flagged on the high-risk transaction-monitoring "
                "rule (threshold breach + cross-border counterparty)."
            ),
            structured_data={"rule_id": "TM-001"},
            confidence_score=0.85,
            contains_pii=False,
            created_by=self.name.value,
        )
        return AgentResult(
            output_payload={
                "summary": "High-risk alert; recommend transaction enrichment.",
                "risk_score": 72,
                "evidence_ids": [str(evidence.id)],
            },
            reasoning="Stub initial assessment chain-of-thought.",
            reasoning_summary="Triage rule TM-001 fired.",
            tokens=_TOKENS,
            requires_review=True,
            new_evidence_ids=[evidence.id],
        )


class StubTransactionEnrichmentAgent(BaseAgent):
    name = AgentName.TRANSACTION_ENRICHMENT
    model_name = "stub-transaction-enrichment"

    async def run(self, ctx: AgentContext) -> AgentResult:
        case_id = ctx.state.case.id
        evidence = await ctx.repos.evidence.record(
            case_id=case_id,
            agent_run_id=ctx.run.id,
            evidence_type=EvidenceType.TRANSACTION,
            source_system="stub-core-banking",
            source_uri="txn://batch/2026-04-25",
            title="Counterparty graph (1 hop)",
            content="2 counterparties identified within 1 hop of subject party.",
            structured_data={"hop_distance": 1, "counterparties": 2},
            confidence_score=0.9,
            contains_pii=True,
            created_by=self.name.value,
        )

        party_a = await ctx.repos.parties.upsert(
            case_id=case_id,
            party_external_id="P-COUNTER-001",
            party_name="Acme Holdings Ltd.",
            party_type=PartyType.CORPORATE,
            relationship="counterparty",
            hop_distance=1,
            risk_indicators={"sanctions_list": False, "pep": False},
            source_evidence_ids=[evidence.id],
        )
        party_b = await ctx.repos.parties.upsert(
            case_id=case_id,
            party_external_id="P-COUNTER-002",
            party_name="Bravo Trust",
            party_type=PartyType.TRUST,
            relationship="beneficiary",
            hop_distance=1,
            risk_indicators={"sanctions_list": False, "pep": True},
            source_evidence_ids=[evidence.id],
        )

        return AgentResult(
            output_payload={
                "party_count": 2,
                "party_ids": [str(party_a.id), str(party_b.id)],
            },
            reasoning="Stub transaction enrichment chain-of-thought.",
            reasoning_summary="Identified 2 counterparties at hop=1.",
            tokens=_TOKENS,
            requires_review=True,
            new_evidence_ids=[evidence.id],
            new_party_ids=[party_a.id, party_b.id],
            next_gates=[
                GateSpec(
                    name="PARTIES_VERIFIED",
                    blocks_agent=AgentName.DUE_DILIGENCE,
                    notes="Verify the 2 enriched counterparties before EDD.",
                )
            ],
        )


class StubDueDiligenceAgent(BaseAgent):
    name = AgentName.DUE_DILIGENCE
    model_name = "stub-due-diligence"

    async def run(self, ctx: AgentContext) -> AgentResult:
        evidence = await ctx.repos.evidence.record(
            case_id=ctx.state.case.id,
            agent_run_id=ctx.run.id,
            evidence_type=EvidenceType.SANCTIONS_HIT,
            source_system="stub-sanctions-screen",
            source_uri="ofac://sdn-check",
            title="Sanctions screen — clean",
            content="No sanctions hits across all enriched parties.",
            structured_data={"hits": 0, "parties_screened": 2},
            confidence_score=0.95,
            contains_pii=False,
            created_by=self.name.value,
        )
        return AgentResult(
            output_payload={
                "sanctions_hits": 0,
                "adverse_media_hits": 0,
                "evidence_ids": [str(evidence.id)],
            },
            reasoning="Stub due-diligence chain-of-thought.",
            reasoning_summary="Sanctions + adverse media: clean.",
            tokens=_TOKENS,
            requires_review=True,
            new_evidence_ids=[evidence.id],
        )


class StubCaseAnalysisAgent(BaseAgent):
    name = AgentName.CASE_ANALYSIS
    model_name = "stub-case-analysis"

    async def run(self, ctx: AgentContext) -> AgentResult:
        case_id = ctx.state.case.id

        # Reuse the most recent piece of evidence as the citation target so
        # the narrative renders something meaningful in the UI tests.
        evidence = ctx.state.evidence[-1] if ctx.state.evidence else None
        citations: list[Citation] = (
            [Citation(footnote=1, evidence_id=evidence.id, excerpt=evidence.title)]
            if evidence
            else []
        )

        narrative = await ctx.repos.narratives.create(
            case_id=case_id,
            classification=Classification.FALSE_POSITIVE,
            rationale=(
                "All counterparties verified, sanctions screen clean, no "
                "adverse media — recommend close as false positive."
            ),
            markdown_body=(
                "## Recommendation\nClose as **false positive**.\n\n"
                "## Findings\n- Counterparties verified [1]\n"
                "- Sanctions screen clean\n"
            ),
            citations=citations,
            created_by=self.name.value,
        )

        return AgentResult(
            output_payload={
                "narrative_id": str(narrative.id),
                "classification": Classification.FALSE_POSITIVE.value,
            },
            reasoning="Stub case-analysis chain-of-thought.",
            reasoning_summary="Drafted FALSE_POSITIVE narrative.",
            tokens=_TOKENS,
            requires_review=True,
        )
