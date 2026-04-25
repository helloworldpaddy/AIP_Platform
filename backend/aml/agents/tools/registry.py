"""Legacy tool registry — maps a tool name to its async callable + JSON schema.

Predates the ADK migration; kept because tests and a couple of utilities
still introspect `ToolSpec` to discover available tools.  Production agents
no longer route through it — they use the `ADK_TOOLS` map in `tools/__init__`
which exposes the same callables as `google.adk.tools.FunctionTool` wrappers.
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
