"""
End-to-end query runner (bypasses the ADK runtime).

This is the fastest way to smoke-test ingestion + retrieval + generation
without spinning up the ADK web UI or CLI runner.

Usage:
    python scripts/query.py "Who is the beneficial owner of ACME Holdings?"
    python scripts/query.py "OFAC sanctions in Russia" --top-k 8
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google import genai
from google.genai import types as genai_types

from agents.rag_agent.config.settings import get_settings
from agents.rag_agent.db.postgres_client import get_postgres_client
from agents.rag_agent.prompts import ANSWER_TEMPLATE, SYSTEM_INSTRUCTION, format_context
from agents.rag_agent.services.retrieval_service import get_retrieval_service
from agents.rag_agent.utils.logging_config import configure_logging, get_logger


def _build_client(settings) -> genai.Client:
    if settings.gemini.use_vertex:
        return genai.Client(
            vertexai=True,
            project=settings.gemini.project,
            location=settings.gemini.location,
        )
    api_key = (
        settings.gemini.api_key.get_secret_value()
        if settings.gemini.api_key else None
    )
    return genai.Client(api_key=api_key)


async def main(query: str, top_k: int) -> None:
    configure_logging()
    log = get_logger("query")
    settings = get_settings()

    retriever = get_retrieval_service()
    try:
        chunks = await retriever.retrieve(query, top_k=top_k)
        context = format_context(chunks)

        client = _build_client(settings)
        prompt = ANSWER_TEMPLATE.format(
            retrieved_chunks=context, user_query=query
        )

        def _generate():
            return client.models.generate_content(
                model=settings.gemini.generation_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.1,
                ),
            )

        resp = await asyncio.to_thread(_generate)
        answer = resp.text if hasattr(resp, "text") else str(resp)

        print("\n" + "=" * 72)
        print("QUERY:", query)
        print("=" * 72)
        print(answer)
        print("=" * 72)
        print(f"[retrieved {len(chunks)} chunks]")
        for c in chunks:
            print(
                f"  • {c.metadata.get('filename', c.source)}"
                f"#{c.chunk_index}  score={c.score:.3f}"
            )

        log.info("query.done", chunks=len(chunks), answer_chars=len(answer))
    finally:
        await get_postgres_client().close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="Natural-language query")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(main(args.query, args.top_k))
