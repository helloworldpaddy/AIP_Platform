"""Extract model / tool text from ADK session events."""

from __future__ import annotations

import json
from typing import Any

from google.adk.sessions.session import Session

from ..adk_runner import ToolCallRecord, extract_json_block
from ...models.state import TokenUsage


def _text_from_content(content: Any) -> str:
    if content is None:
        return ""
    parts = getattr(content, "parts", None) or []
    chunks: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def session_reasoning_log(session: Session) -> str:
    """Flat log of user/model text and tool calls for audit storage."""
    chunks: list[str] = []
    for event in session.events or []:
        content = getattr(event, "content", None)
        if content is None:
            continue
        role = getattr(content, "role", None) or "model"
        text = _text_from_content(content)
        if text:
            chunks.append(f"[{role} text]\n{text}")
        for part in content.parts or []:
            fc = getattr(part, "function_call", None)
            fr = getattr(part, "function_response", None)
            if fc and fc.name:
                args = dict(fc.args or {})
                chunks.append(
                    f"[function_call] {fc.name}({json.dumps(args, default=str)})"
                )
            if fr and fr.name:
                payload = dict(fr.response or {})
                inner = payload.get("result", payload)
                chunks.append(
                    f"[function_response] {fr.name} => "
                    f"{json.dumps(inner, default=str)[:500]}"
                )
    return "\n\n".join(chunks)


def session_final_text(session: Session) -> str:
    """Best-effort final model text (mirrors ``adk_runner.run_adk_turn``)."""
    final_text = ""
    last_model_text = ""
    last_jsonish_text = ""
    for event in session.events or []:
        content = getattr(event, "content", None)
        if content is None:
            continue
        text = _text_from_content(content)
        if not text:
            continue
        role = getattr(content, "role", None) or "model"
        if role != "user" and text.strip():
            last_model_text = text.strip()
            if "```json" in text or text.lstrip().startswith("{"):
                last_jsonish_text = text.strip()
        if hasattr(event, "is_final_response") and event.is_final_response():
            final_text = text.strip()

    if not final_text or (
        final_text
        and "```json" not in final_text
        and not final_text.lstrip().startswith("{")
    ):
        if last_jsonish_text:
            final_text = last_jsonish_text
        elif last_model_text:
            final_text = last_model_text
    return final_text


def session_tool_calls(session: Session) -> list[ToolCallRecord]:
    """Harvest function_call / function_response pairs from session events."""
    tool_calls: list[ToolCallRecord] = []
    pending: dict[str, ToolCallRecord] = {}
    for event in session.events or []:
        content = getattr(event, "content", None)
        if content is None:
            continue
        for part in content.parts or []:
            fc = getattr(part, "function_call", None)
            fr = getattr(part, "function_response", None)
            if fc and fc.name:
                record = ToolCallRecord(
                    name=fc.name,
                    arguments=dict(fc.args or {}),
                    result={},
                )
                tool_calls.append(record)
                pending[fc.name] = record
            if fr and fr.name:
                payload = dict(fr.response or {})
                inner = payload.get("result", payload)
                open_call = pending.pop(fr.name, None)
                if open_call is not None:
                    open_call.result = inner if isinstance(inner, dict) else {"result": inner}
    return tool_calls


def session_output_payload(session: Session) -> dict[str, Any]:
    """Parse the agent's final JSON block; tolerate parse failures."""
    final_text = session_final_text(session)
    try:
        return extract_json_block(final_text)
    except (ValueError, json.JSONDecodeError) as err:
        return {
            "error": "failed_to_parse_output",
            "detail": f"{err.__class__.__name__}: {err}",
            "raw_text": final_text,
        }


def collect_recorded_ids(
    tool_calls: list[ToolCallRecord],
) -> tuple[list[str], list[str]]:
    evidence: list[str] = []
    parties: list[str] = []
    for call in tool_calls:
        r = call.result if isinstance(call.result, dict) else {}
        if call.name == "record_evidence" and "evidence_id" in r:
            evidence.append(str(r["evidence_id"]))
        elif call.name == "record_party" and "party_id" in r:
            parties.append(str(r["party_id"]))
    return evidence, parties
