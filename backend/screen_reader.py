# backend/screen_reader.py
import sys
import subprocess
import psutil
from logger import get_logger

log = get_logger("uia")

PLATFORM = sys.platform  # 'win32', 'darwin', 'linux'


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


def _get_foreground_mac():
    """macOS: returns (window_title, process_name) via osascript."""
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
                return {
                    "window_title": window_title_hint,
                    "focused_text": "",
                    "visible_texts": [],
                    "errors": [],
                }

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
                if depth > 4 or len(visible_texts) >= 50:
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
                                if any(kw in s.lower() for kw in ["error", "exception", "expected", "failed", "syntaxerror"]):
                                    errors_found.append(s)
                        walk(c, depth + 1)
                    except Exception:
                        continue

            walk(window_control)
            log.info(f"UIA scan complete: {len(visible_texts)} elements, {len(errors_found)} errors.")
            return {
                "window_title": window_title,
                "focused_text": focused_text,
                "visible_texts": list(set(visible_texts))[:50],
                "errors": list(set(errors_found)),
            }
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        log.error(f"UIA scan failed: {e}")
        return {"error": str(e)}


def read_screen() -> dict:
    """Return active window info. Deep UIA element walk on Windows only."""
    log.debug("Starting screen scan...")

    if PLATFORM == 'win32':
        window_title, _ = _get_foreground_win()
        return _deep_uia_scan_win(window_title)

    elif PLATFORM == 'darwin':
        window_title, _ = _get_foreground_mac()

    else:  # linux
        window_title, _ = _get_foreground_linux()

    # Mac / Linux: no deep element walk — return basic window title only
    return {
        "window_title": window_title,
        "focused_text": "",
        "visible_texts": [],
        "errors": [],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(read_screen(), indent=2))
