"""Agent 1 — Initial Assessment."""

from __future__ import annotations

import json

from .base import AgentContext
from .llm_agent_base import LlmDrivenAgent
from .prompts import INITIAL_ASSESSMENT_INSTRUCTION
from .stages.initial_assessment.agent import TOOL_NAMES, root_agent as _root_agent
from ..models.enums import AgentName


class InitialAssessmentAgent(LlmDrivenAgent):
    name = AgentName.INITIAL_ASSESSMENT
    instruction = INITIAL_ASSESSMENT_INSTRUCTION
    tool_names = TOOL_NAMES
    root_agent = _root_agent

    def build_user_prompt(self, ctx: AgentContext) -> str:
        case = ctx.state.case
        alert_blob = json.dumps(case.alert_payload, indent=2, default=str)
        return (
            f"Case: {case.case_number}\n"
            f"Subject: {case.subject_party_name} (id={case.subject_party_id})\n"
            f"Alert type: {case.alert_type}\n"
            f"Priority: {case.priority.value}\n\n"
            f"Alert payload:\n```json\n{alert_blob}\n```\n\n"
            "Produce the Initial Assessment.  Follow the system rules: "
            "emit the `Reasoning:` block, then exactly one ```json fenced "
            "block matching the schema in your instructions."
        )
