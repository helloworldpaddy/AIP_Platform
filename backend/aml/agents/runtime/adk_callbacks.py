"""ADK lifecycle callbacks — hybrid case-number → real DB for AML stages."""

from __future__ import annotations

import logging
from collections.abc import Callable

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types

from ...models.enums import AgentName
from .bootstrap import ensure_runtime_ready
from .case_resolver import parse_case_number
from .run_lifecycle import (
    AdkWebInvocation,
    cleanup_adk_web_invocation,
    complete_adk_web_run,
    start_adk_web_run,
)

log = logging.getLogger(__name__)

# invocation_id → active resources (connection + tool contextvar token)
_ACTIVE: dict[str, AdkWebInvocation] = {}

_STATE_CASE_NUMBER = "aml_case_number"
_STATE_PROMPT = "aml_assembled_prompt"
_STATE_PROMPT_INJECTED = "aml_prompt_injected"
_STATE_RUN_ID = "aml_run_id"
_STATE_CASE_ID = "aml_case_id"


def _user_text(callback_context: CallbackContext) -> str:
    content = callback_context.user_content
    if content is None:
        return ""
    parts = content.parts or []
    return "\n".join(p.text for p in parts if getattr(p, "text", None)).strip()


def hybrid_callbacks(
    agent_name: AgentName,
) -> tuple[
    Callable[[CallbackContext], None],
    Callable[[CallbackContext, LlmRequest], LlmResponse | None],
    Callable[[CallbackContext], None],
]:
    """Build before/after/model callbacks wired to a specific AML stage."""

    async def before_agent_callback(callback_context: CallbackContext) -> None:
        """Resolve case number, start agent_run, bind DB tool context."""
        await ensure_runtime_ready()

        text = _user_text(callback_context)
        case_number = parse_case_number(text) or callback_context.state.get(
            _STATE_CASE_NUMBER
        )

        if not case_number:
            log.info(
                "runtime.callback.before_agent skip agent=%s reason=no_case_number "
                "(include e.g. AML-SERVICES-SWIFT-2026-005 in your message)",
                agent_name.value,
            )
            return

        callback_context.state[_STATE_CASE_NUMBER] = case_number
        callback_context.state[_STATE_PROMPT_INJECTED] = False

        inv = await start_adk_web_run(
            case_number=case_number,
            agent_name=agent_name,
            invocation_id=callback_context.invocation_id,
        )
        _ACTIVE[callback_context.invocation_id] = inv
        callback_context.state[_STATE_PROMPT] = inv.assembled_prompt
        callback_context.state[_STATE_RUN_ID] = str(inv.run.id)
        callback_context.state[_STATE_CASE_ID] = str(inv.case_id)

        log.info(
            "runtime.callback.before_agent agent=%s case=%s run_id=%s",
            agent_name.value,
            case_number,
            inv.run.id,
        )

    async def before_model_callback(
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        """Replace the chat message with the orchestrator-equivalent prompt once."""
        prompt = callback_context.state.get(_STATE_PROMPT)
        if not prompt:
            return None

        if callback_context.state.get(_STATE_PROMPT_INJECTED):
            return None

        callback_context.state[_STATE_PROMPT_INJECTED] = True

        if not llm_request.contents:
            llm_request.contents = [
                genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])
            ]
            return None

        replaced = False
        for content in llm_request.contents:
            if getattr(content, "role", None) == "user":
                content.parts = [genai_types.Part(text=prompt)]
                replaced = True
                break
        if not replaced:
            llm_request.contents.append(
                genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])
            )
        return None

    async def after_agent_callback(callback_context: CallbackContext) -> None:
        """Persist the ADK web turn through the same agent_runs / audit path."""
        inv = _ACTIVE.pop(callback_context.invocation_id, None)
        if inv is None:
            return
        try:
            updated = await complete_adk_web_run(inv, callback_context.session)
            callback_context.state["aml_last_run_status"] = updated.status.value
            callback_context.state["aml_last_output"] = updated.output_payload
            log.info(
                "runtime.callback.after_agent agent=%s case=%s run_id=%s status=%s",
                agent_name.value,
                inv.case_number,
                updated.id,
                updated.status.value,
            )
        except Exception:
            log.exception(
                "runtime.callback.after_agent.failed agent=%s case=%s run_id=%s",
                agent_name.value,
                inv.case_number,
                inv.run.id,
            )
            raise
        finally:
            await cleanup_adk_web_invocation(inv)

    return before_agent_callback, before_model_callback, after_agent_callback


# Initial Assessment (backward-compatible exports)
(
    before_agent_callback,
    before_model_callback,
    after_agent_callback,
) = hybrid_callbacks(AgentName.INITIAL_ASSESSMENT)
