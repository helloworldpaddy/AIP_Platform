"""Parse analyst-facing fields from agent free text when JSON output is missing."""

from __future__ import annotations

import re
from typing import Any

_RISK_BAND = re.compile(
    r"(?:\*\*)?Risk\s+Band:?(?:\*\*)?\s*([A-Z][A-Z_]+|\w+)",
    re.IGNORECASE,
)
_HYPOTHESIS = re.compile(
    r"(?:\*\*)?(?:Leading\s+)?Hypothesis:?(?:\*\*)?\s*(.+?)"
    r"(?=(?:\*\*)?Open\s+Questions|\n\s*\d+\.\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_OPEN_QUESTIONS = re.compile(
    r"(?:\*\*)?Open\s+Questions:?(?:\*\*)?\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
_RED_FLAGS = re.compile(
    r"(?:\*\*\d+\.\s*)?(?:Surface\s+any\s+obvious\s+)?red\s+flags?:?(?:\*\*)?\s*"
    r"([\s\S]+?)(?=(?:\n\s*\n(?:Now I will|I will now)|\Z))",
    re.IGNORECASE,
)
_PARTY_BLOCK = re.compile(
    r"Party\s+\d+:\s*\n(.*?)(?=\nParty\s+\d+:|\n\n(?:All parties|The summary|Now I will)|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_PARTY_NAME = re.compile(r"party_name[`'\"]?\s*:\s*\"([^\"]+)\"", re.IGNORECASE)
_HOP_DISTANCE = re.compile(r"hop_distance[`'\"]?\s*:\s*(\d+)", re.IGNORECASE)
_RELATIONSHIP = re.compile(r"relationship[`'\"]?\s*:\s*\"([^\"]+)\"", re.IGNORECASE)
_TE_SUMMARY = re.compile(
    r"(?:The summary will reflect that )?(\d+)\s+counter-parties?\s+were found at hop-(\d+)",
    re.IGNORECASE,
)


def salvage_analyst_summary_from_text(text: str) -> dict[str, Any]:
    """Extract IA-style summary fields from reasoning or partial agent output."""
    if not text or not text.strip():
        return {}

    result: dict[str, Any] = {}
    risk = _RISK_BAND.search(text)
    if risk:
        result["risk_band"] = risk.group(1).strip().upper()

    hypo = _HYPOTHESIS.search(text)
    if hypo:
        hypothesis = _clean_prose(hypo.group(1))
        if hypothesis:
            result["leading_hypothesis"] = hypothesis

    oq = _OPEN_QUESTIONS.search(text)
    if oq:
        questions = _parse_numbered_lines(oq.group(1))
        if questions:
            result["open_questions"] = questions

    red_flags = _RED_FLAGS.search(text)
    if red_flags:
        flags = _parse_bullet_lines(red_flags.group(1))
        if flags:
            result["red_flags"] = flags

    return result


def salvage_te_summary_from_text(text: str) -> dict[str, Any]:
    """Extract TE counterparty table + network summary from partial agent output."""
    if not text or not text.strip():
        return {}

    result: dict[str, Any] = {}
    parties: list[dict[str, Any]] = []
    for block in _PARTY_BLOCK.finditer(text):
        chunk = block.group(1)
        name = _PARTY_NAME.search(chunk)
        if not name:
            continue
        hop = _HOP_DISTANCE.search(chunk)
        rel = _RELATIONSHIP.search(chunk)
        parties.append(
            {
                "party_name": name.group(1).strip(),
                "hop_distance": int(hop.group(1)) if hop else None,
                "relationship": rel.group(1).strip() if rel else None,
            }
        )

    if parties:
        result["parties"] = parties
        result["party_count"] = len(parties)

    summary_match = _TE_SUMMARY.search(text)
    if summary_match:
        count, hop = summary_match.groups()
        result["summary"] = (
            f"{count} counter-parties at hop-{hop}; "
            "hop-2 traversal did not add new unique parties."
        )
    elif parties:
        hops = [p["hop_distance"] for p in parties if p.get("hop_distance")]
        hop_label = f"hop-{max(hops)}" if hops else "hop-1"
        result["summary"] = (
            f"{len(parties)} counter-parties identified at {hop_label}."
        )

    return result


def infer_missing_ia_fields(
    payload: dict[str, Any],
    *,
    case_priority: str | None = None,
) -> dict[str, Any]:
    """Fill risk band / hypothesis when salvaged red flags exist but JSON was cut off."""
    result = dict(payload)
    red_flags = result.get("red_flags")
    flags: list[str] = []
    if isinstance(red_flags, list):
        flags = [str(f) for f in red_flags if isinstance(f, str) and f.strip()]

    if not result.get("risk_band") and flags:
        count = len(flags)
        priority = (case_priority or "").upper()
        if priority in {"HIGH", "CRITICAL"} or count >= 4:
            result["risk_band"] = "HIGH"
        elif count >= 2:
            result["risk_band"] = "MEDIUM"
        else:
            result["risk_band"] = "MEDIUM"
        result["_inferred_risk_band"] = True

    hypo = result.get("leading_hypothesis") or result.get("hypothesis")
    if not hypo and flags:
        result["leading_hypothesis"] = _synthesize_hypothesis(flags)
        result["_inferred_hypothesis"] = True

    return result


def _synthesize_hypothesis(flags: list[str]) -> str:
    highlights = "; ".join(flags[:2])
    if len(highlights) > 280:
        highlights = highlights[:277] + "…"
    return (
        "Working theory (inferred from salvaged red flags): "
        f"suspicious activity patterns include {highlights}."
    )


def _clean_prose(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _parse_numbered_lines(block: str) -> list[str]:
    items: list[str] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^\d+\.\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        if line:
            items.append(line)
    return items


def _parse_bullet_lines(block: str) -> list[str]:
    """Parse markdown bullet lists (including ``- **Title:** detail``)."""
    items: list[str] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s*", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*:?\s*", r"\1: ", line)
        line = line.replace("**", "").strip().replace("::", ":")
        if line:
            items.append(line)
    return items


def _combined_salvage_text(
    output_payload: dict[str, Any],
    reasoning: str | None = None,
) -> str:
    parts: list[str] = []
    raw = output_payload.get("raw_text")
    if isinstance(raw, str) and raw.strip():
        parts.append(raw.strip())
    if reasoning and reasoning.strip():
        parts.append(reasoning.strip())
    return "\n\n".join(parts)


def enrich_failed_output_payload(
    output_payload: dict[str, Any],
    *,
    reasoning: str | None = None,
    case_priority: str | None = None,
    agent_name: str | None = None,
) -> dict[str, Any]:
    """Salvage stage fields from free text when structured JSON was incomplete."""
    if output_payload.get("error") != "failed_to_parse_output":
        return output_payload

    combined = _combined_salvage_text(output_payload, reasoning)
    if not combined:
        return output_payload

    agent_token = (agent_name or "").upper()
    if agent_token == "TRANSACTION_ENRICHMENT":
        salvaged = salvage_te_summary_from_text(combined)
        if not salvaged:
            salvaged = salvage_analyst_summary_from_text(combined)
    else:
        salvaged = salvage_analyst_summary_from_text(combined)

    if not salvaged:
        return output_payload

    merged = dict(output_payload)
    for key, val in salvaged.items():
        if merged.get(key) is None:
            merged[key] = val

    if agent_token == "TRANSACTION_ENRICHMENT":
        merged["_salvaged_te"] = True
        return merged

    return infer_missing_ia_fields(merged, case_priority=case_priority)


def analyst_lines_from_payload(output_payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Human-readable label/value pairs for A2UI (skips internal error keys)."""
    lines: list[tuple[str, str]] = []

    if output_payload.get("error") == "failed_to_parse_output":
        raw = output_payload.get("raw_text")
        if isinstance(raw, str):
            te = salvage_te_summary_from_text(raw)
            if te:
                return _lines_from_te_salvaged(te)
            salvaged = salvage_analyst_summary_from_text(raw)
            if salvaged:
                return _lines_from_salvaged(salvaged)

    preferred = [
        ("risk_band", "Risk band"),
        ("risk_score", "Risk score"),
        ("scenario_type", "Scenario type"),
        ("summary", "Summary"),
        ("hypothesis", "Leading hypothesis"),
        ("leading_hypothesis", "Leading hypothesis"),
        ("classification", "Classification"),
        ("party_count", "Parties discovered"),
    ]
    seen_labels: set[str] = set()
    for key, label in preferred:
        if label in seen_labels:
            continue
        val = output_payload.get(key)
        if val is None:
            continue
        if isinstance(val, (str, int, float, bool)):
            lines.append((label, str(val)))
            seen_labels.add(label)

    questions = output_payload.get("open_questions")
    if isinstance(questions, list) and questions:
        for idx, q in enumerate(questions, start=1):
            if isinstance(q, str) and q.strip():
                lines.append((f"Open question {idx}", q.strip()))

    red_flags = output_payload.get("red_flags")
    if isinstance(red_flags, list) and red_flags:
        for idx, flag in enumerate(red_flags, start=1):
            if isinstance(flag, str) and flag.strip():
                lines.append((f"Red flag {idx}", flag.strip()))

    parties = output_payload.get("parties")
    if isinstance(parties, list) and parties:
        for idx, party in enumerate(parties, start=1):
            if not isinstance(party, dict):
                continue
            name = party.get("party_name")
            if not isinstance(name, str) or not name.strip():
                continue
            hop = party.get("hop_distance")
            rel = party.get("relationship")
            detail = name.strip()
            if hop is not None:
                detail += f" (hop {hop}"
                if isinstance(rel, str) and rel.strip():
                    detail += f", {rel.strip()}"
                detail += ")"
            lines.append((f"Counterparty {idx}", detail))

    if not lines:
        for key, val in output_payload.items():
            if key in {"a2ui_messages", "error", "detail", "raw_text", "red_flags"}:
                continue
            if isinstance(val, (str, int, float, bool)):
                lines.append((key.replace("_", " "), str(val)))

    return lines


def _lines_from_te_salvaged(salvaged: dict[str, Any]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    if salvaged.get("summary"):
        lines.append(("Summary", str(salvaged["summary"])))
    if salvaged.get("party_count") is not None:
        lines.append(("Parties discovered", str(salvaged["party_count"])))
    parties = salvaged.get("parties")
    if isinstance(parties, list):
        for idx, party in enumerate(parties, start=1):
            if not isinstance(party, dict):
                continue
            name = party.get("party_name")
            if not isinstance(name, str):
                continue
            hop = party.get("hop_distance")
            rel = party.get("relationship")
            detail = name.strip()
            if hop is not None:
                detail += f" (hop {hop}"
                if isinstance(rel, str) and rel.strip():
                    detail += f", {rel.strip()}"
                detail += ")"
            lines.append((f"Counterparty {idx}", detail))
    return lines


def _lines_from_salvaged(salvaged: dict[str, Any]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    if salvaged.get("risk_band"):
        lines.append(("Risk band", str(salvaged["risk_band"])))
    hypo = salvaged.get("leading_hypothesis") or salvaged.get("hypothesis")
    if hypo:
        lines.append(("Leading hypothesis", str(hypo)))
    questions = salvaged.get("open_questions")
    if isinstance(questions, list):
        for idx, q in enumerate(questions, start=1):
            if isinstance(q, str):
                lines.append((f"Open question {idx}", q))
    red_flags = salvaged.get("red_flags")
    if isinstance(red_flags, list):
        for idx, flag in enumerate(red_flags, start=1):
            if isinstance(flag, str):
                lines.append((f"Red flag {idx}", flag))
    return lines
