# ADK Evaluation Skill

Every ADK agent must include evaluation cases.

Required eval categories:

1. Happy path
2. Missing evidence
3. Conflicting evidence
4. Tool failure
5. Invalid input
6. Hallucination prevention
7. High-risk escalation
8. False-positive closure
9. Weak match disambiguation
10. Citation completeness

Preferred eval layout:

```text
eval/
  evalset.json
  test_cases/
    happy_path.json
    missing_evidence.json
    conflicting_evidence.json
    hallucination_prevention.json
```

Evaluation rules:

- Expected outputs must be schema-valid.
- Evidence-backed claims must include references.
- Unsupported claims should return `insufficient_evidence`.
- The agent must not invent facts when tools return no result.
