"""
Optional Redis cache for embeddings and retrieval results.

When `cache.enabled=false`, the cache becomes a transparent no-op so the
calling code doesn't need feature flags.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from agents.rag_agent.config.settings import get_settings
from agents.rag_agent.utils.telemetry import CACHE_HITS, CACHE_MISSES

log = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis  # type: ignore
except ImportError:  # redis is optional
    aioredis = None


def _hash_key(prefix: str, payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(serialized).hexdigest()}"


class Cache:
    def __init__(self) -> None:
        self._settings = get_settings().cache
        self._redis = None

    async def _client(self):
        if not self._settings.enabled or aioredis is None:
            return None
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._settings.redis_url, encoding="utf-8", decode_responses=True
            )
        return self._redis

    async def get(self, namespace: str, key_payload: Any) -> Any | None:
        client = await self._client()
        if client is None:
            return None
        key = _hash_key(namespace, key_payload)
        try:
            raw = await client.get(key)
        except Exception as exc:
            log.warning("cache.get.failed", extra={"err": str(exc)})
            return None
        if raw is None:
            CACHE_MISSES.add(1, attributes={"namespace": namespace})
            return None
        CACHE_HITS.add(1, attributes={"namespace": namespace})
        return json.loads(raw)

    async def set(self, namespace: str, key_payload: Any, value: Any) -> None:
        client = await self._client()
        if client is None:
            return
        key = _hash_key(namespace, key_payload)
        try:
            await client.set(
                key, json.dumps(value), ex=self._settings.ttl_seconds
            )
        except Exception as exc:
            log.warning("cache.set.failed", extra={"err": str(exc)})


_cache_singleton: Cache | None = None


def get_cache() -> Cache:
    global _cache_singleton
    if _cache_singleton is None:
        _cache_singleton = Cache()
    return _cache_singleton
