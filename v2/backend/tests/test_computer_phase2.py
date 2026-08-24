"""Computer Use, second pass: several windows, undo, replay, blind windows.

The first pass could drive one window. These are the capabilities that turn
that into something usable for real work, and each one has a failure mode that
matters more than the feature:

  Several sessions at once — the failure is acting on the wrong window, so
  ambiguity must be refused rather than resolved by guessing.

  Undo — the failure is claiming reversibility that does not exist, so a
  button press must be reported as un-undoable rather than approximated.

  Replay — the failure is a macro replayed into a window that has moved on,
  so steps resolve by selector against a fresh read and stop when one is
  missing rather than continuing against a state nothing established.

  Blind windows — the failure is a model reading an empty element list as an
  empty window, so a window with no accessibility provider must say what it
  is and name the route that still works.

Same purpose-built target as `test_computer_use.py`; see that file's docstring
for why it is not a real application.
"""
from __future__ import annotations

import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Computer Use is Windows-only")

from primnox2.computer import grants, session as sessions, targets, tree, workflows
from test_computer_use import WINDOW_CLASS, _SCRIPT       # noqa: E402


CONVERSATION = "conv_phase2_tests"


def _spawn(label: str):
    """A second and third window, so the multi-session paths have subjects."""
    import win32gui
    import win32process

    title = f"Primnox {label} {time.time_ns()}"
    process = subprocess.Popen([sys.executable, str(_SCRIPT), title])
    for _ in range(60):
        time.sleep(0.25)
        hwnd = win32gui.FindWindow(WINDOW_CLASS, title)
        if hwnd:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            target = targets.resolve(f"win_{hwnd}_{pid}")
            for _ in range(20):
                if tree.find_text_target(tree.read(target)) is not None:
                    return process, target
                time.sleep(0.25)
            break
    process.terminate()
    pytest.skip(f"the {label} window did not become usable")


@pytest.fixture
def two_windows():
    processes, made = [], []
    try:
        for label in ("Alpha", "Beta"):
            process, target = _spawn(label)
            processes.append(process)
            made.append(target)
        yield made
    finally:
        sessions.close_all("test finished", conversation_id=CONVERSATION)
        for process in processes:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def _open(target, scope=grants.ACT):
    return sessions.open_session(target, scope, conversation_id=CONVERSATION,
                                 turn_id=None)


def _value(session) -> str:
    field = tree.find_text_target(session.read_tree())
    return field.value if field else ""


# ── Several windows at once ──────────────────────────────────────────────────

def test_two_windows_are_controlled_independently(two_windows):
    alpha, beta = two_windows
    a, b = _open(alpha), _open(beta)

    assert len(sessions.live(CONVERSATION)) == 2, "a session replaced the other"

    from primnox2.computer import actions
    actions.set_value(tree.find_text_target(a.read_tree()), "into alpha")
    actions.set_value(tree.find_text_target(b.read_tree()), "into beta")

    assert _value(a) == "into alpha"
    assert _value(b) == "into beta", "the two sessions are not independent"


def test_ambiguity_is_refused_rather_than_guessed(two_windows):
    """The whole reason `window` is optional-but-sometimes-required.

    Resolving to the most recent session would work almost always and, on the
    occasion it did not, would click a button in an application nobody was
    talking about.
    """
    alpha, beta = two_windows
    _open(alpha)
    _open(beta)

    with pytest.raises(sessions.Ambiguous) as caught:
        sessions.current(CONVERSATION)
    message = str(caught.value)
    assert alpha.handle in message and beta.handle in message, (
        "the refusal must name the candidates, or the model cannot fix it")


def test_one_window_needs_no_disambiguation(two_windows):
    """With a single session the handle is noise, so it stays optional."""
    alpha, _ = two_windows
    opened = _open(alpha)
    assert sessions.current(CONVERSATION) is opened


def test_reopening_the_same_window_replaces_its_session(two_windows):
    """One story per window. Two live grants on one window would put two
    timelines over the same events."""
    alpha, _ = two_windows
    first = _open(alpha)
    second = _open(alpha)
    assert first.closed
    assert len(sessions.live(CONVERSATION)) == 1
    assert sessions.current(CONVERSATION) is second


def test_sessions_are_capped(two_windows):
    """Past a handful of windows nobody can follow the timeline, and the
    timeline is the whole compensating control for asking permission once."""
    alpha, beta = two_windows
    for _ in range(sessions.MAX_SESSIONS + 2):
        _open(alpha)
        _open(beta)
    assert len(sessions.live(CONVERSATION)) <= sessions.MAX_SESSIONS


# ── Undo ─────────────────────────────────────────────────────────────────────

def test_undo_restores_the_previous_text(two_windows):
    from primnox2.computer import actions
    alpha, _ = two_windows
    session = _open(alpha)

    field = tree.find_text_target(session.read_tree())
    actions.set_value(field, "the good text")
    time.sleep(0.2)

    # Through the session, so the reversal is journalled the way the tool does.
    field = tree.find_text_target(session.read_tree())
    previous = field.value
    session.act("type", "type",
                lambda: actions.set_value(field, "the bad text"),
                reversal=sessions.Reversal(
                    "setting the field",
                    lambda: actions.set_value(field, previous)))
    assert _value(session) == "the bad text"

    session.undo()
    assert _value(session) == "the good text"


