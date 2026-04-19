"""
OpenTelemetry bootstrap + convenience helpers.

If `OTEL_EXPORTER_OTLP_ENDPOINT` is unset, tracing is a no-op — we still
create spans but they're dropped. This keeps production and local dev
code identical.
"""
from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from typing import Any, Callable

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from agents.rag_agent.config.settings import get_settings

_initialized = False


def configure_telemetry() -> None:
    global _initialized
    if _initialized:
        return
    settings = get_settings().observability
    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)

    if settings.otlp_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
        )
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer(name: str = "adk-rag"):
    configure_telemetry()
    return trace.get_tracer(name)


def get_meter(name: str = "adk-rag"):
    return metrics.get_meter(name)


# Convenience meters — register once per process.
_meter = get_meter()
RETRIEVAL_LATENCY = _meter.create_histogram(
    "rag.retrieval.latency_ms", unit="ms", description="Retrieval latency"
)
LLM_LATENCY = _meter.create_histogram(
    "rag.llm.latency_ms", unit="ms", description="LLM generation latency"
)
EMBED_LATENCY = _meter.create_histogram(
    "rag.embed.latency_ms", unit="ms", description="Embedding generation latency"
)
QUERY_COUNTER = _meter.create_counter(
    "rag.queries.total", description="Total queries handled"
)
CACHE_HITS = _meter.create_counter(
    "rag.cache.hits", description="Cache hits"
)
CACHE_MISSES = _meter.create_counter(
    "rag.cache.misses", description="Cache misses"
)


@contextmanager
def traced(span_name: str, **attributes: Any):
    """Context manager that produces a span and records duration to telemetry."""
    tracer = get_tracer()
    t0 = time.perf_counter()
    with tracer.start_as_current_span(span_name) as span:
        for k, v in attributes.items():
            span.set_attribute(k, v)
        try:
            yield span
        finally:
            dt_ms = (time.perf_counter() - t0) * 1000
            span.set_attribute("duration_ms", dt_ms)


def timed(histogram, label: str | None = None):
    """Decorator that records execution time to a histogram (sync or async)."""
    def decorator(fn: Callable):
        if _is_coroutine(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    histogram.record((time.perf_counter() - t0) * 1000,
                                      attributes={"op": label or fn.__name__})
            return awrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                histogram.record((time.perf_counter() - t0) * 1000,
                                  attributes={"op": label or fn.__name__})
        return wrapper
    return decorator


def _is_coroutine(fn: Callable) -> bool:
    import asyncio
    return asyncio.iscoroutinefunction(fn)
