"""
Batch ingestion script.

Usage:
    python scripts/ingest.py --path ./data/samples
    python scripts/ingest.py --path ./docs/policies.pdf --tags policy,aml
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.rag_agent.db.postgres_client import get_postgres_client
from agents.rag_agent.services.ingestion_service import get_ingestion_service
from agents.rag_agent.utils.logging_config import configure_logging, get_logger


async def main(path: str, tags: list[str]) -> None:
    configure_logging()
    log = get_logger("ingest")
    ingestion = get_ingestion_service()
    try:
        results = await ingestion.ingest_path(path, tags=tags)
        total_chunks = sum(r.chunks_written for r in results)
        log.info(
            "ingest.batch.done",
            files=len(results),
            chunks=total_chunks,
        )
        for r in results:
            print(f"{r.source}  chunks={r.chunks_written}  ms={r.duration_ms:.0f}")
    finally:
        await get_postgres_client().close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True, help="File or directory to ingest")
    parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated list of tags attached to every chunk's metadata",
    )
    args = parser.parse_args()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    asyncio.run(main(args.path, tags))
