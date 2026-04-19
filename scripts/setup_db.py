"""
Initialize the Postgres schema.

Usage:
    python scripts/setup_db.py
    python scripts/setup_db.py --drop   # DESTRUCTIVE — wipe the documents table first
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.rag_agent.config.settings import get_settings
from agents.rag_agent.db.postgres_client import get_postgres_client
from agents.rag_agent.utils.logging_config import configure_logging, get_logger


async def main(drop: bool) -> None:
    configure_logging()
    log = get_logger("setup_db")
    settings = get_settings()
    client = get_postgres_client()
    schema_path = Path(__file__).resolve().parents[1] / "agents" / "rag_agent" / "db" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8").format(
        embedding_dim=settings.gemini.embedding_dim,
        ivfflat_lists=settings.retrieval.ivfflat_lists,
    )

    await client.connect()
    try:
        if drop:
            log.warning("dropping existing documents table")
            await client.execute_sql("DROP TABLE IF EXISTS documents CASCADE")
        await client.execute_sql(schema_sql)
        log.info(
            "schema.applied",
            embedding_dim=settings.gemini.embedding_dim,
            ivfflat_lists=settings.retrieval.ivfflat_lists,
        )
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drop", action="store_true", help="Drop the documents table first")
    args = parser.parse_args()
    asyncio.run(main(args.drop))
