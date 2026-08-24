"""Background input — clicking and typing without taking the machine.

The promise this module makes is narrow and testable: while the agent works,
the user's mouse pointer does not move, their focused window does not change,
and their keystrokes keep going where they were going. Nothing here calls
`SetCursorPos`, `mouse_event`, or `SetForegroundWindow`. That is the whole
mechanism — the guarantee is structural, not defensive.

Three delivery routes exist, and they are tried in this order because that is
the order of decreasing reliability:

  1. UIA control patterns. Delivered to the control itself, so focus and
     coordinates are both irrelevant. This is the only route that reaches
     WinUI and XAML controls at all, since those report no window handle:
     measured on Notepad's toolbar, `TogglePattern.Toggle()` flipped Bold
     from 0 to 1 on an element whose `NativeWindowHandle` was 0.
  2. Posted mouse messages. `PostMessage(WM_LBUTTONDOWN)` with client
     coordinates, for anything with a real window handle and no useful
     pattern — canvases, custom-drawn controls, plain Win32 children.
  3. Nothing. Some things cannot be done in the background, and this module
     says so rather than doing something else that looks similar.

## How a background hotkey is possible

Two obvious mechanisms do not work, and the third does. All three were
measured, because the first two fail in ways that damage data rather than
raise errors:

  PostMessage alone does not carry modifier state. The target thread's
  keyboard state is never updated, so an app receiving WM_KEYDOWN(VK_A)
  after WM_KEYDOWN(VK_CONTROL) sees a plain "A". Measured against Notepad:
  a posted Ctrl+A typed the literal text "aa" into the document and
  destroyed its contents. It did not fail — it silently did the most
  damaging plausible thing available to it.

  AttachThreadInput plus SendInput does not reach the window. Synthesised
  input goes to whatever holds the real foreground regardless of thread
  attachment, so the selection was untouched and the keystroke went to the
  foreground application instead — worse than failing, because the keys
  landed in a window nobody approved.

  AttachThreadInput plus SetKeyboardState plus PostMessage works. This is
  the route taken. Attaching shares the target thread's KEYBOARD STATE
  TABLE, not just its queue, so marking VK_CONTROL down in that table makes
  the modifier real from the application's point of view. The app's own
  message loop then calls TranslateMessage on the posted key using that
  shared state and resolves it as a shortcut. Measured on Notepad while a
  full-screen game held the foreground: Ctrl+A selected the document,
  Ctrl+Home collapsed the selection, and Ctrl+Shift+End re-selected to the
  end — with no cursor movement and no foreground change.

Two details of that route matter enough to be load-bearing:

  `SetFocus` is deliberately NOT called. Reading `GetFocus()` from the
  shared queue returns the control the application itself considers
  focused, which is where the user left their caret. Moving it would be a
  real disturbance even though the system foreground never changes.

  The modifier is cleared in a `finally`. The keyboard state table is
  shared while attached, so a Ctrl left marked down does not stay a local
  bug — it makes the user's next keystroke in that application a
  Ctrl-keystroke.

The failure mode is also better than the old one. With Ctrl genuinely down,
TranslateMessage produces a control code (Ctrl+A is 0x01) rather than a
letter, and edit controls discard it. An app that ignores the shortcut now
does nothing instead of typing garbage into the document.
"""
from __future__ import annotations

import ctypes
import time

import win32api
import win32con
import win32gui
import win32process

from . import targets, tree

_u32 = ctypes.windll.user32

# Posted input is asynchronous: PostMessage returns as soon as the message is
# queued, not when the app has handled it. Reading the tree back immediately
# therefore observes the state from before the action. This is the settle
# time before a caller may believe what it reads.
SETTLE_S = 0.12

# Typing through WM_CHAR is one message per character. A paragraph posted at
# full speed overruns the input queue of some apps and drops characters, and
# it also produces a burst no human could type, which is what trips the
# "automated input" heuristics in a few applications.
CHAR_DELAY_S = 0.004

