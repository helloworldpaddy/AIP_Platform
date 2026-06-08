"""HMAC-signed tokens for run-scoped tool gateway access."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from uuid import UUID

from ...models.enums import AgentName


@dataclass(frozen=True)
class ToolGatewayClaims:
    run_id: UUID
    case_id: UUID
    agent: AgentName
    allowed_tools: tuple[str, ...]
    exp: int


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def tool_gateway_secret() -> bytes:
    raw = os.getenv("AML_TOOL_GATEWAY_SECRET", "aml-dev-tool-gateway-secret")
    return raw.encode("utf-8")


def mint_tool_gateway_token(
    *,
    claims: ToolGatewayClaims,
    secret: bytes | None = None,
) -> str:
    secret = secret or tool_gateway_secret()
    payload = {
        "run_id": str(claims.run_id),
        "case_id": str(claims.case_id),
        "agent": claims.agent.value,
        "allowed_tools": list(claims.allowed_tools),
        "exp": claims.exp,
    }
    body = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    sig = _b64url_encode(
        hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{body}.{sig}"


def verify_tool_gateway_token(
    token: str,
    *,
    secret: bytes | None = None,
) -> ToolGatewayClaims:
    secret = secret or tool_gateway_secret()
    try:
        body, sig = token.split(".", 1)
    except ValueError as err:
        raise ValueError("invalid tool gateway token format") from err

    expected = _b64url_encode(
        hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(sig, expected):
        raise ValueError("invalid tool gateway token signature")

    payload = json.loads(_b64url_decode(body))
    if int(payload["exp"]) < int(time.time()):
        raise ValueError("tool gateway token expired")

    return ToolGatewayClaims(
        run_id=UUID(payload["run_id"]),
        case_id=UUID(payload["case_id"]),
        agent=AgentName(payload["agent"]),
        allowed_tools=tuple(payload.get("allowed_tools") or ()),
        exp=int(payload["exp"]),
    )
