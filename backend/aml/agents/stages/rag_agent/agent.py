"""Policy RAG agent — thin re-export for unified ``adk web`` discovery.

The canonical RAG agent lives in the self-contained ``agents.rag_agent``
package (PostgreSQL/pgvector + Gemini, with its own ADK import shim).  This
module re-exports its ``root_agent`` so a single
``adk web backend/aml/agents/stages`` lists the policy RAG agent alongside the
four AML investigation stages.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.rag_agent.agent import root_agent  # noqa: E402,F401

__all__ = ["root_agent"]
