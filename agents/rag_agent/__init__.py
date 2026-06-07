"""ADK RAG agent with Postgres/pgvector + Gemini."""
# --- ADK compatibility shim ---
# ADK's agent loader imports this package as top-level `rag_agent`. Our internal
# modules use absolute imports of the form `from agents.rag_agent.xxx import Y`,
# so we register an alias before any internal imports run.
import sys as _sys
import types as _types
from pathlib import Path as _Path

if "agents" not in _sys.modules:
    _agents_pkg = _types.ModuleType("agents")
    _agents_pkg.__path__ = [str(_Path(__file__).resolve().parents[1])]
    _sys.modules["agents"] = _agents_pkg
_sys.modules.setdefault("agents.rag_agent", _sys.modules[__name__])


def __getattr__(name: str):
    """Lazy-load ADK agent so `agents.rag_agent.config.settings` (and AML DB
    client) can import without pulling `google.adk` at package import time."""
    if name == "root_agent":
        from agents.rag_agent.agent import root_agent as _root_agent

        return _root_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["root_agent"]
