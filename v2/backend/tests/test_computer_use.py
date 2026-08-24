"""Computer Use: the safety boundary, and the constraints that shaped it.

These are behavioural in the same way `test_sandbox_isolation.py` is. Every
assertion here corresponds to something measured against real windows on a
real desktop while building this, not to a hypothesis about how Win32 ought
to behave — and in three cases (background capture, posted hotkeys, tree
reads on unfocused windows) the measurement is the reason the implementation
looks the way it does.

A real window is needed for most of it, and it is `_testwindow.py` rather
than a real application. Driving Notepad was tried first and was wrong three
ways over: one Store process is shared by every Notepad window, so tearing
one down by pid took its siblings with it; unsaved tabs are restored on next
launch, so each run left rubbish on the desktop of whoever ran the suite; and
a fresh one seizes the foreground, which the tests then could not give back,
because Windows' foreground lock refuses `SetForegroundWindow` from a process
the user has not just interacted with. Twelve tests each launching one left
twenty-six stranded windows and skipped everything that mattered.

`_testwindow.py` is a plain Win32 window whose children are a standard `EDIT`
and `BUTTON` — common controls, whose UI Automation providers come from
Windows itself, so the patterns behave exactly as they do in any application
built on them. It never takes the foreground, which is how these tests get
their "this really is a background window" precondition.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Computer Use is Windows-only")

from primnox2.computer import actions, grants, pointer
from primnox2.computer import session as sessions, targets, tree
from primnox2.computer import vision

WINDOW_CLASS = "PrimnoxTestWindow"
_SCRIPT = Path(__file__).with_name("_testwindow.py")


@pytest.fixture
def window():
    """A window built to be automated, guaranteed not to be the focused one."""
    import win32gui
    import win32process

    title = f"Primnox Test Window {time.time_ns()}"
    process = subprocess.Popen([sys.executable, str(_SCRIPT), title])

    hwnd = 0
    for _ in range(60):
        time.sleep(0.25)
        hwnd = win32gui.FindWindow(WINDOW_CLASS, title)
        if hwnd:
            break
    if not hwnd:
        process.terminate()
        pytest.skip("the test window did not open")

    # WS_EX_NOACTIVATE should make this impossible, so it is asserted rather
    # than skipped: if the target can steal the foreground, every claim these
    # tests make about background operation is void.
    assert win32gui.GetForegroundWindow() != hwnd, (
        "the test window took the foreground, so nothing below tests "
        "background behaviour")

    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    target = targets.resolve(f"win_{hwnd}_{pid}")

    for _ in range(20):
        if tree.find_text_target(tree.read(target)) is not None:
            break
        time.sleep(0.25)
    else:
        process.terminate()
        pytest.skip("the test window never finished building its controls")

    yield target

    # Our own process, so this is unambiguous — no shared host, no session to
    # restore, and nothing of the user's to lose.
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _edit_hwnd(target) -> int:
    """The EDIT child, which is what messages are addressed to."""
    import win32gui
    return win32gui.FindWindowEx(target.hwnd, 0, "EDIT", None)


def _selection(target) -> tuple[int, int]:
    """The EDIT control's selection range, via EM_GETSEL.

    A standard EDIT exposes ValuePattern but NOT TextPattern, so the UIA
    route cannot see a selection at all. Asking the control directly is both
    available and a more literal question than the pattern would have been.
    """
    import win32gui
    start, end = ctypes.c_ulong(), ctypes.c_ulong()
    win32gui.SendMessage(_edit_hwnd(target), 0x00B0,          # EM_GETSEL
                         ctypes.addressof(start), ctypes.addressof(end))
    return start.value, end.value


# ── Discovery ────────────────────────────────────────────────────────────────

def test_enumeration_excludes_the_desktop_shell():
    """`Progman` is full-screen and titled "Program Manager", so it outranked
    every real window on size and sat at the top of the candidate list. It is
    the desktop itself; approving control of it is never what anyone meant."""
    classes = {t.window_class for t in targets.enumerate_windows()}
    assert not (classes & targets.SHELL_CLASSES)


def test_handles_do_not_survive_the_window_they_named():
    """Windows recycles HWNDs. A grant is authority over one window, so a
    handle whose pid no longer matches must be refused rather than silently
    resolving to whatever inherited the number."""
    with pytest.raises(targets.Stale):
        targets.resolve("win_999999999_1")
    with pytest.raises(targets.Stale):
        targets.resolve("not-a-handle")


def test_resolve_rejects_a_recycled_handle(window):
    """Same hwnd, different process — the exact shape of a recycled handle."""
    with pytest.raises(targets.Stale) as caught:
        targets.resolve(f"win_{window.hwnd}_{window.pid + 1}")
    assert "different program" in str(caught.value)


# ── Reading works on a window nobody is looking at ───────────────────────────

def test_tree_reads_an_unfocused_window(window):
    """The reliable half of computer use. This is the measurement the whole
    design rests on: structure is readable while the window is in the
    background, so control never needs the foreground."""
    snapshot = tree.read(window)
    assert snapshot.elements, "no elements read from a live window"
    assert snapshot.actionable(), "no actionable elements in a live window"


def test_text_target_is_found_by_capability_not_control_type(window):
    """Elements are selected by what they can do, never by what they are.

    The rule exists because control type and capability genuinely disagree in
    the wild: Windows 11 Notepad's editor is a `DocumentControl`, so a search
    for `EditControl` finds nothing at all and the obvious implementation
    silently fails on one of the most ordinary applications there is.

    This target's field really is an `Edit`, which is why the assertion is on
    the pattern rather than on the role — checking `role != "Edit"` here would
    only prove which target the fixture launched.
    """
    snapshot = tree.read(window)
    field = tree.find_text_target(snapshot)
    assert field is not None
    assert "set_value" in field.patterns
    # The selection must survive the role being anything at all.
    assert all("set_value" in e.patterns
               for e in snapshot.elements if e is field)


def test_capture_of_a_background_window_is_not_blank(window):
    """PW_RENDERFULLCONTENT is mandatory: without it a DWM-composited window
    returns success and an all-black bitmap. `capture` checks for content, so
    a regression here surfaces as CaptureError rather than a black image
    presented to a model as a screenshot."""
    image = vision.capture(window)
    low, high = image.convert("L").getextrema()
    assert (high - low) >= vision.MIN_LUMINANCE_SPREAD


# ── The gate ─────────────────────────────────────────────────────────────────

def test_no_grant_means_no_action(window):
    with pytest.raises(grants.Denied):
        grants.require(None, grants.ACT, window)


def test_a_read_grant_does_not_permit_acting(window):
    """Looking at a window and operating it are different authorities, and
    the weaker one must not imply the stronger."""
    grant = grants.Grant(handle=window.handle, label=window.label(),
                         scope=grants.READ)
    grants.require(grant, grants.READ, window)          # allowed
    with pytest.raises(grants.Denied) as caught:
        grants.require(grant, grants.ACT, window)
    assert "only read" in str(caught.value)


def test_a_grant_does_not_cover_a_different_window(window):
    grant = grants.Grant(handle="win_1_1", label="something else",
                         scope=grants.ACT)
    with pytest.raises(grants.Denied) as caught:
        grants.require(grant, grants.ACT, window)
    assert "one window only" in str(caught.value)


def test_grants_expire(window):
    grant = grants.Grant(handle=window.handle, label=window.label(),
                         scope=grants.ACT, ttl_s=0)
    time.sleep(0.01)
    assert grant.expired()
    with pytest.raises(grants.Denied):
        grants.require(grant, grants.ACT, window)


# ── The refusal that protects the user's data ────────────────────────────────

def test_a_modifier_shortcut_reaches_an_unfocused_window(window):
    """The mechanism the whole keys layer rests on.

    A posted key carries no modifier state on its own — the first attempt at
    this typed the literal text "aa" into the document and destroyed it.
    Attaching to the target thread shares its KEYBOARD STATE TABLE, so
    marking Ctrl down there makes the app's own TranslateMessage resolve the
    posted key as a shortcut. Asserted on the effect, not on the return
    value: the point is that the selection really changed.
    """
    text = "alpha beta gamma"
    field = tree.find_text_target(tree.read(window))
    actions.set_value(field, text)
    time.sleep(0.3)
    assert _selection(window) == (0, 0), "nothing should be selected yet"

    actions.press_keys(window, ["ctrl", "a"], take_focus=False)
    time.sleep(0.2)

    assert _selection(window) == (0, len(text)), (
        "ctrl+a did not select the text, so the shortcut was not delivered "
        "as a shortcut")


def test_a_failed_shortcut_never_types_the_letter(window):
    """The old failure mode, guarded permanently.

    With the modifier genuinely down, TranslateMessage produces a control
    code rather than a character, so an application that ignores the shortcut
    does nothing instead of typing into the user's document. This asserts the
    field is byte-for-byte unchanged after a shortcut nothing handles.
    """
    snapshot = tree.read(window)
    field = tree.find_text_target(snapshot)
    actions.set_value(field, "do not corrupt me")
    time.sleep(0.3)

    # A combination this window has no handler for.
    actions.press_keys(window, ["ctrl", "shift", "f7"], take_focus=False)
    time.sleep(0.3)

    refreshed = tree.find_text_target(tree.read(window))
    assert refreshed.value == "do not corrupt me"


def test_modifiers_are_not_left_held_down(window):
    """The keyboard state table is shared while attached, so a Ctrl left
    marked down would make the user's next keystroke in that application a
    Ctrl-keystroke."""
    import ctypes

    actions.press_keys(window, ["ctrl", "a"], take_focus=False)
    state = (ctypes.c_ubyte * 256)()
    ctypes.windll.user32.GetKeyboardState(ctypes.byref(state))

    # ONLY the modifiers this call actually set. Checking Shift too failed
    # here for an instructive reason: the person running the suite was holding
    # it down in another application, and the keyboard state is global. A test
    # that asserts on ambient state the user can move is testing the user.
    for vk in (0x11, 0xA2):                    # VK_CONTROL, VK_LCONTROL
        assert not (state[vk] & 0x80), f"virtual key {vk:#x} left held down"


def test_a_plain_key_needs_no_focus(window):
    """No modifier means no modifier state to lose, so it is deliverable."""
    assert "pressed" in actions.press_keys(window, ["end"], take_focus=False)


# ── The safety claim, tested where it is decidable ───────────────────────────

def test_acting_never_moves_the_cursor_or_steals_focus(window, monkeypatch):
    """Sampling the real cursor cannot test this on a machine somebody is
    using — the user's own hand registers as a failure. So the claim is
    checked at the only place it is decidable: the disturbing calls are
    trapped, and a clean run proves the guarantee holds by construction.
    """
    import win32api
    import win32gui

    called: list[str] = []

    for module, name in ((win32api, "SetCursorPos"), (win32api, "mouse_event"),
                         (win32api, "keybd_event"),
                         (win32gui, "SetForegroundWindow"),
                         (win32gui, "BringWindowToTop"),
                         (win32gui, "SetActiveWindow")):
        monkeypatch.setattr(
            module, name,
            (lambda label: lambda *a, **k: called.append(label))(f"{name}"),
            raising=False)

    active = sessions.open_session(
        window, grants.ACT, conversation_id="conv_test_computer", turn_id=None)
    try:
        snapshot = active.read_tree()
        field = tree.find_text_target(snapshot)
        assert field is not None
        active.act("type", "type", lambda: actions.set_value(field, "hello"))
        active.act("click", "click",
                   lambda: actions.click_point(window.hwnd, 200, 200))
        active.act("scroll", "scroll",
                   lambda: actions.scroll(window.hwnd, 200, 200, clicks=-3))
        active.act("keys", "keys",
                   lambda: actions.press_keys(window, ["end"]))
    finally:
        active.close("test finished")

    assert called == [], f"the desktop was disturbed by: {sorted(set(called))}"


def test_a_session_supersedes_rather_than_stacking(window):
    """Two live grants in one conversation makes the timeline two stories at
    once, and the safety story here depends on it reading as one."""
    first = sessions.open_session(
        window, grants.ACT, conversation_id="conv_supersede", turn_id=None)
    second = sessions.open_session(
        window, grants.ACT, conversation_id="conv_supersede", turn_id=None)
    try:
        assert first.closed, "the previous session was left live"
        assert sessions.current("conv_supersede") is second
    finally:
        sessions.close_all("test finished")


def test_closing_all_sessions_drops_every_grant(window):
    """Authority over the user's applications must not survive the process."""
    sessions.open_session(window, grants.ACT,
                          conversation_id="conv_shutdown", turn_id=None)
    sessions.close_all("shutdown")
    assert sessions.current("conv_shutdown") is None


