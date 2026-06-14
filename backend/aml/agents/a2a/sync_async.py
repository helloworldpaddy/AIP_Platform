"""Run async setup from sync uvicorn factory entrypoints."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


def run_coroutine_sync(coro: Coroutine[object, object, T]) -> T:
    """Execute ``coro`` from sync code.

    Uvicorn's ``--factory`` loader may call ``get_app()`` while an event loop is
    already running (uvloop). ``asyncio.run()`` then fails; delegate to a fresh
    loop in a worker thread instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
