"""Universal tool protocol — ARCH §5.2.

One schema, Primnox's own. Not OpenAI's, not Anthropic's. Provider adapters
translate to whatever a wire format demands; adding a provider never touches
this package.

That inversion is what makes model hot-swap possible: because the contract
belongs to the runtime, a conversation can move from Qwen to GPT-5 to DeepSeek
without its structure changing. Models become interchangeable compute.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from ..sandbox import permissions

# Danger drives how the permission prompt is phrased and whether an approval
# may be reused. It is not a substitute for the manifest — the manifest says
# what is actually granted.
LOW, MEDIUM, HIGH = "low", "medium", "high"


@dataclass
class ToolContext:
    """Everything a tool needs to behave like a conformant subsystem (§12)."""
    job_id: str | None = None
    turn_id: str | None = None
    conversation_id: str | None = None
    should_cancel: Callable[[], bool] = lambda: False
    ask_permission: Callable[..., str] | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, dict]
    handler: Callable[[dict, ToolContext], dict]
    danger: str = LOW
    cancellable: bool = True
    manifest: permissions.Manifest | None = None
    # Whether running this leaves something behind on disk — an execution
    # session and its logs, a workspace and its versions. Declared per tool
    # rather than inferred, because "does this persist" is not the same
    # question as "is this dangerous": creating a workspace is completely safe
    # and entirely durable. An incognito turn (§11.2.4) may not use these.
    persistent: bool = False

    def required(self) -> list[str]:
        return [k for k, v in self.parameters.items() if v.get("required")]

    def validate(self, arguments: dict) -> list[str]:
        errors = []
        for key in self.required():
            if key not in arguments or arguments[key] in (None, ""):
                errors.append(f"missing required argument {key!r}")
        for key in arguments:
            if key not in self.parameters:
                errors.append(f"unknown argument {key!r}")
        return errors

    def to_json_schema(self) -> dict:
        """OpenAI-shaped function schema, for adapters that want one."""
        props = {}
        for name, meta in self.parameters.items():
            props[name] = {"type": meta.get("type", "string"),
                           "description": meta.get("description", "")}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": props,
                               "required": self.required()},
            },
        }

    def to_grammar_line(self) -> str:
        """How this tool is described to a model using the emulated protocol."""
        args = ", ".join(
            f'"{n}": <{m.get("type", "string")}>{"" if m.get("required") else "?"}'
            for n, m in self.parameters.items()
        )
        return f'<tool name="{self.name}">{{{args}}}</tool>  — {self.description}'


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def all_specs() -> list[ToolSpec]:
    return sorted(_REGISTRY.values(), key=lambda s: s.name)


def tool_names() -> list[str]:
    return [s.name for s in all_specs()]


def describe_for_prompt(*, exclude_persistent: bool = False) -> str:
    specs = [s for s in all_specs() if not (exclude_persistent and s.persistent)]
    return "\n".join(s.to_grammar_line() for s in specs)


def json_schemas() -> list[dict]:
    return [s.to_json_schema() for s in all_specs()]
