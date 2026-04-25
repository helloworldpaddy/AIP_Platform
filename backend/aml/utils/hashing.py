"""Deterministic hashing helpers used across the data layer.

Two main use cases:

* `content_hash(...)` — sha256 of canonicalised evidence content.  Used by the
  `evidence_ledger.content_hash` UNIQUE constraint to make ingestion idempotent
  and to detect tampering.
* `idempotency_key(...)` — sha256 of (case_id, agent, logical input version).
  Used by `agent_runs.idempotency_key` so a re-trigger after a network failure
  resumes the same run instead of creating a duplicate.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID


def _canonical_json(value: Any) -> str:
    """JSON dump with stable key ordering and no insignificant whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_hash(
    *,
    source_system: str,
    source_uri: str | None,
    title: str,
    content: str,
    structured_data: dict[str, Any] | None = None,
) -> str:
    """Stable hash of an evidence record's identifying fields."""
    payload = {
        "source_system": source_system.strip().lower(),
        "source_uri": (source_uri or "").strip(),
        "title": title.strip(),
        "content": content.strip(),
        "structured_data": structured_data or {},
    }
    return sha256_hex(_canonical_json(payload))


def idempotency_key(
    *,
    case_id: UUID | str,
    agent: str,
    input_payload: dict[str, Any],
) -> str:
    """Stable key for resumable agent triggers.

    Callers that want a fresh run (e.g. analyst clicked "re-run") can append a
    version / nonce to `input_payload` to deliberately mint a new key.
    """
    payload = {
        "case_id": str(case_id),
        "agent": agent,
        "input": input_payload,
    }
    return sha256_hex(_canonical_json(payload))
