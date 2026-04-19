"""
Async PostgreSQL client using an asyncpg connection pool.

The module exposes a singleton `get_postgres_client()` and a thin
`PostgresClient` wrapper that handles:
    - Pool lifecycle
    - pgvector codec registration (so we can pass list[float] directly)
    - JSONB codec registration (so we can pass dict directly)
    - Typed helpers for upsert / similarity / hybrid search
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Iterable, Sequence

import asyncpg
from pgvector.asyncpg import register_vector

from agents.rag_agent.config.settings import get_settings

log = logging.getLogger(__name__)


class PostgresClient:
    def __init__(self) -> None:
        self._settings = get_settings().database
        self._retrieval = get_settings().retrieval
        self._pool: asyncpg.Pool | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ pool
    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        # Ensure pgvector is installed before we try to register its codec.
        # Idempotent — safe on every new pooled connection.
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(conn)
        await conn.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )
        if self._settings.statement_timeout_ms:
            await conn.execute(
                f"SET statement_timeout = {int(self._settings.statement_timeout_ms)}"
            )
        # Improve recall for IVFFlat at query time.
        await conn.execute(f"SET ivfflat.probes = {self._retrieval.ivfflat_probes}")

    async def connect(self) -> None:
        if self._pool is not None:
            return
        async with self._lock:
            if self._pool is not None:
                return
            self._pool = await asyncpg.create_pool(
                dsn=self._settings.dsn,
                min_size=self._settings.pool_min,
                max_size=self._settings.pool_max,
                init=self._init_connection,
            )
            log.info(
                "postgres.pool.connected",
                extra={"host": self._settings.host, "db": self._settings.name},
            )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Postgres pool not initialized — call connect() first")
        return self._pool

    # -------------------------------------------------------------- schema ops
    async def execute_sql(self, sql: str) -> None:
        await self.connect()
        async with self.pool.acquire() as conn:
            await conn.execute(sql)

    # ------------------------------------------------------------------ writes
    async def upsert_chunks(
        self,
        rows: Sequence[dict[str, Any]],
    ) -> int:
        """Bulk upsert chunk rows. Returns count inserted/updated."""
        if not rows:
            return 0
        await self.connect()
        query = """
            INSERT INTO documents
                (document_id, chunk_index, source, content, embedding, metadata)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (document_id, chunk_index) DO UPDATE
                SET content   = EXCLUDED.content,
                    source    = EXCLUDED.source,
                    embedding = EXCLUDED.embedding,
                    metadata  = EXCLUDED.metadata
        """
        values: list[tuple[Any, ...]] = [
            (
                r["document_id"],
                r["chunk_index"],
                r["source"],
                r["content"],
                r["embedding"],
                r.get("metadata", {}),
            )
            for r in rows
        ]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(query, values)
        return len(values)

    async def delete_by_document_id(self, document_id: str) -> int:
        await self.connect()
        async with self.pool.acquire() as conn:
            res = await conn.execute(
                "DELETE FROM documents WHERE document_id = $1", document_id
            )
        # asyncpg returns "DELETE <count>"
        try:
            return int(res.split()[-1])
        except (ValueError, IndexError):
            return 0

    # -------------------------------------------------------------- retrieval
    async def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Pure vector cosine similarity search.

        Returns rows with `score` = 1 - cosine_distance (higher is better).
        """
        await self.connect()
        where, params = _metadata_where(metadata_filter, start_idx=2)
        sql = f"""
            SELECT id, document_id, chunk_index, source, content, metadata,
                   1 - (embedding <=> $1) AS score
            FROM documents
            {where}
            ORDER BY embedding <=> $1
            LIMIT ${len(params) + 2}
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, query_embedding, *params, top_k)
        return [dict(r) for r in rows]

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        top_k: int,
        vector_weight: float,
        bm25_weight: float,
        metadata_filter: dict[str, Any] | None = None,
        candidate_pool: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Reciprocal Rank Fusion of vector + lexical search.

        Both sub-queries pull `candidate_pool` rows; results are fused by
        weighted normalized rank-reciprocal scoring.
        """
        await self.connect()
        vec_where, params = _metadata_where(metadata_filter, start_idx=3)
        # For the lexical CTE we already have a WHERE; attach metadata as AND.
        lex_where_extra = (
            f"AND metadata @> $3::jsonb" if metadata_filter else ""
        )

        sql = f"""
        WITH
        vec AS (
            SELECT id, document_id, chunk_index, source, content, metadata,
                   1 - (embedding <=> $1) AS vscore,
                   row_number() OVER (ORDER BY embedding <=> $1) AS vrank
            FROM documents
            {vec_where}
            ORDER BY embedding <=> $1
            LIMIT ${len(params) + 3}
        ),
        lex AS (
            SELECT id, document_id, chunk_index, source, content, metadata,
                   ts_rank_cd(tsv, plainto_tsquery('english', $2)) AS lscore,
                   row_number() OVER (
                       ORDER BY ts_rank_cd(tsv, plainto_tsquery('english', $2)) DESC
                   ) AS lrank
            FROM documents
            WHERE tsv @@ plainto_tsquery('english', $2)
            {lex_where_extra}
            ORDER BY lscore DESC
            LIMIT ${len(params) + 3}
        ),
        fused AS (
            SELECT
                COALESCE(vec.id, lex.id) AS id,
                COALESCE(vec.document_id, lex.document_id) AS document_id,
                COALESCE(vec.chunk_index, lex.chunk_index) AS chunk_index,
                COALESCE(vec.source, lex.source) AS source,
                COALESCE(vec.content, lex.content) AS content,
                COALESCE(vec.metadata, lex.metadata) AS metadata,
                COALESCE(1.0 / (60 + vec.vrank), 0) * {float(vector_weight)}
                  + COALESCE(1.0 / (60 + lex.lrank), 0) * {float(bm25_weight)} AS score
            FROM vec
            FULL OUTER JOIN lex USING (id)
        )
        SELECT id, document_id, chunk_index, source, content, metadata, score
        FROM fused
        ORDER BY score DESC
        LIMIT ${len(params) + 4}
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                sql, query_embedding, query_text, *params, candidate_pool, top_k
            )
        return [dict(r) for r in rows]

    async def entity_boosted_search(
        self,
        query_embedding: list[float],
        entities: Iterable[str],
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Vector search with a trigram similarity boost for any of `entities`
        (e.g. party names, aliases). Tolerates spelling variations.
        """
        await self.connect()
        entity_list = [e for e in entities if e and e.strip()]
        if not entity_list:
            return await self.similarity_search(query_embedding, top_k, metadata_filter)

        where, params = _metadata_where(metadata_filter, start_idx=3)
        sql = f"""
            SELECT id, document_id, chunk_index, source, content, metadata,
                   (1 - (embedding <=> $1)) * 0.7
                     + greatest_similarity(content, $2) * 0.3 AS score
            FROM documents
            {where}
            ORDER BY score DESC
            LIMIT ${len(params) + 3}
        """
        # We install `greatest_similarity` as a helper below if missing.
        await self._ensure_greatest_similarity()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, query_embedding, entity_list, *params, top_k)
        return [dict(r) for r in rows]

    async def _ensure_greatest_similarity(self) -> None:
        """Create a helper SQL function if it doesn't exist yet."""
        await self.execute_sql(
            """
            CREATE OR REPLACE FUNCTION greatest_similarity(txt TEXT, needles TEXT[])
            RETURNS REAL AS $$
                SELECT COALESCE(MAX(similarity(txt, n)), 0) FROM unnest(needles) AS n;
            $$ LANGUAGE SQL IMMUTABLE;
            """
        )


def _metadata_where(
    metadata_filter: dict[str, Any] | None,
    start_idx: int = 1,
) -> tuple[str, list[Any]]:
    """
    Build a ``WHERE metadata @> $N`` clause + params.
    Supports equality filtering via JSONB containment.
    """
    if not metadata_filter:
        return "", []
    return f"WHERE metadata @> ${start_idx}::jsonb", [json.dumps(metadata_filter)]


_client_singleton: PostgresClient | None = None


def get_postgres_client() -> PostgresClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = PostgresClient()
    return _client_singleton