VK = {
    "ctrl": win32con.VK_CONTROL, "control": win32con.VK_CONTROL,
    "alt": win32con.VK_MENU, "shift": win32con.VK_SHIFT,
    "win": win32con.VK_LWIN, "enter": win32con.VK_RETURN,
    "return": win32con.VK_RETURN, "tab": win32con.VK_TAB,
    "esc": win32con.VK_ESCAPE, "escape": win32con.VK_ESCAPE,
    "backspace": win32con.VK_BACK, "delete": win32con.VK_DELETE,
    "home": win32con.VK_HOME, "end": win32con.VK_END,
    "pageup": win32con.VK_PRIOR, "pagedown": win32con.VK_NEXT,
    "up": win32con.VK_UP, "down": win32con.VK_DOWN,
    "left": win32con.VK_LEFT, "right": win32con.VK_RIGHT,
    "space": win32con.VK_SPACE,
    "insert": win32con.VK_INSERT,
    # F1–F12. Left out at first, which made `f2` (rename) and `f5` (refresh)
    # — two of the most useful shortcuts there are — parse as unknown keys.
    **{f"f{n}": win32con.VK_F1 + n - 1 for n in range(1, 13)},
}
MODIFIERS = frozenset({"ctrl", "control", "alt", "shift", "win"})

# The left-hand twin of each modifier, marked down alongside the neutral one.
# Applications disagree about which they check: `GetKeyState(VK_CONTROL)` is
# the common test, but enough code asks for VK_LCONTROL specifically that
# setting only the neutral key makes a shortcut work in one app and silently
# not in the next. Setting both costs nothing and removes the whole class.
_SIDED = {
    "ctrl": win32con.VK_LCONTROL, "control": win32con.VK_LCONTROL,
    "alt": win32con.VK_LMENU, "shift": win32con.VK_LSHIFT,
}


# ── Routes, named ───────────────────────────────────────────────────────────
#
# The three delivery routes described above, as values that can be recorded.
# The rung is from the semantic ladder: the higher an action was delivered,
# the less it depended on the window being where it looked. That distinction
# is invisible in a log that only says "clicked Save" — and it is the first
# thing worth knowing when the same step later fails, because a pattern
# invocation that stops working means the control changed, while a coordinate
# click that stops working usually means only that something moved.
ROUTE_PATTERN = "uia_pattern"           # rung L3 — invoke / set_value / toggle
ROUTE_MESSAGE = "posted_message"        # rung L1 — click / scroll / type at a point
ROUTE_ATTACHED = "attached_input"       # rung L1 — keys, without taking focus
ROUTE_FOREGROUND = "foreground_input"   # rung L1 — keys, with the user's focus

RUNGS = {
    ROUTE_PATTERN: "L3",
    ROUTE_MESSAGE: "L1",
    ROUTE_ATTACHED: "L1",
    ROUTE_FOREGROUND: "L1",
}


class ActionFailed(RuntimeError):
    """An action could not be delivered. The message is written for the model."""


class NeedsFocus(ActionFailed):
    """Only possible by taking the user's focus, which was not authorised."""


def _lparam(x: int, y: int) -> int:
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def _settle() -> None:
    time.sleep(SETTLE_S)


# ── Element actions: route 1, the reliable one ───────────────────────────────

def invoke(element: tree.Element) -> str:
    """Operate an element the way its own accessibility contract says to.

    The pattern is chosen from what the element actually supports rather than
    from what its control type suggests, for the reason in `tree.py`: type is
    not capability.
    """
    if not element.enabled:
        raise ActionFailed(
            f"{element.role} {element.name!r} is disabled. The application is "
            "refusing this control, not the agent — something else has to "
            "change first.")

    if "invoke" in element.patterns:
        _run(element, lambda c: c.GetInvokePattern().Invoke())
        return f"invoked {element.role} {element.name!r}"

    if "toggle" in element.patterns:
        before = _toggle_state(element)
        _run(element, lambda c: c.GetTogglePattern().Toggle())
        after = _toggle_state(element)
        return (f"toggled {element.name!r} from {before} to {after}"
                if before != after else
                f"toggled {element.name!r} but its state stayed {after}")

    if "select" in element.patterns:
        _run(element, lambda c: c.GetSelectionItemPattern().Select())
        return f"selected {element.name!r}"

    if "expand" in element.patterns:
        _run(element, lambda c: c.GetExpandCollapsePattern().Expand())
        return f"expanded {element.name!r}"

    # No pattern: fall through to a posted click at the element's centre, but
    # only if it has a window to post to. A pattern-less, handle-less element
    # is unreachable, and saying so is more useful than a click into space.
    if element.hwnd:
        return click_point(element.hwnd, *_centre_client(element))

    raise ActionFailed(
        f"{element.role} {element.name!r} supports no accessibility action "
        "and has no window handle, so there is nothing to send it. This is "
        "usually a decorative element — check whether its parent is the "
        "thing meant to be operated.")


