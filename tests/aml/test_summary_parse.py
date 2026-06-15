"""Tests for analyst summary salvage from free-form agent text."""

from backend.aml.agents.a2a.summary_parse import (
    analyst_lines_from_payload,
    salvage_analyst_summary_from_text,
)


def test_salvage_ia_fields_from_reasoning():
    text = (
        "Reasoning:\n"
        "Risk Band: HIGH\n"
        "Leading Hypothesis: Complex SWIFT pattern via correspondent bank.\n"
        "Open Questions:\n"
        "1. What is the business rationale?\n"
        "2. Who are the beneficiaries?\n"
    )
    salvaged = salvage_analyst_summary_from_text(text)
    assert salvaged["risk_band"] == "HIGH"
    assert "SWIFT" in salvaged["leading_hypothesis"]
    assert len(salvaged["open_questions"]) == 2


def test_analyst_lines_skips_error_keys():
    payload = {
        "error": "failed_to_parse_output",
        "detail": "Expecting value",
        "raw_text": "Risk Band: HIGH\nLeading Hypothesis: Test hypothesis.\n",
    }
    lines = analyst_lines_from_payload(payload)
    assert any(l[0] == "Risk band" and l[1] == "HIGH" for l in lines)
    assert not any("failed_to_parse" in l[1] for l in lines)


def test_salvage_red_flags_from_reasoning():
    text = (
        "The policy citations are now recorded.\n\n"
        "**6. Surface any obvious red flags:**\n"
        "- **Multiple SWIFT message types (MT103, MT202):** Obscure transaction nature.\n"
        "- **Shared correspondent (CHASUS33XXX):** Layering indicator.\n"
        "\nNow I will construct the A2UI JSON for the client.\n"
    )
    salvaged = salvage_analyst_summary_from_text(text)
    assert len(salvaged["red_flags"]) == 2
    assert "SWIFT" in salvaged["red_flags"][0]

    lines = analyst_lines_from_payload(
        {"error": "failed_to_parse_output", "raw_text": text},
    )
    assert any(l[0].startswith("Red flag") for l in lines)
    assert not any(l[0] == "Summary" for l in lines)


def test_enrich_failed_payload_merges_reasoning():
    from backend.aml.agents.a2a.summary_parse import enrich_failed_output_payload

    payload = {
        "error": "failed_to_parse_output",
        "raw_text": "partial text",
        "detail": "err",
    }
    reasoning = "Risk Band: MEDIUM\nLeading Hypothesis: Test.\n"
    enriched = enrich_failed_output_payload(payload, reasoning=reasoning)
    assert enriched["risk_band"] == "MEDIUM"
    assert enriched["leading_hypothesis"] == "Test."


def test_infer_risk_from_red_flags_and_priority():
    from backend.aml.agents.a2a.summary_parse import enrich_failed_output_payload

    text = (
        "**6. Surface any obvious red flags:**\n"
        "- **Multiple SWIFT types:** Obscure nature.\n"
        "- **Shared correspondent:** Layering.\n"
        "- **High aggregate USD:** Large sum.\n"
        "- **Alerted scenarios:** Multiple hits.\n"
    )
    enriched = enrich_failed_output_payload(
        {"error": "failed_to_parse_output", "raw_text": text},
        case_priority="HIGH",
    )
    assert enriched["risk_band"] == "HIGH"
    assert enriched.get("_inferred_risk_band")
    assert enriched.get("leading_hypothesis")
    assert enriched.get("_inferred_hypothesis")


def test_salvage_te_parties_from_reasoning():
    from backend.aml.agents.a2a.summary_parse import (
        enrich_failed_output_payload,
        salvage_te_summary_from_text,
    )

    text = (
        "Party 1:\n"
        "- `party_name`: \"Harbour Logistics Pte Ltd\"\n"
        "- `hop_distance`: 1\n"
        "- `relationship`: \"TRANSFERRED_TO\"\n\n"
        "Party 2:\n"
        "- `party_name`: \"Rhein Components AG\"\n"
        "- `hop_distance`: 1\n"
        "- `relationship`: \"TRANSFERRED_TO\"\n\n"
        "The summary will reflect that 3 counter-parties were found at hop-1.\n"
        "Now I will construct the A2UI JSON for the client.\n"
    )
    salvaged = salvage_te_summary_from_text(text)
    assert salvaged["party_count"] == 2
    assert len(salvaged["parties"]) == 2
    assert "counter-parties at hop-1" in salvaged["summary"]

    enriched = enrich_failed_output_payload(
        {"error": "failed_to_parse_output", "raw_text": text},
        agent_name="TRANSACTION_ENRICHMENT",
    )
    assert enriched.get("_salvaged_te")
    assert enriched.get("party_count") == 2
    assert enriched.get("summary")
