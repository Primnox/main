# backend/screen_reader.py
import hashlib
import re
import sys
import subprocess
import psutil
from logger import get_logger

log = get_logger("uia")

PLATFORM = sys.platform  # 'win32', 'darwin', 'linux'

# Keywords that mark a UI element as reporting an error state. Shared by every
# platform backend so error detection behaves identically across OSes.
_ERROR_KEYWORDS = ("error", "exception", "expected", "failed", "syntaxerror")

# Shapes that only occur in real compiler/runtime/test output — a hit here is
# trusted regardless of length or keyword overlap.
_CODE_ERROR_PATTERNS = [re.compile(p) for p in (
    r'[\w./\\-]+\.\w+:\d+(:\d+)?',           # file.ext:line[:col]
    r'Traceback \(most recent call last\)',
    r'^\s*at .+\(.+:\d+',                     # JS/TS stack frame
    r'line \d+, in \w+',                      # Python traceback frame
    r'TS\d{4}:',                               # TypeScript diagnostic code
    r'error\[E\d+\]',                          # Rust
    r'^\s*\w*(Error|Exception):',              # NameError:, TypeError:, etc.
    r'\d+ (failed|failing)',                   # test-runner summaries
)]

# Keyword hits that are noise, not a code error — a browser/app message, not
# something the user can fix in their editor. Checked before falling back to
# the bare keyword list.
_NOISE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r'\b404\b', r'ERR_INTERNET_DISCONNECTED', r'\bDNS\b', r'\boffline\b',
    r'deprecat', r'^warning:', r'no internet', r'connection lost',
)]

# Walk limits — kept identical across platforms so the payload shape and cost
# of a scan does not change depending on which OS the user is on.
_MAX_DEPTH = 4
_MAX_TEXTS = 50


def _empty_scan(window_title: str = "Unknown") -> dict:
    return {
        "window_title": window_title,
        "focused_text": "",
        "visible_texts": [],
        "errors": [],
        "error_records": [],
    }


def _is_code_error(text: str) -> bool:
    """Shared predicate for both the Windows UIA walk and the mac AX walk —
    they used to diverge (Windows checked keywords inline, mac called
    _find_errors), so the same on-screen text could count as an error on one
    OS and not the other. A hit on a real error *shape* (file:line, a
    traceback, a compiler diagnostic code) is trusted outright; a bare
    keyword hit ("failed", "error"...) only counts if it's not noise and
    isn't so short/long that it's obviously not an error message."""
    if any(p.search(text) for p in _CODE_ERROR_PATTERNS):
        return True
    lower = text.lower()
    if not any(kw in lower for kw in _ERROR_KEYWORDS):
        return False
    if any(p.search(text) for p in _NOISE_PATTERNS):
        return False
    return 12 <= len(text) <= 400


# Fingerprint normalization — collapses "the same error at a different line
# number/timestamp/id" down to one identity so error-streak tracking and
# proactive alerts don't re-fire on every superficial variation.
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_HEX_ID_RE = re.compile(r'\b(0x)?[0-9a-fA-F]{8,}\b')
_DIGIT_RE = re.compile(r'\d+')
_PATH_RE = re.compile(r'(?:[A-Za-z]:)?[/\\]?(?:[\w.\-]+[/\\])+([\w.\-]+)')
_WS_RE = re.compile(r'\s+')


def fingerprint(text: str) -> str:
    s = _ANSI_RE.sub('', text)
    s = _PATH_RE.sub(r'\1', s)       # absolute paths -> basename
    s = _HEX_ID_RE.sub('<id>', s)    # hex/uuid-ish tokens -> placeholder
    s = _DIGIT_RE.sub('#', s)        # remaining digits (line numbers, pids) -> #
    s = _WS_RE.sub(' ', s).strip().lower()
    return hashlib.sha1(s.encode('utf-8', errors='ignore')).hexdigest()[:12]


def _find_errors(texts) -> list:
    return [t for t in texts if _is_code_error(t)]


def _error_records(texts) -> list:
    """Same filter as _find_errors, but returns {text, fingerprint} records
    for callers that want stable error identity (see feed_manager.py)."""
    return [{"text": t, "fingerprint": fingerprint(t)} for t in texts if _is_code_error(t)]


def _get_foreground_win():
    """Windows: returns (window_title, process_name) using win32 APIs."""
    try:
        import win32gui
        import win32process
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "Unknown", "Unknown"
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid).name()
        return title or "Unknown", process or "Unknown"
    except Exception as e:
        log.error(f"Windows foreground window failed: {e}")
        return "Unknown", "Unknown"


def _get_foreground_mac_osascript():
    """macOS fallback: returns (window_title, process_name) via osascript.

    Slow (spawns a process, ~100-300ms) and itself requires Accessibility
    permission for the window title. Only used when the AX path is unavailable.
    """
    try:
        script = (
            'tell application "System Events"\n'
            '  set frontApp to first application process whose frontmost is true\n'
            '  set appName to name of frontApp\n'
            '  try\n'
            '    set windowTitle to name of front window of frontApp\n'
            '  on error\n'
            '    set windowTitle to appName\n'
            '  end try\n'
            '  return appName & "|" & windowTitle\n'
            'end tell'
        )
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split('|', 1)
            app_name = parts[0].strip()
            win_title = parts[1].strip() if len(parts) > 1 else app_name
            return win_title, app_name
        return "Unknown", "Unknown"
    except Exception as e:
        log.error(f"macOS foreground window failed: {e}")
        return "Unknown", "Unknown"