def set_value(element: tree.Element, text: str) -> str:
    """Replace an element's text. Genuinely works unfocused.

    Note this REPLACES rather than appends — `ValuePattern.SetValue` is a
    whole-value write. Appending means reading the current value first and
    writing the concatenation, which the caller must do deliberately, because
    silently appending would make it impossible to clear a field.
    """
    if "set_value" not in element.patterns:
        raise ActionFailed(
            f"{element.role} {element.name!r} does not accept a text value. "
            "Read the window again and pick an element whose capabilities "
            "include set_value.")
    if not element.enabled:
        raise ActionFailed(f"{element.name!r} is read-only or disabled.")

    _run(element, lambda c: c.GetValuePattern().SetValue(text))
    shown = text if len(text) <= 60 else text[:60] + "…"
    return f"set {element.name or element.role} to {shown!r}"


def _toggle_state(element: tree.Element) -> str:
    try:
        return {0: "off", 1: "on", 2: "indeterminate"}.get(
            element.control.GetTogglePattern().ToggleState, "unknown")
    except Exception:
        return "unknown"


def _run(element: tree.Element, operation) -> None:
    try:
        operation(element.control)
    except Exception as exc:
        raise ActionFailed(
            f"The application rejected that action on {element.name!r} "
            f"({type(exc).__name__}). The element may have been replaced "
            "since the window was read — read it again before retrying.")
    _settle()


def _centre_client(element: tree.Element) -> tuple[int, int]:
    """Element centre in the client coordinates of its own window."""
    left, top, right, bottom = element.bounds
    origin = win32gui.ClientToScreen(element.hwnd, (0, 0))
    return ((left + right) // 2 - origin[0], (top + bottom) // 2 - origin[1])


# ── Coordinate actions: route 2 ──────────────────────────────────────────────

def click_point(hwnd: int, x: int, y: int, *, button: str = "left",
                double: bool = False) -> str:
    """Post a mouse click to a window at client coordinates.

    The pointer does not move: these are messages addressed to a window, not
    synthesised device input. The window need not be focused or even visible.

    The caveat worth knowing is that a posted click carries no real pointer
    position, so an application that reads `GetCursorPos` in its handler —
    rather than the coordinates in the message — will act on wherever the
    user's mouse happens to be. That is rare in Win32 controls and common in
    game engines and custom canvases.
    """
    if not win32gui.IsWindow(hwnd):
        raise ActionFailed("That window closed before the click was sent.")

    down, up = {
        "left": (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP),
        "right": (win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP),
        "middle": (win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP),
    }.get(button, (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP))
    flag = {"left": win32con.MK_LBUTTON, "right": win32con.MK_RBUTTON,
            "middle": win32con.MK_MBUTTON}.get(button, win32con.MK_LBUTTON)

    position = _lparam(x, y)
    # WM_MOUSEMOVE first: controls that track hover state ignore a button
    # press at a position they never saw the pointer reach.
    win32api.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, position)
    for _ in range(2 if double else 1):
        win32api.PostMessage(hwnd, down, flag, position)
        win32api.PostMessage(hwnd, up, 0, position)
    _settle()
    kind = "double-clicked" if double else "clicked"
    return f"{kind} {button} at ({x}, {y})"


