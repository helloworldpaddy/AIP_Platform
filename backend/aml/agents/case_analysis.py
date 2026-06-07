"""Agent 4 — Case Analysis & Narrative.

Persists the final narrative directly so submission becomes a one-click
analyst action: the orchestrator's `submit_narrative(narrative_id, …)`
both flips `submitted = locked = TRUE` and locks the parent case.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from .base import AgentContext, AgentResult
from .llm_agent_base import LlmDrivenAgent
from .prompts import CASE_ANALYSIS_INSTRUCTION
from .stages.case_analysis.agent import TOOL_NAMES, root_agent as _root_agent
from ..models.enums import AgentName, Classification
from ..models.state import Citation

log = logging.getLogger(__name__)


def _coerce_citations(raw: Any) -> list[Citation]:
    """Validate citations tolerantly.

    The model sometimes cites a label (e.g. "Due Diligence Findings") instead of
    an evidence UUID, or omits ``footnote``. A single bad entry must not discard
    the whole narrative — keep the valid citations and drop the rest with a
    warning so the analyst still gets a reviewable draft.
    """
    if not isinstance(raw, list):
        return []
    valid: list[Citation] = []
    skipped: list[Any] = []
    for c in raw:
        try:
            valid.append(Citation.model_validate(c))
        except (ValidationError, ValueError, TypeError):
            skipped.append(
                c.get("evidence_id") if isinstance(c, dict) else c
            )
    if skipped:
        log.warning(
            "case_analysis.citations.dropped count=%d kept=%d values=%s",
            len(skipped),
            len(valid),
            skipped,
        )
    return valid


class CaseAnalysisAgent(LlmDrivenAgent):
    name = AgentName.CASE_ANALYSIS
    instruction = CASE_ANALYSIS_INSTRUCTION
    tool_names = TOOL_NAMES  # may add new evidence to anchor narrative
    root_agent = _root_agent

    def build_user_prompt(self, ctx: AgentContext) -> str:
        case = ctx.state.case

        ia = ctx.state.latest_run(AgentName.INITIAL_ASSESSMENT)
        te = ctx.state.latest_run(AgentName.TRANSACTION_ENRICHMENT)
        dd = ctx.state.latest_run(AgentName.DUE_DILIGENCE)

        evidence_index = [
            {
                "evidence_id": str(e.id),
                "type": e.evidence_type.value,
                "source": e.source_system,
                "title": e.title,
                "excerpt": (e.content[:240] + "…") if len(e.content) > 240 else e.content,
            }
            for e in ctx.state.evidence
        ]

        return (
            f"Case: {case.case_number}\n"
            f"Subject: {case.subject_party_name} (id={case.subject_party_id})\n"
            f"Alert type: {case.alert_type}\n\n"
            "INITIAL ASSESSMENT:\n"
            f"```json\n{json.dumps(ia.output_payload if ia else None, indent=2, default=str)}\n```\n\n"
            "TRANSACTION ENRICHMENT:\n"
            f"```json\n{json.dumps(te.output_payload if te else None, indent=2, default=str)}\n```\n\n"
            "DUE DILIGENCE:\n"
            f"```json\n{json.dumps(dd.output_payload if dd else None, indent=2, default=str)}\n```\n\n"
            "AVAILABLE EVIDENCE (use these IDs in your citations):\n"
            f"```json\n{json.dumps(evidence_index, indent=2, default=str)}\n```\n\n"
            "Render the final classification, narrative, and citations per "
            "the schema in your instructions."
        )

    async def _persist_narrative_if_valid(
        self, ctx: AgentContext, out: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            classification = Classification(out["classification"])
            citations = _coerce_citations(out.get("citations", []))
            narrative = await ctx.repos.narratives.create(
                case_id=ctx.state.case.id,
                classification=classification,
                rationale=out.get("rationale", ""),
                markdown_body=out.get("narrative_markdown", ""),
                citations=citations,
                created_by=self.name.value,
            )
            return {**out, "narrative_id": str(narrative.id)}
        except (KeyError, ValueError) as err:
            log.warning(
                "case_analysis.narrative.skip reason=%s err=%s",
                "schema_mismatch",
                err,
            )
            return out

    async def finalize_adk_web_result(
        self, ctx: AgentContext, result: AgentResult
    ) -> AgentResult:
        result.output_payload = await self._persist_narrative_if_valid(
            ctx, result.output_payload
        )
        return result

    async def run(self, ctx: AgentContext) -> AgentResult:
        # Run the LLM as usual.
        result = await super().run(ctx)
        result.output_payload = await self._persist_narrative_if_valid(
            ctx, result.output_payload
        )
        return result
