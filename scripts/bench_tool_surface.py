"""Can a small model actually pick the right desktop tool?

The plan says shrink the model-facing surface to `observe / act / wait /
verify / ask`. That is a plausible-sounding change with a real cost — a tool
NAME may be a stronger signal for a weak model than a verb nested inside an
enum, and collapsing fifteen names into five trades one kind of difficulty for
another. This codebase decides that sort of question by measuring it.

So: the same tasks, the same model, two surfaces, and a number.

What is measured, per task, from the model's FIRST reply:

    call        did it emit a tool call at all, in any of the accepted shapes
    right       was it the tool the task needs
    args        did the arguments survive the real validator

Those are three separate failures with three different fixes, and reporting
them as one score hides which one is happening. A model that names the right
tool in prose without calling it needs the grammar taught; one that calls the
wrong tool needs better descriptions; one that calls the right tool with junk
arguments needs the parameter docs it was not being given.

Everything goes through the REAL parser and the REAL registry. A harness that
reimplements either measures the harness.

Usage:
    python scripts/bench_tool_surface.py [--model qwen2.5:0.5b] [--runs 1]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "v2" / "backend"))

from primnox2.tools import runtime                       # noqa: E402
from primnox2.tools.registry import get, tool_names      # noqa: E402

OLLAMA = "http://127.0.0.1:11434/api/chat"

# Each task is a plain request plus the state the conversation is already in,
# because "type hello into it" is only answerable when something has been
# read. The accepted set is deliberately more than one where more than one
# answer is genuinely correct — counting a defensible choice as a failure
# makes the benchmark measure agreement with me rather than capability.
# `prior` is (the tool the model already called, the result it got back), and
# it is replayed through the REAL formatter into the REAL message shape the
# scheduler uses — assistant turn carrying the call, user turn carrying
# `format_result`. Describing the state in prose instead measures whether the
# model can follow a narration, which is not a situation it will ever be in.
TASKS = [
    ("what windows are open?", None, {"list_windows"}),
    ("take control of the window called Notepad",
     ("list_windows", "2 windows: win_1234_56 'Untitled - Notepad' "
                      "(notepad.exe); win_9876_54 'Inbox' (olk.exe)"),
     {"control_window"}),
    ("what is in that window?",
     ("control_window", "Session open on Untitled - Notepad (300s remaining)."),
     {"read_window", "read_page"}),
    ("type hello into it",
     ("read_window", "read 3 elements from Untitled - Notepad\n"
                     "  [e4@1] Edit 'Document' can=set_value"),
     {"type_into", "run_steps"}),
    ("click the Save button",
     ("read_window", "read 3 elements from Untitled - Notepad\n"
                     "  [e7@1] Button 'Save' can=invoke"),
     {"click_element", "run_steps"}),
    ("press ctrl+s",
     ("control_window", "Session open on Untitled - Notepad (300s remaining)."),
     {"press_keys", "run_steps"}),
    ("scroll down in that window",
     ("control_window", "Session open on Untitled - Notepad (300s remaining)."),
     {"scroll_window", "run_steps"}),
    ("wait until the Save button is enabled",
     ("read_window", "read 3 elements from Untitled - Notepad\n"
                     "  [e7@1] Button 'Save' can=invoke DISABLED"),
     {"wait_for", "run_steps"}),
    ("stop controlling the window",
     ("control_window", "Session open on Untitled - Notepad (300s remaining)."),
     {"end_control"}),
    ("type hello and then click Save",
     ("read_window", "read 4 elements from Untitled - Notepad\n"
                     "  [e4@1] Edit 'Document' can=set_value\n"
                     "  [e7@1] Button 'Save' can=invoke"),
     {"run_steps", "type_into"}),
]


def ask(model: str, system: str, user: str, context: "str | None") -> str:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    if context:
        # Exactly the shape `kernel/scheduler.py` builds: the assistant's own
        # tool call, then the result as a USER message through the real
        # formatter. Anything else measures a conversation the model will
        # never actually be in.
        tool, summary = context
        messages.append({"role": "assistant",
                         "content": f'<tool name="{tool}">{{}}</tool>'})
        messages.append({"role": "user", "content": runtime.format_result(
            {"tool": tool, "status": "success", "summary": summary})})
    payload = json.dumps({
        "model": model, "messages": messages, "stream": False,
        "options": {"temperature": 0.0},
    }).encode()
    request = urllib.request.Request(
        OLLAMA, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())["message"]["content"]


def validate(call: dict) -> "str | None":
    """Run the arguments past the real registry. None means they are fine."""
    spec = get(call["name"])
    if spec is None:
        return f"no such tool {call['name']!r}"
    missing = [name for name, meta in (spec.parameters or {}).items()
               if meta.get("required") and name not in call["arguments"]]
    if missing:
        return "missing required: " + ", ".join(missing)
    unknown = [k for k in call["arguments"] if k not in (spec.parameters or {})]
    if unknown:
        return "invented arguments: " + ", ".join(unknown)
    return None


DESKTOP = {
    "list_windows", "control_window", "read_window", "read_page",
    "click_element", "type_into", "click_at", "scroll_window", "press_keys",
    "wait_for", "run_steps", "undo_last", "record_workflow",
    "replay_workflow", "end_control",
}


def only_desktop():
    """Temporarily hide every non-desktop tool from the prompt.

    The cheap version of the experiment. If tool choice improves when
    `run_python` and friends are not competing, the problem is surface size
    and the Phase 2 shrink is justified. If it does not, the problem is the
    descriptions, and collapsing fifteen tools into five would be a large
    refactor aimed at the wrong thing.
    """
    from primnox2.tools import registry

    hidden = {name: spec for name, spec in registry._REGISTRY.items()
              if name not in DESKTOP}
    for name in hidden:
        del registry._REGISTRY[name]
    return hidden


def restore(hidden: dict):
    from primnox2.tools import registry
    registry._REGISTRY.update(hidden)


def prompt_for(context, narrow: bool) -> str:
    """The system prompt this task would really be given.

    Focus is derived in production from whether a control session is live, so
    the harness reproduces that rather than using one prompt throughout —
    tasks 2 onwards all have a session open, and measuring them against the
    unfocused prompt would measure a turn that never happens.
    """
    if not narrow or context is None:
        return runtime.system_prompt()
    original = runtime._focus
    runtime._focus = lambda _cid: "desktop"
    try:
        return runtime.system_prompt(conversation_id="bench")
    finally:
        runtime._focus = original


def run(model: str, runs: int, label: str, narrow: bool = False) -> dict:
    shown = prompt_for(TASKS[1][1], narrow)
    print(f"\n{label}  —  {len(tool_names())} tools registered, "
          f"{len(shown)} char prompt (~{len(shown) // 4} tokens) once focused")
    print(f"  {'task':46s} {'called':>7s} {'right':>6s} {'args':>6s}   note")

    totals = {"called": 0, "right": 0, "args": 0, "n": 0}
    for user, context, accepted in TASKS:
        for _ in range(runs):
            totals["n"] += 1
            system = prompt_for(context, narrow)
            try:
                reply = ask(model, system, user, context)
            except Exception as exc:
                print(f"  {user[:46]:46s} {'ERR':>7s}          {exc}")
                continue
            call = runtime.parse_call(reply)
            note = ""
            if call is None:
                note = "no tool call: " + reply.strip().replace("\n", " ")[:52]
            else:
                totals["called"] += 1
                if call["name"] in accepted:
                    totals["right"] += 1
                    problem = validate(call)
                    if problem is None:
                        totals["args"] += 1
                    else:
                        note = problem
                else:
                    note = f"called {call['name']}"
            print(f"  {user[:46]:46s} "
                  f"{'yes' if call else 'no':>7s} "
                  f"{'yes' if call and call['name'] in accepted else 'no':>6s} "
                  f"{'yes' if not note and call else 'no':>6s}   {note}")
    return totals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:0.5b")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--label", default="current surface")
    parser.add_argument("--only-desktop", action="store_true")
    parser.add_argument("--focused", action="store_true",
                        help="narrow the catalogue when a session is live, "
                             "as production does")
    args = parser.parse_args()

    hidden = only_desktop() if args.only_desktop else {}
    started = time.time()
    try:
        totals = run(args.model, args.runs, args.label, narrow=args.focused)
    finally:
        restore(hidden)
    n = totals["n"] or 1
    print(f"\n  {args.model}: called {totals['called']}/{n}, "
          f"right tool {totals['right']}/{n}, "
          f"valid arguments {totals['args']}/{n}  "
          f"({time.time() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
