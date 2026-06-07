"""Deployable ADK FastAPI server for the AML investigation stage agents.

This is the Cloud Run entrypoint produced from the ``agents-cli`` ``adk``
template (Cloud Run target) and adapted to this monorepo.  It serves the
**same** agents discovered by ``adk web backend/aml/agents/stages`` — the four
investigation stages plus the policy ``rag_agent`` — via ADK's
``get_fast_api_app`` (interactive dev UI at ``/dev-ui`` + the ADK REST API).

Run locally::

    uvicorn backend.aml.agents.fast_api_app:app --host 0.0.0.0 --port 8080

The production analyst surface remains :mod:`backend.aml.main` (the
orchestrator API the React frontend calls); this server is an additional,
deployable ``adk web``-parity service.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

#: Parent directory that ADK scans for agent packages (each exposes root_agent).
AGENTS_DIR = str(Path(__file__).resolve().parent / "stages")

_allow = os.getenv("ALLOW_ORIGINS")
allow_origins = [o.strip() for o in _allow.split(",") if o.strip()] if _allow else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    web=True,
    allow_origins=allow_origins,
    session_service_uri=os.getenv("SESSION_SERVICE_URI") or None,
    artifact_service_uri=os.getenv("ARTIFACT_SERVICE_URI") or None,
    otel_to_cloud=os.getenv("OTEL_TO_CLOUD", "false").lower() == "true",
)
app.title = "AML Investigation Agents (ADK)"
app.description = (
    "ADK web + REST surface for the AML investigation stage agents "
    "(initial_assessment, transaction_enrichment, due_diligence, "
    "case_analysis, rag_agent)."
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
