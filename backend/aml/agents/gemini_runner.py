"""Single-turn Gemini function-calling driver.

Runs one agent invocation:

    1. Send the prompt + system instruction + tool declarations.
    2. Loop: while the model emits function_calls, dispatch them to the
       registered Python tools and feed back the results.
    3. Stop when the model emits text-only output (or a hard cap is hit).
    4. Return:
         * `final_text`         — the model's final user-visible message
         * `reasoning_log`      — full per-turn transcript suitable for CoT
         * `tool_calls`         — structured log of every tool invocation
         * `tokens`             — TokenUsage from response.usage_metadata

The driver is intentionally separate from the orchestrator and from the
agent classes so it can be unit-tested with a fake Gemini client.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types as genai_types

from agents.rag_agent.config.settings import get_settings

from ..models.state import TokenUsage
from .tools.registry import ToolSpec

log = logging.getLogger(__name__)

_MAX_TOOL_TURNS = 12  # safety cap; well above any realistic agent need


# -----------------------------------------------------------------------------
# Result + tool-call records
# -----------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | str


@dataclass
class GeminiTurnResult:
    final_text: str
    reasoning_log: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    tokens: TokenUsage | None = None


# -----------------------------------------------------------------------------
# Client (singleton, mirrors the embedding service)
# -----------------------------------------------------------------------------


_client_singleton: genai.Client | None = None


def _build_client() -> genai.Client:
    settings = get_settings().gemini
    if settings.use_vertex:
        return genai.Client(
            vertexai=True,
            project=settings.project,
            location=settings.location,
        )
    api_key = settings.api_key.get_secret_value() if settings.api_key else None
    return genai.Client(api_key=api_key)


def get_gemini_client() -> genai.Client:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = _build_client()
    return _client_singleton


# -----------------------------------------------------------------------------
# Function-declaration construction
# -----------------------------------------------------------------------------


def _to_function_declaration(spec: ToolSpec) -> genai_types.FunctionDeclaration:
    return genai_types.FunctionDeclaration(
        name=spec.name,
        description=spec.description,
        parameters=spec.parameters,
    )


def _build_tool_block(specs: list[ToolSpec]) -> list[genai_types.Tool]:
    if not specs:
        return []
    return [
        genai_types.Tool(
            function_declarations=[_to_function_declaration(s) for s in specs]
        )
    ]


# -----------------------------------------------------------------------------
# Main driver
# -----------------------------------------------------------------------------


async def run_agent_turn(
    *,
    system_instruction: str,
    user_prompt: str,
    tools: list[ToolSpec],
    model: str,
    temperature: float = 0.1,
) -> GeminiTurnResult:
    """Run one agent invocation to completion.

    Errors in tool calls are reported back to the model as a function
    response with an `error` key — the model decides whether to retry
    differently or surface the problem in its final output.
    """
    client = get_gemini_client()
    tool_specs = {s.name: s for s in tools}

    contents: list[genai_types.Content] = [
        genai_types.Content(role="user", parts=[genai_types.Part(text=user_prompt)])
    ]

    reasoning_chunks: list[str] = ["[user_prompt]\n" + user_prompt]
    tool_calls: list[ToolCallRecord] = []
    final_text: str = ""
    tokens = TokenUsage()

    for turn in range(_MAX_TOOL_TURNS):
        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                tools=_build_tool_block(tools),
            ),
        )

        # Accumulate token usage across turns.
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            tokens = TokenUsage(
                prompt=tokens.prompt + int(getattr(usage, "prompt_token_count", 0) or 0),
                completion=tokens.completion
                + int(getattr(usage, "candidates_token_count", 0) or 0),
                total=tokens.total + int(getattr(usage, "total_token_count", 0) or 0),
            )

        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            break

        # Append the model turn to history so subsequent turns see context.
        contents.append(candidate.content)

        text_parts: list[str] = []
        function_calls: list[genai_types.FunctionCall] = []
        for part in candidate.content.parts or []:
            if getattr(part, "text", None):
                text_parts.append(part.text)
            if getattr(part, "function_call", None) and part.function_call.name:
                function_calls.append(part.function_call)

        if text_parts:
            reasoning_chunks.append(f"[turn {turn} text]\n" + "\n".join(text_parts))

        if not function_calls:
            final_text = "\n".join(text_parts).strip()
            break

        # Dispatch every function call in this turn, then feed responses back.
        function_response_parts: list[genai_types.Part] = []
        for call in function_calls:
            args = dict(call.args or {})
            spec = tool_specs.get(call.name)
            if spec is None:
                result: dict[str, Any] = {"error": f"unknown tool {call.name!r}"}
            else:
                try:
                    result = await spec.fn(**args)
                except Exception as err:  # noqa: BLE001 — feed errors back to LLM
                    log.warning(
                        "tool.error name=%s err=%s", call.name, err, exc_info=True
                    )
                    result = {
                        "error": f"{err.__class__.__name__}: {err}",
                        "tool": call.name,
                    }
            tool_calls.append(
                ToolCallRecord(name=call.name, arguments=args, result=result)
            )
            reasoning_chunks.append(
                f"[turn {turn} tool_call] {call.name}({json.dumps(args, default=str)}) "
                f"=> {json.dumps(result, default=str)[:500]}"
            )
            function_response_parts.append(
                genai_types.Part.from_function_response(
                    name=call.name,
                    response={"result": result},
                )
            )

        contents.append(
            genai_types.Content(role="user", parts=function_response_parts)
        )
    else:
        # Loop exhausted without a final text turn — synthesize an error.
        log.warning("gemini.tool_loop.exhausted turns=%d", _MAX_TOOL_TURNS)
        final_text = "ERROR: tool-calling loop exhausted without producing a final answer."

    return GeminiTurnResult(
        final_text=final_text,
        reasoning_log="\n\n".join(reasoning_chunks),
        tool_calls=tool_calls,
        tokens=tokens,
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
        # Skip optional newline after the fence marker.
        if text[body_start : body_start + 1] == "\n":
            body_start += 1
        fence_close = text.find("```", body_start)
        if fence_close == -1:
            raise ValueError("unterminated ```json block in agent output")
        return json.loads(text[body_start:fence_close])

    # No fence — try parsing the whole thing.
    return json.loads(text)
