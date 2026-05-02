# Google ADK Engineering Skills Pack

This pack provides reusable engineering instructions for building Google ADK-native agents in:

- Cursor
- Claude Code
- VS Code
- GitHub Copilot

## Contents

```text
.adk-engineering-skills/
  01-adk-agent-structure.md
  02-adk-tool-engineering.md
  03-adk-state-session-memory.md
  04-adk-artifacts.md
  05-adk-evaluation.md
  06-adk-guardrails-grounding.md
  07-adk-aml-agent-pattern.md
  08-vscode-support.md
  09-github-copilot-support.md

.vscode/
  settings.json
  extensions.json
  launch.json
  tasks.json

.github/
  copilot-instructions.md

cursor-rules.md
claude-code-instructions.md
.env.example
```

## How to use with Cursor

1. Copy `cursor-rules.md` into your Cursor rules.
2. Or create `.cursor/rules/google-adk.mdc`.
3. Paste the content from `cursor-rules.md`.
4. Prompt Cursor:

```text
Use the Google ADK engineering skills in .adk-engineering-skills.
Build this agent using Google ADK-native patterns only.
```

## How to use with Claude Code

Prompt Claude Code:

```text
Read claude-code-instructions.md and the .adk-engineering-skills folder.
Generate Google ADK-native code only.
```

## How to use with VS Code

1. Open the repo in VS Code.
2. Install recommended extensions from `.vscode/extensions.json`.
3. Create virtual environment:

```bash
python -m venv .venv
```

4. Install dependencies:

```bash
.venv/bin/pip install -r requirements.txt
```

5. Use VS Code tasks:
   - Create virtual environment
   - Install dependencies
   - ADK Run
   - ADK Web
   - ADK Eval
   - Run Tests
   - Lint
   - Format

## How to use with GitHub Copilot

GitHub Copilot will use `.github/copilot-instructions.md` as repository-level guidance.

Copilot Chat prompt:

```text
Use .github/copilot-instructions.md and .adk-engineering-skills.
Build this Google ADK agent with typed tools, session state, artifacts, evals, and tests.
```

## ADK-first development rule

Do not generate LangChain, CrewAI, or AutoGen code unless explicitly requested.
