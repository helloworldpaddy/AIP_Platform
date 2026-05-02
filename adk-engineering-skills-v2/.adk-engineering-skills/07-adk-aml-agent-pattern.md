# AML Investigation Agent Pattern Skill

Recommended AML investigation multi-agent structure:

```text
Root AML Investigation Agent
  |
  |-- Case Intake Agent
  |-- Customer Profile Agent
  |-- Transaction Behavior Agent
  |-- Counterparty Prioritization Agent
  |-- Party Research Agent
  |-- Evidence Assessment Agent
  |-- Risk Scoring Agent
  |-- Narrative Generation Agent
  |-- QA / Guardrail Agent
```

Workflow:

1. Ingest case
2. Validate alert details
3. Build customer profile
4. Summarize alerted transactions
5. Analyze transaction behavior
6. Prioritize counterparties
7. Research parties
8. Assess evidence quality
9. Score residual risk
10. Generate investigation narrative
11. Run QA and grounding validation
12. Produce final recommendation

Final recommendation categories:

- False positive
- Needs more information
- Escalate for enhanced review
- Potential SAR consideration
- Block / reject / restrict recommendation, where applicable by policy

Rules:

- Do not let the narrative agent bypass evidence assessment.
- Do not let the risk scoring agent invent risk factors.
- The QA agent must check citations, unsupported claims, and policy alignment.