def _get_foreground_mac():
    """macOS: returns (window_title, process_name).

    Uses NSWorkspace for the frontmost app (no subprocess, sub-millisecond) and
    the Accessibility API for its focused window title. Falls back to osascript
    if pyobjc is missing.
    """
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return _get_foreground_mac_osascript()

    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return "Unknown", "Unknown"

        proc_name = str(app.localizedName() or "Unknown")
        pid = int(app.processIdentifier())

        title = _ax_window_title_for_pid(pid)
        return (title or proc_name), proc_name
    except Exception as e:
        log.error(f"macOS foreground window failed: {e}")
        return _get_foreground_mac_osascript()


def _get_foreground_linux():
    """Linux: returns (window_title, process_name) via xdotool."""
    try:
        win_id = subprocess.run(
            ['xdotool', 'getactivewindow'],
            capture_output=True, text=True, timeout=2
        ).stdout.strip()
        if not win_id:
            return "Unknown", "Unknown"
        title = subprocess.run(
            ['xdotool', 'getwindowname', win_id],
            capture_output=True, text=True, timeout=2
        ).stdout.strip()
        try:
            pid_str = subprocess.run(
                ['xdotool', 'getwindowpid', win_id],
                capture_output=True, text=True, timeout=2
            ).stdout.strip()
            process = psutil.Process(int(pid_str)).name() if pid_str else "Unknown"
        except Exception:
            process = "Unknown"
        return title or "Unknown", process
    except Exception as e:
        log.error(f"Linux foreground window failed: {e}")
        return "Unknown", "Unknown"


# ————— macOS Accessibility (AX) ————————————————————————————————————————
# Counterpart to the Windows UIAutomation walk below. Attribute names are passed
# as plain strings rather than imported constants: they are defined as strings by
# the framework and the constant symbols move between pyobjc releases.

_AX_FOCUSED_UI_ELEMENT = "AXFocusedUIElement"
_AX_FOCUSED_WINDOW = "AXFocusedWindow"
_AX_CHILDREN = "AXChildren"
_AX_TITLE = "AXTitle"
_AX_VALUE = "AXValue"
_AX_DESCRIPTION = "AXDescription"

# Per-call ceiling for AX messaging. Without this an unresponsive app blocks the
# calling thread indefinitely and takes the scan (and the feed loop) down with it.
_AX_TIMEOUT_SECONDS = 0.5


def mac_accessibility_trusted() -> bool:
    """True if this process holds macOS Accessibility permission.

    Without it every AX read returns an API-disabled error and the scan can only
    report the window title. The user grants it in
    System Settings -> Privacy & Security -> Accessibility.
    """
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _ax_get(element, attribute):
    """Read one AX attribute. Returns the value, or None on any failure."""
    try:
        from ApplicationServices import AXUIElementCopyAttributeValue
        err, value = AXUIElementCopyAttributeValue(element, attribute, None)
        if err != 0:  # kAXErrorSuccess
            return None
        return value
    except Exception:
        return None


def _ax_app_element(pid: int):
    """AX element for an application, with a messaging timeout applied."""
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementSetMessagingTimeout,
    )
    element = AXUIElementCreateApplication(pid)
    try:
        AXUIElementSetMessagingTimeout(element, _AX_TIMEOUT_SECONDS)
    except Exception:
        pass  # older pyobjc without the binding — proceed without a timeout
    return element


def _ax_window_title_for_pid(pid: int) -> str:
    """Focused window title for a pid, or '' if unreadable."""
    try:
        app = _ax_app_element(pid)
        window = _ax_get(app, _AX_FOCUSED_WINDOW)
        if window is None:
            return ""
        title = _ax_get(window, _AX_TITLE)
        return str(title) if title else ""
    except Exception:
        return ""


