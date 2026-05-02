# Claude Code Instructions for Google ADK Engineering

You are working in a Google ADK agent repository.

Always generate Google ADK-native code.

Follow these standards:

1. Use `LlmAgent` for reasoning agents.
2. Use ADK workflow agents for orchestration:
   - `SequentialAgent`
   - `ParallelAgent`
   - `LoopAgent`
3. Use typed Python function tools.
4. Use JSON-serializable tool outputs.
5. Use Session State for case-specific runtime context.
6. Use Memory only for approved long-term knowledge.
7. Use Artifacts for generated files and reports.
8. Add ADK eval cases.
9. Add pytest tests.
10. Add README usage instructions.
11. Add VS Code support files.
12. Add GitHub Copilot instructions.

Do not generate:

- LangChain code
- CrewAI code
- AutoGen code
- Custom orchestration when ADK has a native option
- AML findings without evidence
- Name-only adverse match conclusions
