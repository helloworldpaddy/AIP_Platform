"""
Structured JSON logging bootstrap.

structlog and the stdlib ``logging`` module both need to end up rendering
JSON once — not twice. The pattern below:

    - structlog loggers produce an event dict and hand it off to the stdlib
      handler via ``ProcessorFormatter.wrap_for_formatter``
    - the stdlib handler applies a single ``ProcessorFormatter`` that runs
      the shared processor chain and then renders JSON

Net result: one JSON line per log event, regardless of whether the call
site uses structlog or stdlib ``logging``.
"""
from __future__ import annotations

import logging
import sys

import structlog

from agents.rag_agent.config.settings import get_settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    level_name = get_settings().observability.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Structlog loggers: do NOT render here — wrap the event for the stdlib
    # formatter so the final JSONRenderer runs exactly once.
    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Stdlib handler: runs `foreign_pre_chain` only on non-structlog records,
    # then the shared final processors render JSON for everything.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    _configured = True


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
