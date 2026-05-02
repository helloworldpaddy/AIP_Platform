# VS Code Support Skill

Use this skill when generating or modifying a Google ADK project for Visual Studio Code.

## Required VS Code files

Create:

```text
.vscode/
  settings.json
  extensions.json
  launch.json
  tasks.json
.github/
  copilot-instructions.md
```

## Recommended VS Code extensions

- Python
- Pylance
- Ruff
- Black Formatter
- GitHub Copilot
- GitHub Copilot Chat
- YAML
- Markdown All in One
- Docker
- Dev Containers

## VS Code engineering rules

1. Use a Python virtual environment named `.venv`.
2. Keep source code under `agents/`, `tools/`, and `common/`.
3. Use `pytest` for unit tests.
4. Use `ruff` for linting.
5. Use `black` for formatting.
6. Store secrets only in `.env`, never in source code.
7. Provide `.env.example`.
8. Add VS Code tasks for:
   - install dependencies
   - run ADK agent
   - open ADK web
   - run ADK eval
   - run tests
   - lint
   - format

## Example `.vscode/settings.json`

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "ms-python.black-formatter",
  "ruff.enable": true,
  "files.exclude": {
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/.ruff_cache": true
  }
}
```

## Example `.vscode/extensions.json`

```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "charliermarsh.ruff",
    "ms-python.black-formatter",
    "github.copilot",
    "github.copilot-chat",
    "redhat.vscode-yaml",
    "yzhang.markdown-all-in-one",
    "ms-azuretools.vscode-docker"
  ]
}
```

## Example `.vscode/tasks.json`

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Install dependencies",
      "type": "shell",
      "command": ".venv/bin/pip install -r requirements.txt",
      "problemMatcher": []
    },
    {
      "label": "ADK Run",
      "type": "shell",
      "command": ".venv/bin/adk run agents/aml_investigation",
      "problemMatcher": []
    },
    {
      "label": "ADK Web",
      "type": "shell",
      "command": ".venv/bin/adk web",
      "problemMatcher": []
    },
    {
      "label": "ADK Eval",
      "type": "shell",
      "command": ".venv/bin/adk eval agents/aml_investigation eval/",
      "problemMatcher": []
    },
    {
      "label": "Run Tests",
      "type": "shell",
      "command": ".venv/bin/pytest tests",
      "problemMatcher": []
    },
    {
      "label": "Lint",
      "type": "shell",
      "command": ".venv/bin/ruff check .",
      "problemMatcher": []
    },
    {
      "label": "Format",
      "type": "shell",
      "command": ".venv/bin/black .",
      "problemMatcher": []
    }
  ]
}
```

## Example `.vscode/launch.json`

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug ADK Agent",
      "type": "python",
      "request": "launch",
      "module": "google.adk.cli",
      "args": ["run", "agents/aml_investigation"],
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env"
    }
  ]
}
```
