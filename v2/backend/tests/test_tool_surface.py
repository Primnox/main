"""What a small model is actually shown, and why it matters.

The goal these defend is the one that was asked for in plain words: a 0.5B
model should be able to do basic desktop things. Measured on qwen2.5:0.5b
across ten desktop tasks, replaying the real message shapes through the real
parser and the real registry:

    baseline                          right tool  1/10
    + success-path continuation                   4/10
    + ownership line                              5/10
    + capability retrieval                        7/10
    (ceiling: desktop tools only)                 8/10

Each step was measured before it was kept, and one of them — the ownership
line — barely moved the number and is kept only because it is true and cheap.
The harness is `scripts/bench_tool_surface.py`.

The two findings worth protecting with tests are both about asymmetries that
nobody had noticed:

  `format_result` told the model how to continue only when something FAILED.
  On success it said nothing, and a 0.5B pattern-matched the previous message
  — a success report — and wrote another success report. Nine of ten replies
  were fabricated outcomes: "I have successfully controlled the Notepad
  window". None of it had happened.

  A general-purpose tool is where a small model goes when it is unsure.
  `run_python` was winning desktop tasks it cannot possibly perform, and no
  amount of description fixed it, because the model was not reading that far.
"""
from __future__ import annotations

import pytest

from primnox2.tools import registry, runtime


# ── The success path has to say what happens next ───────────────────────────

def test_a_successful_result_says_a_turn_can_continue():
    """The asymmetry this closes: the model was told how to carry on only
    when something went wrong."""
    text = runtime.format_result(
        {"tool": "control_window", "status": "success",
         "summary": "Session open on Untitled - Notepad"})
    assert "<tool" in text
    assert "next" in text.lower()


def test_a_successful_result_forbids_inventing_the_outcome():
    """The measured failure, in the model's own words: "I have successfully
    controlled the Notepad window", when nothing had been controlled."""
    text = runtime.format_result(
        {"tool": "control_window", "status": "success", "summary": "ok"})
    assert "Do not write a result you were not given" in text


def test_a_failing_result_still_explains_how_to_retry():
    """The older half of the same idea, which must not regress."""
    text = runtime.format_result(
        {"tool": "run_python", "status": "error", "summary": "boom"})
    assert "To retry" in text
    assert "code fence" in text


def test_success_and_failure_say_different_things():
    """If they converged, one of the two situations would be getting advice
    written for the other."""
    ok = runtime.format_result({"tool": "t", "status": "success", "summary": "s"})
    bad = runtime.format_result({"tool": "t", "status": "error", "summary": "s"})
    assert ok != bad
    assert "To retry" not in ok


# ── Capability retrieval ────────────────────────────────────────────────────

def test_focusing_on_the_desktop_hides_the_general_purpose_tools():
    """`run_python` was winning tasks it cannot perform — it cannot see or
    touch another application's window."""
    focused = registry.describe_for_prompt(focus="desktop")
    assert "read_window" in focused
    assert "run_python" not in focused


def test_no_focus_shows_everything():
    """The turn where the model is deciding which family of work it is in
    needs to see both families."""
    everything = registry.describe_for_prompt()
    assert "run_python" in everything
    assert "list_windows" in everything


def test_narrowing_advertises_less_without_removing_anything():
    """The property that makes this safe: the registry executes whatever is
    registered, and the catalogue only advertises. A tool left out of the
    description is still callable."""
    registry.describe_for_prompt(focus="desktop")
    assert registry.get("run_python") is not None
    assert "run_python" in registry.tool_names()


def test_an_unknown_focus_narrows_nothing():
    """A typo in a focus name must not silently empty the catalogue."""
    assert registry.describe_for_prompt(focus="nonsense") == \
        registry.describe_for_prompt()


def test_focus_never_leaves_the_model_with_no_tools():
    """On a build without the desktop tools registered, narrowing to them
    would advertise an empty list."""
    hidden = {name: spec for name, spec in registry._REGISTRY.items()
              if name in registry.DESKTOP_TOOLS}
    for name in hidden:
        del registry._REGISTRY[name]
    try:
        assert registry.describe_for_prompt(focus="desktop").strip()
    finally:
        registry._REGISTRY.update(hidden)


def test_the_focused_prompt_is_materially_smaller():
    """The saving is per desktop turn, and tool descriptions are re-sent on
    every iteration of the tool loop."""
    if not runtime.COMPUTER_USE:
        pytest.skip("Computer Use is not available on this platform")
    wide = len(registry.describe_for_prompt())
    narrow = len(registry.describe_for_prompt(focus="desktop"))
    assert narrow < wide * 0.8, f"{narrow} against {wide} is not a saving"


# ── When focus is chosen ────────────────────────────────────────────────────

def test_focus_follows_a_live_control_session(monkeypatch):
    """The one unambiguous signal available: the user has approved driving a
    specific window, so the work in front of the model is that window."""
    if not runtime.COMPUTER_USE:
        pytest.skip("Computer Use is not available on this platform")
    from primnox2.computer import session as sessions

    monkeypatch.setattr(sessions, "live", lambda cid: ["a session"])
    assert runtime._focus("conv") == "desktop"


def test_nothing_is_narrowed_without_a_session(monkeypatch):
    """The turn that OPENS a session is exactly the turn that needs to see
    every tool — the model is still deciding what kind of work this is."""
    if not runtime.COMPUTER_USE:
        pytest.skip("Computer Use is not available on this platform")
    from primnox2.computer import session as sessions

    monkeypatch.setattr(sessions, "live", lambda cid: [])
    assert runtime._focus("conv") is None


def test_no_conversation_means_no_narrowing():
    assert runtime._focus(None) is None


def test_a_broken_session_lookup_does_not_break_the_prompt(monkeypatch):
    """Losing the focus hint costs a bigger prompt. Losing the prompt costs
    the turn."""
    if not runtime.COMPUTER_USE:
        pytest.skip("Computer Use is not available on this platform")
    from primnox2.computer import session as sessions

    def explode(cid):
        raise RuntimeError("session store unavailable")

    monkeypatch.setattr(sessions, "live", explode)
    assert runtime._focus("conv") is None
    assert runtime.system_prompt(conversation_id="conv")


# ── The desktop guidance ────────────────────────────────────────────────────

def test_the_desktop_family_is_named_as_owning_screen_work():
    if not runtime.COMPUTER_USE:
        pytest.skip("Computer Use is not available on this platform")
    prompt = runtime.system_prompt()
    assert "never with run_python" in prompt


def test_the_three_call_sequence_survives():
    """The measured shape a 0.5B imitates. Everything added since has gone
    after it rather than into it, for that reason."""
    if not runtime.COMPUTER_USE:
        pytest.skip("Computer Use is not available on this platform")
    prompt = runtime.system_prompt()
    # Only within the taught block. Searching the whole prompt finds the
    # alphabetical tool catalogue first, where control_window precedes
    # list_windows — which says nothing about what is being taught.
    start = prompt.find("Using the desktop takes three calls")
    assert start > 0, "the taught sequence is gone"
    taught = prompt[start:]
    order = [taught.find(t) for t in
             ("list_windows", "control_window", "type_into", "run_steps")]
    assert all(i > 0 for i in order), order
    assert order == sorted(order), "the taught sequence is out of order"
