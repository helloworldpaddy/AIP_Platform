"""ADK-discoverable AML investigation stage agents (single source of truth).

Each subpackage exposes a module-level ``root_agent`` (a
:class:`google.adk.agents.LlmAgent`) in its ``agent.py``.  The same definitions
are used two ways:

* ``adk web backend/aml/agents/stages`` — discovers every stage here and loads
  each ``agent.py`` as a top-level package for interactive debugging.
* The FastAPI orchestrator imports the identical ``root_agent`` objects (via the
  per-stage subclasses in ``backend/aml/agents/<stage>.py``) to run them against
  the real database.

Stage ``agent.py`` modules use **absolute** imports plus a repo-root
``sys.path`` bootstrap so they import correctly under both the top-level name
(``initial_assessment``) used by ``adk web`` and the package path
(``backend.aml.agents.stages.initial_assessment``) used by the orchestrator.
"""
