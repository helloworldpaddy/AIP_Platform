"""Tool registry — maps a tool name to its async callable + JSON schema.

Used by `gemini_runner` to build the function declarations passed to
`google.genai` and to dispatch model-emitted tool calls back to Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

ToolFn = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]   # JSON Schema (object)
    fn: ToolFn


_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> ToolSpec:
    if spec.name in _REGISTRY:
        raise ValueError(f"tool {spec.name!r} already registered")
    _REGISTRY[spec.name] = spec
    return spec


def get_tool(name: str) -> ToolSpec:
    if name not in _REGISTRY:
        raise KeyError(f"unknown tool {name!r}")
    return _REGISTRY[name]


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())


def tools_named(names: list[str]) -> list[ToolSpec]:
    return [get_tool(n) for n in names]
