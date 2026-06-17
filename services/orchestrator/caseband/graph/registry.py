"""registry — a typed, reusable tool catalogue the agents draw from.

A tool is declared once and any agent can call it. Each tool says whether it's a
deterministic gate or an LLM op, carries a JSON-schema for its args, and exposes
an OpenAI function-calling schema so a live agent can pick it dynamically."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    fn: Callable
    kind: str = "llm"                       # "llm" | "det"
    params: dict = field(default_factory=lambda: {"type": "object", "properties": {}})

    def openai_schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.params}}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def add(self, name, description, fn, *, kind="llm", params=None) -> None:
        self.register(ToolSpec(name, description, fn, kind, params or
                               {"type": "object", "properties": {}}))

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"no tool {name!r}; have {sorted(self._tools)}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def openai_schemas(self) -> list[dict]:
        return [t.openai_schema() for t in self._tools.values()]

    def call(self, name: str, args: dict) -> Any:
        return self.get(name).fn(**(args or {}))
