# ADK Agent Structure Skill

Every Google ADK agent must include:

- Agent name
- Description
- Instruction
- Model configuration
- Allowed tools
- Input contract
- Output contract
- Error handling
- Evaluation cases
- README run instructions

Preferred layout:

```text
agents/
  aml_investigation/
    __init__.py
    agent.py
    tools.py
    schemas.py
    eval/
      evalset.json
```

Engineering rules:

1. Use `LlmAgent` for reasoning agents.
2. Use `SequentialAgent` for ordered workflows.
3. Use `ParallelAgent` for independent workstreams.
4. Use `LoopAgent` for iterative refinement.
5. Avoid custom orchestration when ADK workflow agents can handle it.
6. Keep agent instructions explicit, grounded, and schema-driven.