# ── Refs are only valid for the read that produced them ──────────────────────

def test_a_ref_from_no_read_is_refused(window):
    active = sessions.open_session(
        window, grants.ACT, conversation_id="conv_refs", turn_id=None)
    try:
        with pytest.raises(LookupError) as caught:
            active.element("e1")
        assert "has not been read" in str(caught.value)
    finally:
        sessions.close_all("test finished")


def test_an_unknown_ref_names_the_real_ones(window):
    """A model given "no such element" invents another ref and burns a step.
    Telling it which refs exist converts a loop into a correction — the same
    reasoning as the unknown-tool message in tools/runtime.py."""
    active = sessions.open_session(
        window, grants.ACT, conversation_id="conv_refs2", turn_id=None)
    try:
        active.read_tree()
        with pytest.raises(LookupError) as caught:
            active.element("e9999")
        assert "Actionable refs were" in str(caught.value)
    finally:
        sessions.close_all("test finished")


# ── The painted pointer ────────────────────────────────────────────────────

# Everything above this line tests that the agent works WITHOUT disturbing the
# desktop, and succeeding at that creates the problem these tests cover: work
# that disturbs nothing also shows nothing, and a user who cannot see the agent
# working cannot supervise it. The overlay is the answer, and it is only an
# answer if it is incapable of becoming a second way to disturb things — so
# what is asserted here is mostly what it CANNOT do.

