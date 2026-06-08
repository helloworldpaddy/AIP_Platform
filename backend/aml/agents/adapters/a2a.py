"""A2A adapter — invoke remote AML stage agents via the A2A protocol."""

from __future__ import annotations

import logging
from uuid import UUID

from ...models.enums import AgentName
from ...models.state import TokenUsage
from ...utils.circuit_breaker import CircuitOpenError
from ..a2a.metadata import build_a2a_request_metadata
from ..adk_runner import extract_json_block
from ..base import AgentContext, AgentResult, BaseAgent
from ..ports import ToolGatewaySpec
from .a2a_client import A2aRemoteClient, A2aRemoteError
from .a2a_resilience import circuit_breaker_for, load_a2a_circuit_config

log = logging.getLogger(__name__)


class A2aAdapterError(RuntimeError):
    """Raised when remote A2A execution fails."""


class A2aCircuitOpenError(A2aAdapterError):
    """Raised when the A2A circuit breaker is open for an endpoint."""


class A2aAdapter:
    """Execute a stage on a remote ADK ``to_a2a`` host."""

    def __init__(
        self,
        *,
        agent_name: AgentName,
        agent_card_url: str,
        timeout_seconds: float = 600.0,
    ) -> None:
        self._agent_name = agent_name
        self._agent_card_url = agent_card_url
        self._timeout_seconds = timeout_seconds

    async def execute(
        self,
        *,
        agent_name: AgentName,
        agent: BaseAgent,
        ctx: AgentContext,
        user_message: str,
        tool_gateway: ToolGatewaySpec | None = None,
    ) -> AgentResult:
        if tool_gateway is None:
            raise A2aAdapterError(
                f"A2A transport for {agent_name.value} requires a run-scoped tool_gateway"
            )

        preflight = await agent.preflight(ctx)
        if preflight is not None:
            return preflight

        breaker = circuit_breaker_for(
            self._agent_card_url,
            config=load_a2a_circuit_config(),
        )
        try:
            breaker.ensure_allow()
        except CircuitOpenError as err:
            raise A2aCircuitOpenError(str(err)) from err

        client = A2aRemoteClient(
            agent_card_url=self._agent_card_url,
            timeout_seconds=self._timeout_seconds,
        )
        metadata = build_a2a_request_metadata(
            case_id=ctx.state.case.id,
            run_id=ctx.run.id,
            agent_name=agent_name,
            tool_gateway=tool_gateway,
        )

        remote = None
        try:
            remote = await client.send_turn(
                user_message=user_message,
                request_metadata=metadata,
            )
            breaker.record_success()
        except (A2aRemoteError, OSError, TimeoutError) as err:
            breaker.record_failure()
            raise A2aAdapterError(
                f"A2A stage {agent_name.value} failed: {err}"
            ) from err
        except Exception as err:
            breaker.record_failure()
            if is_a2a_transient(err):
                raise A2aAdapterError(
                    f"A2A stage {agent_name.value} failed: {err}"
                ) from err
            raise
        finally:
            await client.close()

        assert remote is not None

        try:
            output = extract_json_block(remote.final_text)
        except ValueError as err:
            log.warning(
                "adapter.a2a.parse_failed agent=%s err=%s",
                agent_name.value,
                err,
            )
            output = {
                "error": "failed_to_parse_output",
                "detail": str(err),
                "raw_text": remote.final_text,
            }

        evidence_ids, party_ids = await _collect_ids_written_during_run(ctx)
        summary = _reasoning_summary(remote.final_text)

        result = AgentResult(
            output_payload=output,
            reasoning=remote.final_text,
            reasoning_summary=summary,
            tokens=TokenUsage(),
            requires_review=getattr(agent, "requires_review", True),
            new_evidence_ids=evidence_ids,
            new_party_ids=party_ids,
            next_gates=agent.next_gates(ctx, output),
        )
        return await agent.finalize_a2a_result(ctx, result)


async def _collect_ids_written_during_run(
    ctx: AgentContext,
) -> tuple[list[UUID], list[UUID]]:
    """Harvest rows written via the tool gateway during this agent run."""
    evidence = await ctx.repos.evidence.list_for_case(ctx.state.case.id)
    parties = await ctx.repos.parties.list_for_case(ctx.state.case.id)
    run_id = ctx.run.id
    ev_ids = [e.id for e in evidence if e.agent_run_id == run_id]
    party_ids = [p.id for p in parties if p.agent_run_id == run_id]
    return ev_ids, party_ids


def _reasoning_summary(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    return (stripped[:237] + "…") if len(stripped) > 240 else stripped


def is_a2a_transient(err: BaseException) -> bool:
    from ...utils.rate_limit import is_retryable_error

    return is_retryable_error(err)
