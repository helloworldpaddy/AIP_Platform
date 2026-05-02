# ADK Guardrails and Grounding Skill

The agent must classify every material statement as:

- `FACT`: directly supported by evidence
- `INFERENCE`: derived from evidence
- `GAP`: missing or insufficient evidence
- `ACTION`: recommended next step

AML grounding rules:

1. Never answer AML findings from model memory.
2. Every adverse finding must have evidence.
3. Name match alone is not a true match.
4. Use DOB, address, country, occupation, and relationship context for disambiguation.
5. Separate confirmed facts from inferred risk indicators.
6. If evidence is weak, return `insufficient_evidence`.
7. Never create final suspicious activity conclusions without support.
8. Do not overstate sanctions, fraud, criminal, or adverse media findings.

Recommended output fragment:

```json
{
  "finding_type": "INFERENCE",
  "finding": "Potential relationship to higher-risk counterparty activity.",
  "evidence_ids": ["EV-001", "EV-004"],
  "confidence": "medium",
  "limitations": "Relationship is transaction-based only; no ownership evidence found."
}
```
