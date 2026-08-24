"""Window discovery — what the agent is allowed to have an opinion about.

A "target" is one top-level window, identified by an opaque handle string
rather than a raw HWND. Handles are recycled by Windows, so a bare integer is
not a safe identity across time: close a window, open another, and the number
can come back attached to something else entirely. Every target therefore
carries the creation-time identity of what it pointed at (pid, class, title),
and `resolve` refuses a handle whose window no longer matches — a grant for
Notepad must never silently become a grant for whatever inherited its HWND.

Enumeration is deliberately narrow. `EnumWindows` reports several hundred
objects on a normal desktop, almost all of them invisible shells, zero-size
message sinks, and cloaked UWP hosts. Handing that list to a model produces
confident clicks on things that are not on screen, so the filter here is
aggressive and its reasons are written down next to each rule.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, asdict

import win32api
import win32con
import win32gui
import win32process

_dwm = ctypes.windll.dwmapi

# A window can be visible by `IsWindowVisible` and still not be on screen.
# UWP/WinUI apps keep a hidden `ApplicationFrameWindow` alive per suspended
# app, and it answers "yes" to IsWindowVisible while DWM has it cloaked. Every
# Store app the user has ever opened shows up this way. Asking DWM directly is
# the only reliable test.
DWMWA_CLOAKED = 14

# Below this, a window is a tooltip, a drop shadow, or a message-only sink —
# not something anybody can be asked to approve control of.
MIN_WIDTH, MIN_HEIGHT = 120, 80

# The shell's own windows. `Progman` and `WorkerW` are the desktop itself —
# full-screen, titled "Program Manager", and therefore the largest match for
# almost any query, which put the desktop at the top of the candidate list.
# Approving "control of Program Manager" means control of the desktop icons
# and, through them, the shell; it is never what a user meant to say yes to.
#
# `Windows.UI.Core.CoreWindow` is deliberately NOT listed. It looks like shell
# machinery and usually is, but a UWP app with no frame host presents only as
# a CoreWindow, and blocking the class outright would make those apps
# invisible. The pairing rule in `enumerate_windows` already resolves the
# common double-listing without hiding anything.
SHELL_CLASSES = frozenset({
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "NotifyIconOverflowWindow",
})

# Browsers, recognised two ways because neither is sufficient alone.
# `Chrome_WidgetWin_1` is the class every Chromium build uses — Chrome, Edge,
# Opera, Brave, and also every Electron app, which is why the class alone
# cannot be trusted. The process list catches the real browsers; the class
# catches a browser whose executable has been renamed.
BROWSER_CLASSES = frozenset({"MozillaWindowClass"})
BROWSER_PROCESSES = frozenset({
    "chrome.exe", "msedge.exe", "opera.exe", "brave.exe", "firefox.exe",
    "vivaldi.exe", "arc.exe", "zen.exe",
})


@dataclass(frozen=True)
class Target:
    """One window, as the agent and the user both see it."""
    handle: str          # opaque; "win_<hwnd>_<pid>"
    hwnd: int
    pid: int
    title: str
    window_class: str
    process: str
    bounds: tuple[int, int, int, int]     # left, top, right, bottom (screen)
    foreground: bool
    minimized: bool

    @property
    def size(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return right - left, bottom - top

    def label(self) -> str:
        """How this window is named in a permission prompt.

        The process name is included because the title alone is forgeable and
        often generic — three different apps on this machine present a window
        titled "Settings". The user is approving control of a *program*.
        """
        name = self.title.strip() or "(untitled window)"
        return f"{name} — {self.process}" if self.process else name

    @property
    def is_browser(self) -> bool:
        """Whether this window is a web browser.

        Worth knowing because a browser is not one application, it is a
        different application per tab — and because its accessibility tree is
        the live DOM rather than a fixed set of controls, so it is both far
        deeper than a native window's and far more worth reading. The two
        adjustments that follow from this are in `tree.read` (depth) and in
        the browser page's own document element being the thing to act on.
        """
        return self.window_class in BROWSER_CLASSES or self.process.lower() in BROWSER_PROCESSES

    def to_json(self) -> dict:
        data = asdict(self)
        data["bounds"] = list(self.bounds)
        data["label"] = self.label()
        data["is_browser"] = self.is_browser
        return data


def _cloaked(hwnd: int) -> bool:
    value = wintypes.DWORD(0)
    result = _dwm.DwmGetWindowAttribute(
        wintypes.HWND(hwnd), wintypes.DWORD(DWMWA_CLOAKED),
        ctypes.byref(value), ctypes.sizeof(value))
    # A non-zero HRESULT means DWM has no opinion (pre-composition window);
    # treat that as "not cloaked" rather than hiding a real window.
    return result == 0 and value.value != 0


def _process_name(pid: int) -> str:
    """Best-effort image name. Never raises: a window we cannot identify is
    still a window, and dropping it would hide the very thing most worth
    being careful about."""
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except Exception:
        # Protected and elevated processes deny the query. That is worth
        # knowing rather than papering over — `vision.capture` fails on these
        # too, and for the same reason.
        return ""
    try:
        return win32process.GetModuleFileNameEx(handle, 0).rsplit("\\", 1)[-1]
    except Exception:
        return ""
    finally:
        win32api.CloseHandle(handle)


def _describe(hwnd: int, foreground: int) -> "Target | None":
    try:
        title = win32gui.GetWindowText(hwnd) or ""
        cls = win32gui.GetClassName(hwnd) or ""
        bounds = win32gui.GetWindowRect(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return None
    return Target(
        handle=f"win_{hwnd}_{pid}",
        hwnd=hwnd, pid=pid, title=title, window_class=cls,
        process=_process_name(pid), bounds=bounds,
        foreground=(hwnd == foreground),
        minimized=bool(win32gui.IsIconic(hwnd)),
    )


# The hosted half of a UWP window. Real, but it does not accept input — see
# the pairing note in enumerate_windows.
UWP_CORE_CLASS = "Windows.UI.Core.CoreWindow"


def enumerate_windows(*, include_minimized: bool = True) -> list[Target]:
    """Every window a user could plausibly point at, best candidates first."""
    found: list[Target] = []
    foreground = win32gui.GetForegroundWindow()

    def visit(hwnd: int, _) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if not win32gui.GetWindowText(hwnd):
            # An untitled top-level window is machinery. Naming it in a
            # permission prompt would produce "Allow Primnox to control
            # (untitled window)?" — a question nobody can answer safely.
            return True
        if _cloaked(hwnd):
            return True
        if win32gui.GetClassName(hwnd) in SHELL_CLASSES:
            return True
        target = _describe(hwnd, foreground)
        if target is None:
            return True
        width, height = target.size
        # A minimized window reports a nonsense rect (-32000), so the size
        # filter must not be applied to it or every minimized app vanishes.
        if not target.minimized and (width < MIN_WIDTH or height < MIN_HEIGHT):
            return True
        if target.minimized and not include_minimized:
            return True
        found.append(target)
        return True

    win32gui.EnumWindows(visit, None)

    # UWP apps present twice: an `ApplicationFrameWindow` host and the
    # `Windows.UI.Core.CoreWindow` it hosts, with identical titles. Both are
    # real handles, but only the frame accepts input, and offering the user the
    # same app twice invites approving the half that cannot be driven.
    #
    # Collapsing them by (title, process) was too blunt, and hid real windows.
    # Measured: three separate windows all titled "Untitled - Notepad" came back
    # as ONE, because two windows of one program legitimately share both a title
    # and a process name. That is the exact situation the caller most needs to
    # see — a title shared by ten Notepads is precisely when the user cannot
    # safely approve by name — and it was the situation this silently erased.
    #
    # So identity is the handle, and only the UWP pairing is collapsed, matched
    # on the two classes that actually form it rather than on a coincidence of
    # naming.
    frames = {t.title for t in found
              if t.window_class == "ApplicationFrameWindow"}
    deduped = [t for t in found
               if not (t.window_class == UWP_CORE_CLASS and t.title in frames)]

    return sorted(deduped, key=_rank)


def _rank(target: Target) -> tuple:
    """Foreground first, then visible, then largest — the order a person would
    guess at if asked "which window did you mean"."""
    width, height = target.size
    return (not target.foreground, target.minimized, -(width * height), target.title)


def find(query: str) -> list[Target]:
    """Windows matching a human phrase — a title fragment or a process name."""
    needle = (query or "").strip().lower()
    if not needle:
        return []
    return [t for t in enumerate_windows()
            if needle in t.title.lower() or needle in t.process.lower()]


class Stale(LookupError):
    """The window a handle names is gone, or is no longer the same window."""


def resolve(handle: str) -> Target:
    """Turn a handle back into a live window, or refuse.

    The identity check is the point. Windows recycles HWNDs aggressively, and
    a grant is authority over a *specific* window; letting a stale handle
    resolve to whatever now owns that number would convert an expired approval
    for a text editor into live authority over a banking tab.
    """
    try:
        _, raw, pid_text = handle.split("_", 2)
        hwnd, expected_pid = int(raw), int(pid_text)
    except (ValueError, AttributeError):
        raise Stale(f"{handle!r} is not a window handle")

    if not win32gui.IsWindow(hwnd):
        raise Stale("That window has been closed.")

    target = _describe(hwnd, win32gui.GetForegroundWindow())
    if target is None:
        raise Stale("That window can no longer be inspected.")
    if target.pid != expected_pid:
        raise Stale(
            "That window handle now belongs to a different program. Windows "
            "reuses window handles after a window closes, so this is a new "
            "window that happens to share the old number — not the one that "
            "was approved. Ask for the window list again.")
    return target
