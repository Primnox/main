"""Golden Conversation Suite.

Canonical conversations, replayed against a scripted model so the only variable
is the runtime itself. Each one produces a behavioural signature; when the
runtime changes, an unexpected change to that signature fails the build.

The signature deliberately excludes anything timing-dependent. Token events are
batched every 100ms or 5 tokens, so their *count* is not reproducible — the
concatenated text is, and that is what actually matters. Comparing the raw
event count would produce a suite that fails randomly and gets ignored, which
is worse than having none.

Regenerate deliberately, never reflexively:

    PRIMNOX2_UPDATE_GOLDEN=1 pytest tests/test_golden.py
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from conftest import run_turn, wait_for_turn

from primnox2.assets import service as assets
from primnox2.chat import turns
from primnox2.sandbox import manager as sandbox
from primnox2.workspaces import service as workspaces

GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_DIR.mkdir(exist_ok=True)
UPDATING = os.getenv("PRIMNOX2_UPDATE_GOLDEN") == "1"


def collapse(kinds: list[str]) -> list[str]:
    """Collapse runs of the same kind. `token token token` → `token*`."""
    out: list[str] = []
    for k in kinds:
        marker = f"{k}*" if k == "token" else k
        if out and out[-1] == marker:
            continue
        out.append(marker)
    return out


def signature(turn_id: str, conversation_id: str, events) -> dict:
    history = [t for t in turns.get_history(conversation_id) if t["turn_id"] == turn_id]
    assistant = history[0]["assistant_message"] if history else None
    return {
        "event_flow": collapse(events.kinds(turn_id)),
        "statuses": events.statuses(turn_id),
        "final_text": (assistant or {}).get("text", ""),
        "streamed_text": events.text(turn_id).strip(),
        "workspaces": len(workspaces.for_turn(turn_id)),
        "executions": len(sandbox.for_turn(turn_id)),
        "assets": len(assets.for_turn(turn_id)),
    }


def compare(name: str, actual: dict) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    if UPDATING or not path.is_file():
        path.write_text(json.dumps(actual, indent=2), encoding="utf-8")
        if not UPDATING:
            pytest.skip(f"recorded new golden file {path.name} — re-run to verify")
        return

    expected = json.loads(path.read_text(encoding="utf-8"))
    if expected != actual:
        diff = []
        for key in sorted(set(expected) | set(actual)):
            if expected.get(key) != actual.get(key):
                diff.append(f"  {key}:\n    expected {expected.get(key)!r}\n    actual   {actual.get(key)!r}")
        raise AssertionError(
            f"golden conversation {name!r} changed behaviour:\n" + "\n".join(diff)
            + "\n\nIf this change is intended, re-record with PRIMNOX2_UPDATE_GOLDEN=1."
        )


# ── The conversations ────────────────────────────────────────────────────────
class TestGoldenCoding:
    """"Write Fibonacci." — the canonical code-generation conversation."""

    FIB = ('def fib(n):\n'
           '    a, b = 0, 1\n'
           '    for _ in range(n):\n'
           '        a, b = b, a + b\n'
           '    return a\n')

    def test_write_fibonacci(self, conversation, events, scripted, sandbox_ready):
        scripted(
            '<tool name="create_workspace">\n'
            + json.dumps({"kind": "python", "title": "Fibonacci",
                          "files": {"fib.py": self.FIB}})
            + '\n</tool>',
            "I wrote `fib.py` with an iterative Fibonacci function.",
        )
        tid = run_turn(conversation, "Write Fibonacci.")
        assert wait_for_turn(tid, timeout=180) == "completed"

        created = workspaces.for_turn(tid)
        assert len(created) == 1, "a coding conversation produced no workspace"

        source = workspaces.get(created[0]["id"])["files"]["fib.py"]
        # The code must actually be valid Python, not merely present.
        compile(source, "fib.py", "exec")
        namespace: dict = {}
        exec(source, namespace)
        assert [namespace["fib"](i) for i in range(8)] == [0, 1, 1, 2, 3, 5, 8, 13]

        compare("coding_fibonacci", signature(tid, conversation, events))

    def test_streaming_order_preserved(self, conversation, events, scripted):
        scripted("First. Second. Third. Fourth. Fifth.", chunk=3)
        tid = run_turn(conversation, "Count in order.")
        assert wait_for_turn(tid) == "completed"

        streamed = events.text(tid).strip()
        stored = [t for t in turns.get_history(conversation)
                  if t["turn_id"] == tid][0]["assistant_message"]["text"]
        assert streamed == stored, "what was streamed differs from what was stored"
        assert streamed == "First. Second. Third. Fourth. Fifth."


class TestGoldenExplanation:
    """"Explain recursion." — the canonical prose conversation."""

    ANSWER = (
        "Recursion is when a function calls itself on a smaller version of the "
        "same problem.\n\n"
        "Every recursive function needs a base case — a version of the problem "
        "small enough to answer outright — otherwise it never stops.\n\n"
        "The classic example is factorial: `n! = n * (n-1)!`, with `0! = 1` as "
        "the base case."
    )

    def test_explain_recursion(self, conversation, events, scripted):
        scripted(self.ANSWER, chunk=11)
        tid = run_turn(conversation, "Explain recursion.")
        assert wait_for_turn(tid) == "completed"

        text = [t for t in turns.get_history(conversation)
                if t["turn_id"] == tid][0]["assistant_message"]["text"]

        # No duplicated paragraphs — the V1 defect this suite exists to catch.
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        assert len(paragraphs) == len(set(paragraphs)), "a paragraph was duplicated"

        # Markdown survived chunking: backticks are balanced.
        assert text.count("`") % 2 == 0, "chunking split a code span"
        assert text == self.ANSWER, "the reassembled text differs from what was sent"

        compare("explanation_recursion", signature(tid, conversation, events))

    def test_no_duplication_under_small_chunks(self, conversation, events, scripted):
        """One character at a time — the worst case for the stream filter."""
        scripted(self.ANSWER, chunk=1)
        tid = run_turn(conversation, "Explain recursion again.")
        assert wait_for_turn(tid) == "completed"
        assert events.text(tid).strip() == self.ANSWER


class TestGoldenToolUse:
    """A conversation that plans, runs code, and reports back."""

    def test_plan_execute_report(self, conversation, events, scripted, sandbox_ready):
        scripted(
            '<plan>\nCompute the total with Python.\n</plan>\n'
            '<tool name="run_python">\n{"code": "print(sum(range(101)))"}\n</tool>',
            "The sum of 1 through 100 is 5050.",
        )
        tid = run_turn(conversation, "What is the sum of 1..100?")
        assert wait_for_turn(tid, timeout=180) == "completed"

        assert [e["payload"]["plan"] for e in events.of_kind("plan.proposed", tid)] == \
            ["Compute the total with Python."]

        streamed = events.text(tid)
        assert "<tool" not in streamed and "<plan" not in streamed, \
            "protocol markup leaked into the user-visible stream"

        compare("tool_plan_execute", signature(tid, conversation, events))
