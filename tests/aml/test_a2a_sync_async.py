"""Tests for A2A app factory helpers."""

from __future__ import annotations

import asyncio

import pytest

from backend.aml.agents.a2a.sync_async import run_coroutine_sync


@pytest.mark.asyncio
async def test_run_coroutine_sync_from_running_loop():
    async def _inner() -> str:
        return "ok"

    async def _caller() -> str:
        return run_coroutine_sync(_inner())

    assert await _caller() == "ok"


def test_run_coroutine_sync_without_loop():
    async def _inner() -> int:
        return 42

    assert run_coroutine_sync(_inner()) == 42