def scroll(hwnd: int, x: int, y: int, *, clicks: int) -> str:
    """Wheel a window without the pointer being over it.

    WM_MOUSEWHEEL is unusual among mouse messages in taking SCREEN
    coordinates rather than client ones — a detail that silently scrolls the
    wrong pane in a multi-pane window if missed.
    """
    if not win32gui.IsWindow(hwnd):
        raise ActionFailed("That window closed before the scroll was sent.")
    screen_x, screen_y = win32gui.ClientToScreen(hwnd, (x, y))
    delta = int(clicks) * win32con.WHEEL_DELTA
    # Packed as an explicitly unsigned 32-bit word. Scrolling down means a
    # negative delta, and `(-360 << 16)` is a negative Python int being handed
    # to an API that wants a WPARAM — it happens to be accepted here, but the
    # masking is what makes that true rather than luck.
    wparam = ((delta & 0xFFFF) << 16) & 0xFFFFFFFF
    win32api.PostMessage(hwnd, win32con.WM_MOUSEWHEEL,
                         wparam, _lparam(screen_x, screen_y))
    _settle()
    return f"scrolled {'up' if clicks > 0 else 'down'} {abs(int(clicks))} clicks"


def type_text(hwnd: int, text: str) -> str:
    """Post characters to a window one WM_CHAR at a time.

    Prefer `set_value` when the target supports it. This route inserts at the
    application's own caret, whose position the agent does not control and
    cannot see — measured on Notepad, text posted after a `SetValue` landed at
    offset zero, in front of the existing content rather than after it. It is
    the right route for a search box that has just been clicked, and the wrong
    one for composing a document.
    """
    if not win32gui.IsWindow(hwnd):
        raise ActionFailed("That window closed before the text was sent.")

    for character in text:
        if character == "\n":
            win32api.PostMessage(hwnd, win32con.WM_CHAR, win32con.VK_RETURN, 0)
        else:
            win32api.PostMessage(hwnd, win32con.WM_CHAR, ord(character), 0)
        time.sleep(CHAR_DELAY_S)
    _settle()
    shown = text if len(text) <= 60 else text[:60] + "…"
    return f"typed {shown!r}"


# ── Keys: route 3, the one that refuses ──────────────────────────────────────

def press_keys(target: targets.Target, keys: list[str], *,
               take_focus: bool = False) -> str:
    """Send a key combination. Requires focus for anything with a modifier.

    See the module docstring for the measurements behind this. A plain key
    with no modifier can be posted safely; a combination cannot be delivered
    to an unfocused window by any mechanism Windows provides, so this either
    takes focus with the user's knowledge or declines.
    """
    names = [k.strip().lower() for k in keys if k and k.strip()]
    if not names:
        raise ActionFailed("No keys were given.")

    modifiers = [k for k in names if k in MODIFIERS]
    plain = [k for k in names if k not in MODIFIERS]
    if len(plain) != 1:
        raise ActionFailed(
            "A key press needs exactly one non-modifier key, "
            f"got {plain or 'none'}.")

    key = plain[0]
    code = VK.get(key) or (ord(key.upper()) if len(key) == 1 else None)
    if code is None:
        raise ActionFailed(
            f"{key!r} is not a key this can send. Known names: "
            + ", ".join(sorted(VK)))

    if not modifiers:
        # No modifier state to carry, so a plain post is enough.
        hwnd = target.hwnd
        scan = _u32.MapVirtualKeyW(code, 0)
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, code, 1 | (scan << 16))
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, code,
                             1 | (scan << 16) | (1 << 30) | (1 << 31))
        _settle()
        return f"pressed {key}"

    try:
        return _press_background(target, names, modifiers, code)
    except ActionFailed:
        # Attaching can be refused — most often by a window belonging to an
        # elevated process, which an unelevated one may not share input state
        # with. Falling back to the foreground is a real interruption, so it
        # happens only when it was authorised in advance.
        if take_focus:
            return _press_focused(target, names, modifiers, code)
        raise