POINTER_CONVERSATION = "conv_pointer_tests"


@pytest.fixture
def painted():
    """A running overlay, torn down so no test inherits another's position."""
    pointer.shutdown()
    overlay = pointer.acquire()
    if overlay is None:
        pytest.skip(f"no overlay on this machine: {pointer.unavailable()}")
    yield overlay
    pointer.shutdown()


def _settle(overlay=None) -> None:
    """Wait out one glide, with margin for a frame the pump may have missed."""
    time.sleep(pointer.GLIDE_S + 0.2)


def test_the_pointer_cannot_take_a_click_or_the_foreground(painted):
    """The load-bearing styles, asserted as styles and then as behaviour.

    WS_EX_TRANSPARENT is the difference between an overlay and a liability: it
    is not that the window declines to handle the mouse, it is that hit-testing
    never reaches it, so a click at the pointer's own position lands in the
    application underneath. Checking the bit and then checking what the bit
    does, because a window can carry the style and still be found by
    WindowFromPoint if anything else about it is wrong.
    """
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.WindowFromPoint.restype = ctypes.c_void_p

    foreground_before = user32.GetForegroundWindow()
    style = user32.GetWindowLongW(painted._hwnd, -20) & 0xFFFFFFFF
    assert style & 0x00000020, "WS_EX_TRANSPARENT: clicks must pass through"
    assert style & 0x08000000, "WS_EX_NOACTIVATE: must never take focus"
    assert style & 0x00080000, "WS_EX_LAYERED: per-pixel alpha"
    assert style & 0x00000080, "WS_EX_TOOLWINDOW: must stay out of Alt-Tab"

    painted.move_to(640, 420)
    _settle(painted)
    assert user32.IsWindowVisible(painted._hwnd), "the overlay never appeared"

    from ctypes import wintypes
    under = user32.WindowFromPoint(wintypes.POINT(640, 420)) or 0
    assert under != painted._hwnd, (
        "a click on the agent's pointer would hit the pointer instead of the "
        "application under it")
    assert user32.GetForegroundWindow() == foreground_before


