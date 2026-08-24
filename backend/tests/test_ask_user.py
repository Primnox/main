"""Primnox asking, instead of guessing.

The alternative to asking is a guess, and a guess from a small model does not
arrive labelled as one — it arrives as a confident sentence that nothing
downstream can tell apart from an instruction the user gave. This turns the most
expensive class of hallucination, an invented premise the rest of the answer is
built on, into one click.
"""
from __future__ import annotations

import threading
import time

import pytest

from primnox2.tools import builtins
from primnox2.tools.permissions import (ANSWER_TIMEOUT, ANSWER_UNCLEAR, broker)
from primnox2.tools.registry import ToolContext, get, tool_names


def _ctx() -> ToolContext:
    return ToolContext(conversation_id=None, turn_id=None)


def _answer_when_asked(pick, timeout=5.0) -> threading.Thread:
    """Answer the first question that appears, the way the UI would."""
    def run():
        deadline = time.time() + timeout
        while time.time() < deadline:
            ids = broker.pending_ids()
            if ids:
                rid = ids[0]
                choice = pick(broker._pending[rid].options)
                broker.resolve(rid, choice)
                return
            time.sleep(0.02)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


# ── the tool exists and is described ─────────────────────────────────────────

def test_the_tool_is_registered():
    assert "ask_user" in tool_names()


def test_it_tells_the_model_to_prefer_asking_over_guessing():
    """The description is the only thing steering when it gets used."""
    d = get("ask_user").description.lower()
    assert "guess" in d, "nothing tells the model why to prefer this"


# ── the shape of a question ──────────────────────────────────────────────────

def test_a_question_needs_real_alternatives():
    """A model that cannot name the options does not yet know what it is
    asking, and an open 'what would you like?' just moves the work back."""
    r = builtins._ask_user({"question": "What should I do?", "options": []}, _ctx())
    assert r["status"] == "error"
    assert "2-4" in r["output"]


def test_an_empty_question_is_refused():
    r = builtins._ask_user({"question": "  ", "options": ["a", "b"]}, _ctx())
    assert r["status"] == "error"


def test_a_comma_string_of_options_is_accepted():
    """Small models send `"a, b"` where the schema says array. Refusing on a
    formatting detail wastes a step for a call that was understood."""
    _answer_when_asked(lambda opts: opts[0]["id"])
    r = builtins._ask_user({"question": "Which?", "options": "Postgres, SQLite"}, _ctx())
    assert r["status"] == "success"
    assert "Postgres" in r["output"]


# ── answering ────────────────────────────────────────────────────────────────

def test_the_chosen_option_comes_back_by_label():
    _answer_when_asked(lambda opts: opts[1]["id"])
    r = builtins._ask_user(
        {"question": "Which database?", "options": ["Postgres", "SQLite"]}, _ctx())
    assert r["status"] == "success"
    assert "SQLite" in r["output"]


def test_none_of_these_is_always_offered():
    """A question with no way to reject the framing forces a wrong answer into
    the record."""
    captured = {}

    def pick(opts):
        captured["ids"] = [o["id"] for o in opts]
        return ANSWER_UNCLEAR

    _answer_when_asked(pick)
    r = builtins._ask_user({"question": "Which?", "options": ["a", "b"]}, _ctx())
    assert ANSWER_UNCLEAR in captured["ids"]
    assert "do not pick one anyway" in r["output"].lower()


def test_an_unoffered_answer_is_not_taken_as_a_choice():
    """Resolving with a value nobody offered would put words in the user's
    mouth — the exact thing this feature exists to prevent."""
    _answer_when_asked(lambda opts: "opt_does_not_exist")
    r = builtins._ask_user({"question": "Which?", "options": ["a", "b"]}, _ctx())
    assert "a" not in r["output"].split(":")[-1].strip()[:3] or "reject" in r["output"].lower()
    assert r["status"] == "success"


def test_silence_is_reported_as_silence_not_as_a_default():
    """Nobody answered is not the same as 'they chose the first one'. The model
    must proceed on its own judgement AND say that it did."""
    import primnox2.tools.permissions as perms
    original = perms.DEFAULT_TIMEOUT_S
    perms.DEFAULT_TIMEOUT_S = 1
    try:
        r = builtins._ask_user({"question": "Which?", "options": ["a", "b"]}, _ctx())
    finally:
        perms.DEFAULT_TIMEOUT_S = original
    assert r["summary"] == "no answer"
    assert "best judgement" in r["output"].lower()
    assert "a" != r["output"].strip()


# ── the property that matters most ───────────────────────────────────────────

def test_auto_approve_never_answers_a_question(monkeypatch):
    """PRIMNOX2_AUTO_APPROVE=all is a fine default for permissions — the user
    chose not to be interrupted about tools they trust. Applying it here would
    answer, on their behalf, a question asked *because the model did not know*,
    and present the invention as confirmed. Worse than the unaided guess.
    """
    import primnox2.tools.permissions as perms
    monkeypatch.setattr(perms, "AUTO_APPROVE", "all", raising=False)
    monkeypatch.setattr(perms, "DEFAULT_TIMEOUT_S", 1, raising=False)

    r = builtins._ask_user({"question": "Delete which?", "options": ["a", "b"]}, _ctx())
    assert r["summary"] == "no answer", (
        "auto-approve answered a question on the user's behalf: "
        f"{r['output']!r}")
