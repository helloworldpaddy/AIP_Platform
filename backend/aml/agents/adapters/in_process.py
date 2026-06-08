"""In-process adapter — current production path (ADK ``LlmAgent`` in orchestrator process)."""

from __future__ import annotations

import logging

from ...models.enums import AgentName
from ..base import AgentContext, AgentResult, BaseAgent
from ..ports import ToolGatewaySpec

log = logging.getLogger(__name__)


class InProcessAdapter:
    """Delegates to :meth:`BaseAgent.run` with a transactional ``AgentContext``."""

    async def execute(
        self,
        *,
        agent_name: AgentName,
        agent: BaseAgent,
        ctx: AgentContext,
        user_message: str,
        tool_gateway: ToolGatewaySpec | None = None,
    ) -> AgentResult:
        if tool_gateway is not None:
            log.debug(
                "adapter.in_process ignore tool_gateway agent=%s",
                agent_name.value,
            )
        # ``user_message`` is composed by the orchestrator for parity with the
        # future A2A path; in-process agents still build the prompt inside
        # ``agent.run`` via ``build_user_prompt(ctx)`` today.
        _ = user_message
        log.debug("adapter.in_process agent=%s run_id=%s", agent_name.value, ctx.run.id)
        return await agent.run(ctx)