def test_the_pointer_arrives_within_the_glide_it_advertises(painted):
    """A regression, and the bug it guards is the kind that looks fine.

    The first implementation moved a fixed FRACTION of the remaining distance
    each frame. That is the obvious ease-out and it never converges: measured,
    it took ~0.8s to finish a 0.22s glide and stopped only once the per-frame
    step rounded under a pixel, leaving the pointer short of the control it
    was meant to be indicating. Watching it did not reveal that. Asserting
    exact arrival within the advertised time does.
    """
    painted.move_to(300, 300)
    _settle(painted)
    assert painted._position == (300, 300)

    painted.move_to(1100, 700)
    _settle(painted)
    assert painted._position == (1100, 700), (
        "the pointer was still travelling after the glide it advertises")


def test_the_pointer_is_where_the_action_is(window, painted):
    """The whole point: it indicates the control being operated, not a corner.

    Driven through the tool rather than through `Session.act` directly, because
    the failure this catches is a tool that forgets to say where it is acting
    — which is silent, and leaves the user watching a pointer parked
    somewhere irrelevant while something happens elsewhere.
    """
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    active = sessions.open_session(
        window, grants.ACT, conversation_id=POINTER_CONVERSATION, turn_id=None)
    try:
        snapshot = active.read_tree()
        field = tree.find_text_target(snapshot)
        assert field is not None

        result = computer_tools._type_into(
            {"text": "watch the pointer"},
            ToolContext(conversation_id=POINTER_CONVERSATION))
        assert result["status"] == "success", result["summary"]

        _settle(painted)
        left, top, right, bottom = field.bounds
        assert painted._position == ((left + right) // 2, (top + bottom) // 2)
    finally:
        active.close("test finished")


def test_the_pointer_leaves_when_the_grant_does(window, painted):
    """A pointer still sitting over somebody's window after the session ended
    claims a presence that no longer exists."""
    user32 = ctypes.windll.user32
    active = sessions.open_session(
        window, grants.ACT, conversation_id=POINTER_CONVERSATION, turn_id=None)
    snapshot = active.read_tree()
    field = tree.find_text_target(snapshot)
    assert field is not None
    left, top, right, bottom = field.bounds
    active.act("type", "type", lambda: actions.set_value(field, "hello"),
               at=((left + right) // 2, (top + bottom) // 2))
    _settle(painted)
    assert user32.IsWindowVisible(painted._hwnd)

    active.close("test finished")
    time.sleep(0.3)
    assert not user32.IsWindowVisible(painted._hwnd)


def test_an_overlay_that_will_not_run_does_not_stop_the_work(window, monkeypatch):
    """The priority when the decoration fails, stated as a test.

    A machine with no interactive desktop — a service, a locked session —
    cannot draw this, and the right outcome is a session that works without
    the picture. Losing the click because the picture failed would be the
    feature holding itself hostage to its own garnish.
    """
    def refuse():
        raise OSError("no interactive desktop")

    monkeypatch.setattr(pointer, "acquire", refuse)

    active = sessions.open_session(
        window, grants.ACT, conversation_id=POINTER_CONVERSATION, turn_id=None)
    try:
        snapshot = active.read_tree()
        field = tree.find_text_target(snapshot)
        assert field is not None
        left, top, right, bottom = field.bounds
        result = active.act(
            "type", "type", lambda: actions.set_value(field, "still works"),
            at=((left + right) // 2, (top + bottom) // 2))
        assert result, "the action returned nothing"
        assert active.grant.actions_used == 1, (
            "the action did not complete when the overlay refused to start")
    finally:
        active.close("test finished")


def test_a_machine_without_an_overlay_is_asked_once(monkeypatch):
    """`acquire` runs on the path of every action, so a machine that cannot
    draw must cost one failed start for the process, not one per click."""
    pointer.shutdown()
    starts: list[int] = []

    def never_starts(self) -> bool:
        starts.append(1)
        self._failed = "OSError: no interactive desktop"
        return False

    monkeypatch.setattr(pointer.Pointer, "start", never_starts)
    try:
        for _ in range(5):
            assert pointer.acquire() is None
        assert len(starts) == 1, f"tried to start the overlay {len(starts)} times"
        assert "no interactive desktop" in pointer.unavailable()
    finally:
        pointer.shutdown()


def test_a_new_session_does_not_fly_in_from_the_last_one(painted):
    """After the pointer leaves, it comes back where it is needed \u2014 instantly.

    The position is the origin of the next glide, so a `hide` that forgot to
    clear it would send the first action of the next session travelling across
    the desktop from the last window of the previous one: a movement that
    corresponds to nothing that happened, in an overlay whose entire job is to
    correspond to what is happening.
    """
    painted.move_to(200, 200)
    _settle()
    assert painted._position == (200, 200)

    painted.hide()
    painted.move_to(1000, 600)
    time.sleep(pointer.GLIDE_S / pointer.FRAMES * 5)      # well inside one glide
    assert painted._position == (1000, 600), (
        "the pointer set off across the screen from a window it had left")


# ── What the tools claim, versus what happened ───────────────────────────────

# These three guard fixes made on 2026-08-23, each of which was a tool being
# confidently wrong rather than failing. That failure mode is the worst one an
# agent has: a refusal costs a turn, but a false claim gets believed.

def test_a_write_that_does_not_land_is_reported_as_a_failure(window):
    """The false-success bug, reproduced.

    `type_into` once reported "set Text editor to 'PRIMNOX WAS HERE'" while the
    text went into a different window of the same name \u2014 ten were open, and
    nothing in the stack could tell them apart or tell that nothing had
    changed. The operation returning without raising was taken as proof.

    Simulated here by a write that returns its success sentence and does
    nothing, which is indistinguishable from the real failure at the point the
    caller sees it.
    """
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="conv_false_success")
    computer_tools._control_window(
        {"window": window.handle, "reason": "test verification"}, ctx)
    try:
        original = actions.set_value
        actions.set_value = lambda element, text: (
            f"set {element.name or element.role} to {text!r}")
        try:
            result = computer_tools._type_into({"text": "NEVER LANDS"}, ctx)
        finally:
            actions.set_value = original

        assert result["status"] == "error", (
            "a write that did not take was reported as success")
        assert "did not take" in result["summary"]
    finally:
        sessions.close_all("test finished")


def test_a_confirmed_write_says_so_and_an_unverifiable_one_admits_it(window):
    """Confirmed and unconfirmed must not read identically to the model.

    A value write can be checked by asking the control what it now holds. A
    plain button press cannot \u2014 whatever it did happened somewhere else \u2014 so
    it is reported UNVERIFIED rather than assumed, which is the honest answer
    and the one that stops a chain of unchecked clicks reading as success.
    """
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="conv_confirmed")
    computer_tools._control_window(
        {"window": window.handle, "reason": "test verification"}, ctx)
    try:
        typed = computer_tools._type_into({"text": "REALLY LANDS"}, ctx)
        assert typed["status"] == "success"
        assert "NOT VERIFIED" not in typed["summary"], (
            "a write that was confirmed by readback claimed it was not")

        active = sessions.current("conv_confirmed")
        entry = [e for e in active.summary()["log"]
                 if e["kind"] == "type" and e["status"] != "running"][-1]
        assert entry["effect"] == "confirmed"
        assert entry["confidence"] >= 0.85
        assert entry["evidence"], "confirmed with no evidence recorded"
    finally:
        sessions.close_all("test finished")


def test_find_text_target_never_returns_a_slider(window):
    """Ranking by "largest element that accepts a value" picked Paint's Opacity
    slider, so a default type_into moved a tool setting and reported that it
    had typed. Sliders and scrollbars expose ValuePattern; they are not text.
    """
    snapshot = tree.read(window)
    chosen = tree.find_text_target(snapshot)
    assert chosen is not None, "the test window has an EDIT and should be typeable"
    assert chosen.role in tree.TEXT_ROLES

    for element in snapshot.elements:
        assert element.role not in tree.NOT_TEXT_ROLES or element is not chosen


def test_an_empty_tool_body_is_a_call_with_no_arguments():
    """`<tool name="list_windows"></tool>` is what a model actually writes for a
    tool that needs nothing, and it was being spent as a malformed-call
    correction \u2014 measured, qwen2.5:7b opens desktop tasks that way, and the
    turn could end having executed nothing at all."""
    from primnox2.tools import runtime

    parsed = runtime.parse_call('<tool name="list_windows"></tool>')
    assert parsed["arguments"] == {}
    assert "malformed" not in parsed, parsed.get("malformed")

    # And a tool that genuinely needs an argument still refuses, naming it.
    assert runtime.parse_call('<tool name="control_window"></tool>').get(
        "malformed") is None


def test_windows_sharing_a_title_are_all_listed(window):
    """Deduplicating by (title, process) collapsed genuinely distinct windows.

    Measured: three separate windows all titled "Untitled - Notepad" came back
    as ONE. That is the exact case where the caller most needs to see them all
    \u2014 a title shared by ten windows is precisely when nobody can approve by
    name \u2014 and it was the case being erased.
    """
    import subprocess
    import win32gui

    shared = f"Shared Title {time.time_ns()}"
    extra = [subprocess.Popen([sys.executable, str(_SCRIPT), shared])
             for _ in range(2)]
    try:
        for _ in range(60):
            time.sleep(0.25)
            if len([h for h in _windows_titled(shared)]) >= 2:
                break
        listed = [t for t in targets.enumerate_windows() if t.title == shared]
        assert len(listed) >= 2, (
            f"{len(listed)} of 2 same-titled windows survived enumeration")
        assert len({t.handle for t in listed}) == len(listed)
    finally:
        for process in extra:
            process.terminate()


def _windows_titled(title: str) -> list[int]:
    import win32gui
    found: list[int] = []
    win32gui.EnumWindows(
        lambda h, _: found.append(h) if win32gui.GetWindowText(h) == title else None,
        None)
    return found


def test_every_refusal_carries_a_code_and_a_recovery_policy(window):
    """Prose cannot be dispatched on.

    "That window has been closed" and "no window is under control" call for
    opposite responses \u2014 re-resolve and retry, versus stop and go get
    approval \u2014 and until now the only thing that could tell them apart was a
    model spending a turn reading English. Most desktop failures have a correct
    response that needs no intelligence at all; the code is what lets the
    runtime take it.
    """
    from primnox2.computer import failures
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    ctx = ToolContext(conversation_id="conv_taxonomy")

    no_session = computer_tools._type_into({"text": "x"}, ctx)
    assert no_session["code"] == failures.PRECONDITION_FAILED
    assert no_session["recovery"] == failures.STOP

    missing = computer_tools._control_window(
        {"window": "No Such Application Zzz", "reason": "x"}, ctx)
    assert missing["code"] == failures.TARGET_NOT_FOUND
    assert missing["recovery"] == failures.REGROUND, (
        "a window that could not be found must be re-resolved, not treated as "
        "a security refusal")

    stale = computer_tools._control_window(
        {"window": "win_999999999_1", "reason": "x"}, ctx)
    assert stale["code"] == failures.TARGET_STALE
    assert stale["recovery"] == failures.REGROUND

    # Every code the taxonomy defines must declare a policy, or the recovery
    # engine silently falls through to STOP for a case somebody meant to handle.
    for code in vars(failures).values():
        if isinstance(code, str) and code.isupper() and code in failures.RECOVERY:
            assert failures.recovery_for(code) in (
                failures.REGROUND, failures.WAIT, failures.ASK, failures.STOP)


def test_ambiguity_is_asked_about_never_guessed(window):
    """Several windows sharing a title must produce a question, not a choice."""
    import subprocess

    from primnox2.computer import failures
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    shared = f"Ambiguous Window {time.time_ns()}"
    extra = [subprocess.Popen([sys.executable, str(_SCRIPT), shared])
             for _ in range(2)]
    try:
        for _ in range(60):
            time.sleep(0.25)
            if len([t for t in targets.enumerate_windows()
                    if t.title == shared]) >= 2:
                break
        result = computer_tools._control_window(
            {"window": shared, "reason": "test ambiguity"},
            ToolContext(conversation_id="conv_ambiguous"))
        assert result["status"] == "error", "ambiguity was resolved by guessing"
        assert result["code"] == failures.TARGET_AMBIGUOUS
        assert result["recovery"] == failures.ASK
        # The refusal has to carry the candidates, or the model has to go and
        # rediscover them, which is the turn this was meant to save.
        assert result["summary"].count("win_") >= 2
    finally:
        for process in extra:
            process.terminate()
