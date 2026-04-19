"""
ADK agent wiring.

`root_agent` is picked up by ``adk run agents.rag_agent`` / ``adk web``.
The agent is a standard LlmAgent that owns a single retrieval tool plus
a strict, grounded system prompt.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agents.rag_agent.config.settings import get_settings
from agents.rag_agent.prompts import SYSTEM_INSTRUCTION
from agents.rag_agent.tools.ingest_tool import postgres_document_ingest_tool
from agents.rag_agent.tools.vector_search_tool import postgres_vector_search_tool
from agents.rag_agent.utils.logging_config import configure_logging
from agents.rag_agent.utils.telemetry import configure_telemetry


def build_agent() -> LlmAgent:
    configure_logging()
    configure_telemetry()

    settings = get_settings()

    return LlmAgent(
        name="rag_agent",
        model=settings.gemini.generation_model,
        description=(
            "Domain expert assistant that answers strictly from an internal "
            "knowledge base backed by PostgreSQL/pgvector, with AML-aware retrieval."
        ),
        instruction=SYSTEM_INSTRUCTION,
        tools=[postgres_vector_search_tool, postgres_document_ingest_tool],
    )


root_agent = build_agent()
