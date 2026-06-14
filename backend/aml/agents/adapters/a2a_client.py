"""Low-level A2A client used by :class:`A2aAdapter`."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from a2a.client.card_resolver import A2ACardResolver
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import Message, Part, Role, Task, TaskQueryParams, TaskState, TextPart
from a2a.utils.message import get_message_text

log = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 1.0

_TERMINAL_TASK_STATES = frozenset(
    {
        TaskState.completed,
        TaskState.failed,
        TaskState.canceled,
        TaskState.rejected,
    }
)


class A2aRemoteError(RuntimeError):
    """Raised when a remote stage returns a failed or empty A2A response."""


@dataclass
class A2aRemoteResponse:
    final_text: str
    task_id: str | None = None
    context_id: str | None = None
    task_state: TaskState | None = None


class A2aRemoteClient:
    """Resolve an agent card and send one user turn via the A2A protocol."""

    def __init__(
        self,
        *,
        agent_card_url: str,
        timeout_seconds: float = 600.0,
        httpx_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._agent_card_url = agent_card_url.strip()
        self._timeout_seconds = timeout_seconds
        self._httpx_client = httpx_client
        self._owns_client = httpx_client is None
        self._client = None
        self._factory: ClientFactory | None = None

    async def _ensure_client(self):
        if self._client is not None:
            return self._client

        if self._httpx_client is None:
            self._httpx_client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout=self._timeout_seconds)
            )
            self._owns_client = True

        parsed = urlparse(self._agent_card_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"invalid agent card URL: {self._agent_card_url!r}")
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        resolver = A2ACardResolver(
            httpx_client=self._httpx_client,
            base_url=base_url,
        )
        card = await resolver.get_agent_card(relative_card_path=parsed.path)
        config = ClientConfig(
            httpx_client=self._httpx_client,
            streaming=False,
            polling=False,
        )
        self._factory = ClientFactory(config=config)
        self._client = self._factory.create(card)
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._httpx_client is not None:
            await self._httpx_client.aclose()
        self._httpx_client = None
        self._client = None
        self._factory = None

    async def send_turn(
        self,
        *,
        user_message: str,
        request_metadata: dict[str, Any] | None = None,
    ) -> A2aRemoteResponse:
        client = await self._ensure_client()
        message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=user_message))],
            message_id=str(uuid.uuid4()),
        )

        final_text = ""
        task_id: str | None = None
        context_id: str | None = None
        task_state: TaskState | None = None

        async for event in client.send_message(
            request=message,
            request_metadata=request_metadata,
        ):
            if isinstance(event, Message):
                final_text = get_message_text(event)
                context_id = event.context_id or context_id
                task_id = event.task_id or task_id
                continue

            if not isinstance(event, tuple):
                continue

            task, _update = event
            if task is None:
                continue
            task_id, context_id, task_state, final_text = _merge_task_snapshot(
                task,
                task_id=task_id,
                context_id=context_id,
                task_state=task_state,
                final_text=final_text,
            )

        if task_id and (
            not _is_terminal_task_state(task_state) or not final_text.strip()
        ):
            task_id, context_id, task_state, final_text = await self._poll_task(
                client,
                task_id=task_id,
                context_id=context_id,
                task_state=task_state,
                final_text=final_text,
            )

        if task_state == TaskState.failed:
            raise A2aRemoteError(
                f"remote A2A task failed (task_id={task_id}) text={final_text[:400]!r}"
            )
        if not final_text.strip():
            raise A2aRemoteError(
                f"remote A2A agent returned no text (task_id={task_id}, state={task_state})"
            )

        return A2aRemoteResponse(
            final_text=final_text,
            task_id=task_id,
            context_id=context_id,
            task_state=task_state,
        )

    async def _poll_task(
        self,
        client,
        *,
        task_id: str,
        context_id: str | None,
        task_state: TaskState | None,
        final_text: str,
    ) -> tuple[str, str | None, TaskState | None, str]:
        """Poll ``tasks/get`` until the task is terminal or the timeout elapses."""
        deadline = time.monotonic() + self._timeout_seconds
        while time.monotonic() < deadline:
            if _is_terminal_task_state(task_state) and final_text.strip():
                break

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            task = await client.get_task(TaskQueryParams(id=task_id))
            task_id, context_id, task_state, final_text = _merge_task_snapshot(
                task,
                task_id=task_id,
                context_id=context_id,
                task_state=task_state,
                final_text=final_text,
            )

        return task_id, context_id, task_state, final_text


def _is_terminal_task_state(state: TaskState | None) -> bool:
    return state in _TERMINAL_TASK_STATES


def _merge_task_snapshot(
    task: Task,
    *,
    task_id: str | None,
    context_id: str | None,
    task_state: TaskState | None,
    final_text: str,
) -> tuple[str, str | None, TaskState | None, str]:
    task_id = task.id or task_id
    context_id = task.context_id or context_id
    if task.status is not None:
        task_state = task.status.state
        if task.status.message is not None:
            status_text = get_message_text(task.status.message)
            if status_text.strip():
                final_text = status_text
    extracted = _extract_agent_text(task)
    if extracted:
        final_text = extracted
    return task_id, context_id, task_state, final_text


def _extract_agent_text(task: Task) -> str:
    history = list(task.history or [])
    for message in reversed(history):
        if message.role == Role.agent:
            text = get_message_text(message)
            if text.strip():
                return text
    if task.artifacts:
        chunks: list[str] = []
        for artifact in task.artifacts:
            for part in artifact.parts or []:
                root = getattr(part, "root", None)
                if root is not None and hasattr(root, "text") and root.text:
                    chunks.append(str(root.text))
        if chunks:
            return "\n".join(chunks)
    return ""