def _press_background(target: targets.Target, names: list[str],
                      modifiers: list[str], code: int) -> str:
    """Deliver a shortcut to an unfocused window. See the module docstring.

    Nothing here blocks on the target: `AttachThreadInput`, `SetKeyboardState`
    and `PostMessage` are all asynchronous with respect to it, which is what
    keeps a wedged application from wedging the worker too. `SendMessage`
    would not have that property and is deliberately not used.
    """
    our_thread = win32api.GetCurrentThreadId()
    target_thread, _ = win32process.GetWindowThreadProcessId(target.hwnd)
    if target_thread == our_thread:
        raise ActionFailed("That window belongs to Primnox itself.")

    if not _u32.AttachThreadInput(our_thread, target_thread, True):
        raise NeedsFocus(
            f"Could not share input state with {target.label()}, so "
            f"{'+'.join(names)} cannot be delivered without taking focus. "
            "This is usual for windows owned by an elevated process. Look for "
            "a menu item or button that does the same thing — that route works "
            "in the background — or retry with take_focus.")

    codes = [VK[name] for name in modifiers]
    sided = [_SIDED[name] for name in modifiers if name in _SIDED]
    try:
        # The control the APPLICATION considers focused, which is where the
        # user left their caret. Not SetFocus: moving it would be a real
        # disturbance even though the system foreground never changes.
        sink = _u32.GetFocus() or target.hwnd

        state = (ctypes.c_ubyte * 256)()
        _u32.GetKeyboardState(ctypes.byref(state))
        for vk in codes + sided:
            state[vk] = 0x80
        if not _u32.SetKeyboardState(ctypes.byref(state)):
            raise ActionFailed(
                f"Could not set modifier state for {target.label()}.")

        try:
            scan = _u32.MapVirtualKeyW(code, 0)
            win32api.PostMessage(sink, win32con.WM_KEYDOWN, code, 1 | (scan << 16))
            win32api.PostMessage(sink, win32con.WM_KEYUP, code,
                                 1 | (scan << 16) | (1 << 30) | (1 << 31))
            _settle()
        finally:
            # The keyboard state table is SHARED while attached, so a modifier
            # left marked down is not a local bug — it makes the user's next
            # keystroke in that application a Ctrl-keystroke. Re-read first:
            # the app may have changed other keys while we held the shortcut.
            _u32.GetKeyboardState(ctypes.byref(state))
            for vk in codes + sided:
                state[vk] = 0
            _u32.SetKeyboardState(ctypes.byref(state))
    finally:
        _u32.AttachThreadInput(our_thread, target_thread, False)

    # Said without overclaiming. The keys were delivered as a shortcut; whether
    # the application acted on them is not observable from here, and a model
    # told "done" will not think to check.
    return (f"sent {'+'.join(names)} to {target.title or target.process} in the "
            "background — read the window to confirm it took effect")


def _press_focused(target: targets.Target, names: list[str],
                   modifiers: list[str], code: int) -> str:
    """The foreground path. Announced, deliberate, and restored afterwards."""
    previous = win32gui.GetForegroundWindow()
    try:
        if win32gui.IsIconic(target.hwnd):
            win32gui.ShowWindow(target.hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(target.hwnd)
    except Exception as exc:
        raise ActionFailed(
            f"Could not bring {target.label()} to the front ({exc}). Windows "
            "refuses foreground changes from a process the user has not "
            "interacted with recently.")

    time.sleep(0.15)
    if win32gui.GetForegroundWindow() != target.hwnd:
        raise ActionFailed(
            f"{target.label()} did not come to the front. The keys were NOT "
            "sent — sending them now would have delivered them to whatever "
            "window is actually focused.")

    codes = [VK[m] for m in modifiers]
    try:
        for modifier in codes:
            win32api.keybd_event(modifier, 0, 0, 0)
        win32api.keybd_event(code, 0, 0, 0)
        win32api.keybd_event(code, 0, win32con.KEYEVENTF_KEYUP, 0)
    finally:
        # Released in reverse, and in a finally: a modifier left logically
        # down survives this process and makes the user's next click a
        # ctrl-click, which is a genuinely confusing thing to leave behind.
        for modifier in reversed(codes):
            win32api.keybd_event(modifier, 0, win32con.KEYEVENTF_KEYUP, 0)

    time.sleep(0.1)
    restored = False
    if previous and previous != target.hwnd and win32gui.IsWindow(previous):
        try:
            win32gui.SetForegroundWindow(previous)
            restored = True
        except Exception:
            restored = False

    note = "" if restored else " (the window kept focus — restore it yourself)"
    return f"pressed {'+'.join(names)} in the foreground{note}"
