"""Single-turn ADK agent driver.

Replaces the prior `gemini_runner.py` (which called `google.genai` directly).
Each AML agent owns a long-lived `google.adk.agents.LlmAgent` instance with
its instruction + tools baked in; this module spins up an `InMemoryRunner`
per invocation, feeds the user prompt, and collapses the resulting event
stream into the same `(final_text, reasoning_log, tool_calls, tokens)`
shape the rest of the platform expects.

The driver is intentionally separate from the orchestrator and from the
agent classes so it can be unit-tested with a fake LlmAgent.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools import FunctionTool
from google.genai import types as genai_types

from ..models.state import TokenUsage

log = logging.getLogger(__name__)

_APP_NAME = "aml"
_USER_ID = "orchestrator"


# -----------------------------------------------------------------------------
# Result + tool-call records (kept name-compatible with the prior runner so
# `LlmDrivenAgent` and any analytics code don't have to change).
# -----------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | str


@dataclass
class AdkTurnResult:
    final_text: str
    reasoning_log: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    tokens: TokenUsage | None = None


# -----------------------------------------------------------------------------
# Agent factory
# -----------------------------------------------------------------------------


def build_llm_agent(
    *,
    name: str,
    instruction: str,
    model: str,
    tools: list[FunctionTool],
    temperature: float = 0.1,
) -> LlmAgent:
    """Construct a long-lived ADK LlmAgent for one of the AML stages.

    The same instance is reused across many cases — it carries no per-case
    state.  Per-invocation context (case_id, agent_run_id, repos) flows
    through the `agents.context` contextvar that wraps each run.
    """
    return LlmAgent(
        name=name,
        model=model,
        instruction=instruction,
        tools=list(tools),
        generate_content_config=genai_types.GenerateContentConfig(
            temperature=temperature,
        ),
    )


# -----------------------------------------------------------------------------
# Main driver
# -----------------------------------------------------------------------------


async def run_adk_turn(
    *, adk_agent: LlmAgent, user_prompt: str
) -> AdkTurnResult:
    """Run one agent invocation to completion against the InMemoryRunner.

    Tool dispatch, function-response re-feeding, and the multi-turn loop are
    all handled by ADK; we just consume the event stream and accumulate:

        * final user-visible text (the agent's last `is_final_response()` event)
        * structured `ToolCallRecord` per function_call/function_response pair
        * a flat reasoning log suitable for the audit trail
        * cumulative `TokenUsage` from event.usage_metadata
    """
    runner = InMemoryRunner(agent=adk_agent, app_name=_APP_NAME)
    session = await runner.session_service.create_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=uuid4().hex
    )

    new_message = genai_types.Content(
        role="user", parts=[genai_types.Part(text=user_prompt)]
    )

    reasoning_chunks: list[str] = ["[user_prompt]\n" + user_prompt]
    tool_calls: list[ToolCallRecord] = []
    final_text = ""
    tokens = TokenUsage()
    pending_calls: dict[str, ToolCallRecord] = {}  # name -> last open call

    try:
        async for event in runner.run_async(
            user_id=_USER_ID,
            session_id=session.id,
            new_message=new_message,
        ):
            tokens = _accumulate_tokens(tokens, getattr(event, "usage_metadata", None))

            content = getattr(event, "content", None)
            if content is None:
                continue

            for part in content.parts or []:
                text = getattr(part, "text", None)
                fc = getattr(part, "function_call", None)
                fr = getattr(part, "function_response", None)

                if text:
                    role = content.role or "model"
                    reasoning_chunks.append(f"[{role} text]\n{text}")
                    if event.is_final_response():
                        final_text = text.strip()

                if fc and fc.name:
                    args = dict(fc.args or {})
                    record = ToolCallRecord(name=fc.name, arguments=args, result={})
                    tool_calls.append(record)
                    pending_calls[fc.name] = record
                    reasoning_chunks.append(
                        f"[function_call] {fc.name}({json.dumps(args, default=str)})"
                    )

                if fr and fr.name:
                    response = dict(fr.response or {})
                    # ADK wraps tool returns under `{"result": ...}` when the
                    # callable returned a dict; unwrap so the audit log shows
                    # the bare value the LLM saw.
                    payload = response.get("result", response)
                    open_call = pending_calls.pop(fr.name, None)
                    if open_call is not None:
                        open_call.result = payload
                    reasoning_chunks.append(
                        f"[function_response] {fr.name} => "
                        f"{json.dumps(payload, default=str)[:500]}"
                    )
    finally:
        # InMemoryRunner holds a session-service handle; close releases it
        # so successive invocations don't leak state across cases.
        try:
            await runner.close()
        except Exception:  # pragma: no cover — defensive cleanup
            log.debug("adk_runner.close.error", exc_info=True)

    return AdkTurnResult(
        final_text=final_text,
        reasoning_log="\n\n".join(reasoning_chunks),
        tool_calls=tool_calls,
        tokens=tokens,
    )


def _accumulate_tokens(running: TokenUsage, usage: Any) -> TokenUsage:
    if usage is None:
        return running
    return TokenUsage(
        prompt=running.prompt + int(getattr(usage, "prompt_token_count", 0) or 0),
        completion=running.completion
        + int(getattr(usage, "candidates_token_count", 0) or 0),
        total=running.total + int(getattr(usage, "total_token_count", 0) or 0),
    )


# -----------------------------------------------------------------------------
# Helpers for parsing the agent's final JSON block
# -----------------------------------------------------------------------------


def extract_json_block(text: str) -> dict[str, Any]:
    """Extract the first ```json fenced block from `text`.

    Falls back to parsing the entire string as JSON if no fence is found.
    Raises `ValueError` if neither parses.
    """
    fence_open = text.find("```json")
    if fence_open != -1:
        body_start = fence_open + len("```json")
        if text[body_start : body_start + 1] == "\n":
            body_start += 1
        fence_close = text.find("```", body_start)
        if fence_close == -1:
            raise ValueError("unterminated ```json block in agent output")
        return json.loads(text[body_start:fence_close])
    return json.loads(text)