def _ax_text_of(element) -> str:
    """Best available human-readable text for an element."""
    for attr in (_AX_TITLE, _AX_VALUE, _AX_DESCRIPTION):
        value = _ax_get(element, attr)
        # AXValue is frequently a number, a bool, or a nested AXUIElement —
        # only plain strings are useful as visible text.
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _deep_ax_scan_mac(window_title_hint: str) -> dict:
    """macOS: deep Accessibility element walk. Mirrors _deep_uia_scan_win."""
    try:
        from AppKit import NSWorkspace
    except ImportError:
        log.warning(
            "pyobjc not installed — macOS element scan disabled. "
            "Install pyobjc-framework-Cocoa and pyobjc-framework-ApplicationServices."
        )
        return _empty_scan(window_title_hint)

    if not mac_accessibility_trusted():
        log.warning(
            "macOS Accessibility permission not granted — element scan disabled. "
            "Grant it in System Settings -> Privacy & Security -> Accessibility."
        )
        return _empty_scan(window_title_hint)

    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return _empty_scan(window_title_hint)

        pid = int(app.processIdentifier())
        app_element = _ax_app_element(pid)

        window = _ax_get(app_element, _AX_FOCUSED_WINDOW)
        root = window if window is not None else app_element

        window_title = _ax_get(root, _AX_TITLE) if window is not None else None
        window_title = str(window_title) if window_title else window_title_hint

        # Text of the currently focused control, matching the Windows
        # GetValuePattern().Value read.
        focused_text = ""
        focused = _ax_get(app_element, _AX_FOCUSED_UI_ELEMENT)
        if focused is not None:
            value = _ax_get(focused, _AX_VALUE)
            if isinstance(value, str):
                focused_text = value

        visible_texts: list[str] = []

        def walk(element, depth=0):
            if depth > _MAX_DEPTH or len(visible_texts) >= _MAX_TEXTS:
                return
            children = _ax_get(element, _AX_CHILDREN)
            if not children:
                return
            for child in children:
                if len(visible_texts) >= _MAX_TEXTS:
                    return
                try:
                    text = _ax_text_of(child)
                    if len(text) > 1:
                        visible_texts.append(text)
                    walk(child, depth + 1)
                except Exception:
                    continue

        walk(root)

        unique_texts = list(set(visible_texts))[:_MAX_TEXTS]
        errors_found = _find_errors(unique_texts)
        log.info(f"AX scan complete: {len(unique_texts)} elements, {len(errors_found)} errors.")
        return {
            "window_title": window_title,
            "focused_text": focused_text,
            "visible_texts": unique_texts,
            "errors": errors_found,
            "error_records": _error_records(unique_texts),
        }
    except Exception as e:
        log.error(f"AX scan failed: {e}")
        return {"error": str(e)}


def _deep_uia_scan_win(window_title_hint: str) -> dict:
    """Windows-only: deep UIAutomation element walk for error detection."""
    try:
        import uiautomation as auto
        import pythoncom
        import win32gui

        pythoncom.CoInitialize()
        try:
            active = auto.GetFocusedControl()
            if not active:
                try:
                    hwnd = win32gui.GetForegroundWindow()
                    if hwnd:
                        active = auto.ControlFromHandle(hwnd)
                except Exception:
                    pass

            if not active:
                return _empty_scan(window_title_hint)

            # Climb to the window root
            window_control = active
            try:
                while window_control and window_control.ControlType != auto.ControlType.WindowControl:
                    parent = window_control.GetParentControl()
                    if not parent or parent == auto.GetRootControl():
                        break
                    window_control = parent
            except Exception:
                pass

            window_title = window_control.Name if window_control else window_title_hint

            focused_text = ""
            try:
                vp = active.GetValuePattern()
                if vp:
                    focused_text = vp.Value or ""
            except Exception:
                pass

            visible_texts: list[str] = []
            errors_found: list[str] = []

            def walk(ctrl, depth=0):
                if depth > _MAX_DEPTH or len(visible_texts) >= _MAX_TEXTS:
                    return
                try:
                    children = ctrl.GetChildren()
                except Exception:
                    return
                for c in children:
                    try:
                        name = c.Name
                        if name:
                            s = name.strip()
                            if len(s) > 1:
                                visible_texts.append(s)
                                # Shared with the mac AX walk via _is_code_error —
                                # this used to be a bare keyword check duplicated
                                # inline here, which let the two platforms flag
                                # different things as "an error" for identical
                                # on-screen text.
                                if _is_code_error(s):
                                    errors_found.append(s)
                        walk(c, depth + 1)
                    except Exception:
                        continue

            walk(window_control)
            unique_errors = list(set(errors_found))
            log.info(f"UIA scan complete: {len(visible_texts)} elements, {len(unique_errors)} errors.")
            return {
                "window_title": window_title,
                "focused_text": focused_text,
                "visible_texts": list(set(visible_texts))[:_MAX_TEXTS],
                "errors": unique_errors,
                "error_records": [{"text": t, "fingerprint": fingerprint(t)} for t in unique_errors],
            }
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        log.error(f"UIA scan failed: {e}")
        return {"error": str(e)}


def read_screen() -> dict:
    """Return active window info, including a deep element walk where supported.

    Windows uses UIAutomation, macOS uses the Accessibility API. Linux has no
    element walk and returns the window title only.
    """
    log.debug("Starting screen scan...")

    if PLATFORM == 'win32':
        window_title, _ = _get_foreground_win()
        return _deep_uia_scan_win(window_title)

    elif PLATFORM == 'darwin':
        window_title, _ = _get_foreground_mac()
        return _deep_ax_scan_mac(window_title)

    else:  # linux — no element walk available
        window_title, _ = _get_foreground_linux()
        return _empty_scan(window_title)


if __name__ == "__main__":
    import json
    if PLATFORM == 'darwin':
        print(f"Accessibility trusted: {mac_accessibility_trusted()}")
    print(json.dumps(read_screen(), indent=2))
