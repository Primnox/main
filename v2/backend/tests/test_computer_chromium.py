"""The Chromium adapter — reading the page instead of the painting of it.

A browser window read through UIA is mostly not the page. Measured here, the
same window: 229 elements through the accessibility tree, 4 through the
browser's own protocol — and the 4 are the page, while most of the 229 are
tab strips, toolbar buttons and layout nodes. UIA also truncates at 800
elements, so on a content-heavy page the model reads a partial view and has no
way to know which part it lost.

The claim these tests exist to defend is not "CDP is faster". It is that a
page element behaves like ANY other element everywhere else in this package:
`actions.invoke` works on it, `tree.live_value` verifies it, and neither
knows or asks which backend it came from. That is what makes this an adapter
rather than a second implementation, and it is the thing that would rot
silently if nothing checked it.

These spawn their own browser with `--remote-debugging-port` on a throwaway
profile, because the point of the discovery code is that it only works when
the flag is present — and a user's ordinary browser does not have it.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Computer Use is Windows-only")

from primnox2.computer import (actions, chromium, grants, session as sessions,
                               targets, tree)

PAGE = ("data:text/html,<title>Primnox Adapter Test</title>"
        "<h1>Heading</h1>"
        "<input id=box value=start>"
        "<button onclick=\"document.getElementById('box').value='clicked'\">Go</button>"
        "<input type=checkbox id=flag>"
        "<a href='#somewhere'>A link</a>")


def find_browser() -> "Path | None":
    import os

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Opera GX/opera.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Opera/opera.exe",
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    ]
    return next((c for c in candidates if c.exists()), None)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def browser(tmp_path_factory):
    """A real browser window with the debugging port on, and its own profile.

    Its own profile matters for more than tidiness: attaching a debugger to a
    browser somebody is signed into gives whatever holds the port the ability
    to read every page in it, and a test suite should not be the thing that
    does that to a developer's session.
    """
    executable = find_browser()
    if executable is None:
        pytest.skip("no Chromium browser installed to test the adapter against")

    port = free_port()
    profile = tmp_path_factory.mktemp("cdp-profile")
    process = subprocess.Popen([
        str(executable), f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}", "--no-first-run", "--disable-extensions",
        # A real window, because window-to-page matching is half of what is
        # being tested and headless has no window to match. Parked off-screen
        # so a suite run does not take over the desktop of whoever is running
        # it — the window is genuinely there, it is just not in the way.
        "--window-size=900,600", "--window-position=-2400,-2400", PAGE,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    target = None
    for _ in range(60):
        time.sleep(0.5)
        found = [t for t in targets.enumerate_windows()
                 if "Primnox Adapter Test" in t.title]
        if found and chromium.endpoint_for(found[0]):
            target = found[0]
            break
    if target is None:
        process.terminate()
        pytest.skip("the test browser did not come up with a debugging port")

    try:
        yield target, port
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except Exception:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)


# ── Discovery ───────────────────────────────────────────────────────────────

def test_a_browser_with_the_flag_is_found(browser):
    target, port = browser
    assert chromium.endpoint_for(target) == f"http://127.0.0.1:{port}"


def test_a_process_without_the_flag_has_no_port():
    """The ordinary answer, and it must not be an error. A normally-started
    browser reads perfectly well through UIA; this route only ever adds one.

    Asked of this process rather than of whatever browsers happen to be open,
    because a developer machine may well have one running with the flag on for
    unrelated reasons, and a test that fails because of that is testing the
    desktop rather than the code."""
    import os

    assert chromium._debug_port(os.getpid()) is None


def test_a_window_that_is_not_chromium_is_not_probed():
    """Walking the process tree of every window looking for a flag would cost
    a psutil call per window on every enumeration."""
    plain = targets.Target(
        handle="win_1_1", hwnd=1, pid=1, title="Notepad", window_class="Notepad",
        process="notepad.exe", bounds=(0, 0, 100, 100), foreground=False,
        minimized=False)
    assert chromium.endpoint_for(plain) is None


def test_the_refusal_explains_why_and_names_the_route_that_works():
    plain = targets.Target(
        handle="win_1_1", hwnd=1, pid=1, title="Notepad", window_class="Notepad",
        process="notepad.exe", bounds=(0, 0, 100, 100), foreground=False,
        minimized=False)
    with pytest.raises(chromium.Unavailable) as raised:
        chromium.read(plain)
    assert "remote-debugging-port" in str(raised.value)
    assert "accessibility tree still works" in str(raised.value)


# ── Reading ─────────────────────────────────────────────────────────────────

def test_the_page_is_read_as_the_page(browser):
    target, _ = browser
    snapshot = chromium.read(target)
    roles = {e.role for e in snapshot.elements}
    assert "Button" in roles and "Edit" in roles


def test_the_page_read_is_far_smaller_than_the_window_read(browser):
    """The context argument, on a page with five controls. On a real page the
    window read also truncates, and this one does not."""
    target, _ = browser
    page = chromium.read(target)
    window = tree.read(target)
    assert len(page.elements) < len(window.elements) / 10, (
        f"{len(page.elements)} page elements against "
        f"{len(window.elements)} window elements")


def test_a_control_carries_what_it_can_do(browser):
    target, _ = browser
    snapshot = chromium.read(target)
    button = next(e for e in snapshot.elements if e.role == "Button")
    box = next(e for e in snapshot.elements if e.role == "Edit")
    assert button.patterns == ["invoke"]
    assert "set_value" in box.patterns


def test_a_label_is_not_repeated_as_its_own_element(browser):
    """A button's label is also a StaticText child carrying the same words.
    Keeping both doubles the read to say nothing."""
    target, _ = browser
    names = [e.name for e in chromium.read(target).elements if e.name]
    assert len(names) == len(set(names)), f"duplicated: {names}"


# ── Acting, which is the claim that matters ─────────────────────────────────

def test_actions_invoke_works_on_a_page_element_unchanged(browser):
    """`actions.py` was not modified for this. If it had to be, the adapter
    would be a second implementation rather than a backend."""
    target, _ = browser
    snapshot = chromium.read(target)
    box = next(e for e in snapshot.elements if e.role == "Edit")
    button = next(e for e in snapshot.elements if e.role == "Button")

    actions.set_value(box, "before")
    actions.invoke(button)
    time.sleep(0.3)
    assert tree.live_value(box) == "clicked"


def test_setting_a_value_tells_the_page_it_changed(browser):
    """Assigning `.value` alone leaves a framework's own state holding the old
    text — the write lands visually and is discarded on submit."""
    target, _ = browser
    box = next(e for e in chromium.read(target).elements if e.role == "Edit")
    actions.set_value(box, "typed through the protocol")
    assert tree.live_value(box) == "typed through the protocol"


def test_a_toggle_reads_and_flips(browser):
    target, _ = browser
    flag = next((e for e in chromium.read(target).elements
                 if e.role == "CheckBox"), None)
    if flag is None:
        pytest.skip("the checkbox was not exposed")
    before = tree.live_toggle(flag)
    # `invoke` is the entry point for toggles too — it dispatches on the
    # element's own patterns, which is exactly the indirection that lets a
    # page element and a UIA element go through the same call.
    actions.invoke(flag)
    time.sleep(0.2)
    assert tree.live_toggle(flag) != before


def test_a_ref_still_works_after_the_socket_is_dropped(browser):
    """Sockets are not held across turns; refs are. Acting on one reopens."""
    target, _ = browser
    box = next(e for e in chromium.read(target).elements if e.role == "Edit")
    time.sleep(0.5)                       # the read's socket is long closed
    actions.set_value(box, "after the socket went away")
    assert tree.live_value(box) == "after the socket went away"


# ── Through the session and the tool ────────────────────────────────────────

def test_page_refs_and_window_refs_can_be_held_at_once(browser):
    """`e3@7` and `p3@7` have to be unambiguous, or a model holding both has
    no way to say which one it means."""
    target, _ = browser
    active = sessions.open_session(target, grants.ACT,
                                   conversation_id="conv_cdp_session",
                                   turn_id=None)
    try:
        window = active.read_tree()
        page = active.read_page()
        assert page.generation == window.generation + 1, (
            "the two backends are not sharing one generation counter")

        from_window = active.element(
            active.snapshot.actionable()[0].qualified(window.generation))
        from_page = active.element(f"p1@{page.generation}")
        assert from_window.ref.startswith("e")
        assert from_page.ref.startswith("p")
    finally:
        active.close("test finished")


def test_a_page_ref_before_any_page_read_says_so(browser):
    target, _ = browser
    active = sessions.open_session(target, grants.ACT,
                                   conversation_id="conv_cdp_norread",
                                   turn_id=None)
    try:
        active.read_tree()
        with pytest.raises(LookupError) as raised:
            active.element("p1@1")
        assert "read_page" in str(raised.value)
    finally:
        active.close("test finished")


def test_the_tool_says_the_browser_chrome_is_not_in_this_view(browser):
    """A model told only "here is the page" will look for the back button in
    it and conclude the browser has none."""
    from primnox2.tools import computer as computer_tools
    from primnox2.tools.registry import ToolContext

    target, _ = browser
    ctx = ToolContext(conversation_id="conv_cdp_tool")
    computer_tools._control_window(
        {"window": target.handle, "reason": "adapter test"}, ctx)
    try:
        result = computer_tools._read_page({}, ctx)
        assert result["status"] == "success", result["summary"]
        assert "address bar" in result["output"]
        assert "read_window" in result["output"]
    finally:
        active = sessions.current("conv_cdp_tool")
        if active:
            active.close("test finished")
