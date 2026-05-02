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
- Add VS Code tasks and launch configuration.

Do not:

- Generate LangChain, CrewAI, or AutoGen code unless specifically asked.
- Store secrets in source code.
- Make unsupported AML risk conclusions.
- Treat name-only matches as confirmed adverse findings.
- Skip evidence references in investigation output.
