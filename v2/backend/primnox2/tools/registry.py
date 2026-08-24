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
    # How this call is described in its permission prompt, when the generic
    # "description + manifest + arguments" rendering is not good enough.
    #
    # It exists for Computer Use. Everything else being gated is code Primnox
    # is about to run, and the arguments ARE the thing to read — a user
    # approving `run_python` wants to see the Python. A user approving control
    # of a window needs to read about that window, and `{"window": "win_262332_2504"}`
    # tells them nothing. The hook stays inside the runtime's gate rather than
    # letting the tool prompt for itself, so the invariant that a tool cannot
    # forget to ask is preserved.
    prompt: "Callable[[dict], str] | None" = None
    # Whether `PRIMNOX2_AUTO_APPROVE` may cover this tool. It may not cover
    # Computer Use, and the reason is structural rather than a matter of taste.
    #
    # Auto-approval is defensible for everything else here because the sandbox
    # boundary survives a bad generation: model-written Python runs in an
    # AppContainer with no network capability and no path out of its own
    # directory, so the prompt is a second line of defence behind a measured
    # first one. Computer Use has no first line. It operates the user's real
    # applications, which cannot be sandboxed even in principle, and the grant
    # IS the boundary. Auto-approving it does not weaken the defence, it
    # removes it — so these tools ask even when the setting says not to.
    always_ask: bool = False

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
        """How this tool is described to a model using the emulated protocol.

        Required parameters carry their description; optional ones do not.

        That split is the whole point rather than a saving. Every line here is
        charged to every turn forever, so the question for each one is what a
        wrong guess costs. Getting an optional argument wrong means a slightly
        worse call; getting a required one wrong means the call fails and the
        turn is spent recovering. `control_window` is the case that proved it:
        the shape alone says `"window": <string>`, and a model handed a window
        titled "Notepad" will pass "Notepad" — measured, four times out of
        four, on a model easily strong enough to know better. The text that
        would have prevented it ("A window handle from list_windows") was
        sitting in the parameter spec and never reached the model.
        """
        args = ", ".join(
            f'"{n}": <{m.get("type", "string")}>{"" if m.get("required") else "?"}'
            for n, m in self.parameters.items()
        )
        line = f'<tool name="{self.name}">{{{args}}}</tool>  — {self.description}'

        required = [(n, (m.get("description") or "").strip())
                    for n, m in self.parameters.items()
                    if m.get("required") and (m.get("description") or "").strip()]
        for name, description in required:
            line += f'\n    {name}: {description}'
        return line


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


# Tools that exist to drive another application's window. Named here rather
# than derived from the module they live in, because the grouping is about
# what a request is ABOUT, not about how the code is filed.
DESKTOP_TOOLS = frozenset({
    "list_windows", "control_window", "read_window", "read_page",
    "click_element", "type_into", "click_at", "scroll_window", "press_keys",
    "wait_for", "run_steps", "undo_last", "record_workflow",
    "replay_workflow", "end_control",
})


def describe_for_prompt(*, exclude_persistent: bool = False,
                        focus: "str | None" = None) -> str:
    """The tool catalogue, optionally narrowed to what this turn is about.

    Narrowing is not a capability change, and that is what makes it safe: the
    registry executes anything registered, and this string only ADVERTISES. A
    tool left out is still callable by name; it has simply stopped competing
    for attention.

    The competing is the measured problem. On qwen2.5:0.5b across ten desktop
    tasks, with all 29 tools described it picked the right tool 4 times and
    reached for `run_python` to type, click and press keys. With only the
    desktop tools described: 8. Nothing about the descriptions changed — a
    general-purpose tool is simply where a small model goes when it is
    unsure, and the way to stop that is to not offer it for work it cannot
    do.

    A prompt line saying as much in words was tried first and moved 4 to 5.
    The model was not reading that far.
    """
    specs = [s for s in all_specs() if not (exclude_persistent and s.persistent)]
    if focus == "desktop":
        chosen = [s for s in specs if s.name in DESKTOP_TOOLS]
        # Only narrow when there is something to narrow to. A build without
        # the desktop tools must not end up advertising nothing at all.
        if chosen:
            specs = chosen
    return "\n".join(s.to_grammar_line() for s in specs)


def json_schemas() -> list[dict]:
    return [s.to_json_schema() for s in all_specs()]
