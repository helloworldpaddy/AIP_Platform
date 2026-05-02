# Cursor Rules for Google ADK Engineering

Always implement agents using Google ADK-native patterns.

Use:

- `LlmAgent` for reasoning
- `SequentialAgent` for ordered workflows
- `ParallelAgent` for independent analysis
- `LoopAgent` for iterative refinement
- Function tools for external actions
- Session State for case runtime data
- Memory for approved long-term knowledge
- Artifacts for generated files
- ADK evals for validation

Reject:

- Generic agent abstractions
- LangChain-style chains
- CrewAI-style crews
- AutoGen-style conversations
- Unstructured prompts without schemas
- Final AML answers without evidence grounding

When generating code, also create:

```text
.vscode/
  settings.json
  extensions.json
  launch.json
  tasks.json
.github/
  copilot-instructions.md
.env.example
README.md
```