def test_undo_refuses_when_nothing_is_reversible(two_windows):
    """A click has no inverse. Saying so is the feature — a model told undo
    is available will take risks on that basis."""
    alpha, _ = two_windows
    session = _open(alpha)
    session.read_tree()

    with pytest.raises(LookupError) as caught:
        session.undo()
    message = str(caught.value)
    assert "can be undone by Primnox" in message
    # The distinction the message exists to draw: Primnox cannot reverse it,
    # and the application's own undo is a different thing rather than a
    # substitute. Losing either half would make this a dead end.
    assert "ctrl+z" in message.lower()
    assert "different thing" in message


# ── Record and replay ────────────────────────────────────────────────────────

def test_a_selector_survives_a_reread(two_windows):
    """Refs do not survive a re-read; selectors are the reason replay works."""
    alpha, _ = two_windows
    session = _open(alpha)

    first = session.read_tree()
    button = next(e for e in first.elements if "invoke" in e.patterns)
    selector = tree.selector_for(first, button)

    second = session.read_tree()
    found = tree.resolve_selector(second, selector)
    assert found is not None, "the selector did not survive a re-read"
    assert found.name == button.name and found.role == button.role


def test_a_recording_replays_into_a_different_window(two_windows):
    """The point of selectors rather than refs or coordinates: a workflow
    recorded against one window runs against another of the same shape."""
    from primnox2.computer import actions
    alpha, beta = two_windows
    source = _open(alpha)

    source.start_recording()
    snapshot = source.read_tree()
    field = tree.find_text_target(snapshot)
    source.act("type", "type", lambda: actions.set_value(field, "replayed text"),
               step=workflows.step_for("type", tree.selector_for(snapshot, field),
                                       {"text": "replayed text"}))
    steps = source.stop_recording()
    assert steps, "nothing was recorded"

    doc = workflows.document("demo", alpha.handle, alpha.label(), steps)
    parsed = workflows.parse(workflows.to_bytes(doc))

    destination = _open(beta)
    target_snapshot = destination.read_tree()
    element = tree.resolve_selector(target_snapshot, parsed["steps"][0]["selector"])
    assert element is not None, "the recorded step did not resolve in the other window"
    actions.set_value(element, parsed["steps"][0]["arguments"]["text"])
    time.sleep(0.2)
    assert _value(destination) == "replayed text"


def test_a_workflow_from_another_build_is_refused():
    """A recording is a stored document, so it outlives the code that wrote
    it. Reading one with an unknown shape and replaying whatever it seems to
    say would run guesses against the user's applications."""
    doc = workflows.document("x", "win_1_1", "somewhere", [])
    doc["schema"] = 99
    with pytest.raises(ValueError) as caught:
        workflows.parse(workflows.to_bytes(doc))
    assert "different version" in str(caught.value)


def test_rubbish_is_not_mistaken_for_a_workflow():
    with pytest.raises(ValueError):
        workflows.parse(b"not json at all")
    with pytest.raises(ValueError):
        workflows.parse(b'{"something": "else"}')


# ── Windows with no accessibility tree ───────────────────────────────────────

def test_a_window_with_controls_is_not_reported_blind(two_windows):
    alpha, _ = two_windows
    assert not tree.read(alpha).blind


def test_blind_is_about_actionability_not_emptiness():
    """`blind` has to mean "cannot be operated by element", not "has no
    nodes". A window full of decorative labels reports plenty of elements and
    is exactly as unusable as an empty one."""
    decorative = tree.Snapshot(
        handle="win_1_1", title="t",
        elements=[tree.Element(ref="e1", role="Text", name="hello", value="",
                               patterns=[], bounds=(0, 0, 1, 1), enabled=True,
                               depth=0, hwnd=0)])
    assert decorative.blind

    usable = tree.Snapshot(
        handle="win_1_1", title="t",
        elements=[tree.Element(ref="e1", role="Button", name="Go", value="",
                               patterns=["invoke"], bounds=(0, 0, 1, 1),
                               enabled=True, depth=0, hwnd=0)])
    assert not usable.blind


# ── Browsers ─────────────────────────────────────────────────────────────────

def test_browsers_are_recognised_and_read_deeper():
    """A browser's tree is the live DOM, so the native limits truncate the
    page before reaching its content — which reads to a model as an empty
    page rather than a truncated one."""
    assert tree.BROWSER_MAX_DEPTH > tree.MAX_DEPTH
    assert tree.BROWSER_MAX_ELEMENTS > tree.MAX_ELEMENTS

    browsers = [t for t in targets.enumerate_windows() if t.is_browser]
    for browser in browsers:
        assert browser.process.lower() in targets.BROWSER_PROCESSES \
            or browser.window_class in targets.BROWSER_CLASSES


def test_electron_apps_are_not_mistaken_for_browsers(two_windows):
    """`Chrome_WidgetWin_1` is every Chromium build AND every Electron app, so
    the class alone cannot decide this — the process list is what separates a
    browser from a desktop application that happens to be built on one."""
    alpha, _ = two_windows
    assert not alpha.is_browser
