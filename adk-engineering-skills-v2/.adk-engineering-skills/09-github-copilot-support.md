# GitHub Copilot Support Skill

Use this skill to keep GitHub Copilot aligned with Google ADK engineering standards.

## Required file

Create:

```text
.github/copilot-instructions.md
```

## Copilot rules

GitHub Copilot must:

1. Generate Google ADK-native Python code.
2. Prefer `LlmAgent` for reasoning agents.
3. Prefer ADK workflow agents for orchestration.
4. Use typed function tools.
5. Use structured schemas.
6. Include eval cases.
7. Include tests.
8. Include source references for grounded AML outputs.
9. Avoid LangChain-style abstractions unless explicitly requested.
10. Avoid ungrounded AML conclusions.

## Example `.github/copilot-instructions.md`

```markdown
# GitHub Copilot Instructions

This repository builds agents using Google ADK.

When generating code:

- Use Google ADK-native patterns.
- Use `LlmAgent` for reasoning agents.
- Use `SequentialAgent`, `ParallelAgent`, or `LoopAgent` for workflow orchestration.
- Create typed Python function tools with docstrings.
- Keep tool inputs and outputs JSON-serializable.
- Use Session State for runtime case context.
- Use Memory only for approved long-term knowledge.
- Use Artifacts for generated reports and evidence files.
- Add ADK eval cases for every agent.
- Add pytest unit tests for tools and schemas.
- Add README commands for `adk run`, `adk web`, and `adk eval`.

Do not:

- Generate LangChain, CrewAI, or AutoGen code unless specifically asked.
- Store secrets in source code.
- Make unsupported AML risk conclusions.
- Treat name-only matches as confirmed adverse findings.
- Skip evidence references in investigation output.
```

## Copilot Chat prompt template

```markdown
Use the instructions in `.github/copilot-instructions.md` and `.adk-engineering-skills`.

Build or modify this Google ADK agent using ADK-native patterns only.

Requirements:
- LlmAgent or ADK workflow agent where appropriate
- typed function tools
- session state usage
- artifact output
- eval cases
- pytest tests
- README usage
- no LangChain
- no ungrounded AML conclusions
```
