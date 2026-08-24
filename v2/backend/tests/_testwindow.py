"""A window built to be automated, for the Computer Use tests.

The tests used to drive Notepad, which was a mistake with three separate
edges. Windows 11 Notepad is a Store app: it shares one process across every
window, so tearing one down by pid takes its siblings with it; it restores
unsaved tabs on next launch, so each run left rubbish behind for the person
whose desktop it is; and a freshly launched one grabs the foreground, which
the tests then could not give back, because Windows' foreground lock refuses
`SetForegroundWindow` from a process the user has not just interacted with.
Twelve tests each launching one produced twenty-six stranded windows.

So the target is built here instead. It is a plain Win32 window with two
standard common controls as children, which is what makes it a fair test
rather than a rigged one: `EDIT` and `BUTTON` get their UI Automation
providers from Windows itself, so ValuePattern and InvokePattern behave
exactly as they do in any application that uses the common controls.

Two properties are deliberate:

  WS_EX_NOACTIVATE — the window never takes the foreground, so the tests get
  their "this is genuinely a background window" precondition by construction
  instead of by fighting the foreground lock for it.

  Focus is set on the EDIT child at creation. The background-hotkey route
  reads `GetFocus()` from the attached thread rather than calling SetFocus,
  so the target has to have an opinion about its own focus for that path to
  be exercised at all.

Run as a script; the title is argv[1] so a test can find its own window.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_CHILD, WS_VISIBLE, WS_BORDER = 0x40000000, 0x10000000, 0x00800000
WS_EX_NOACTIVATE = 0x08000000
ES_MULTILINE, ES_AUTOVSCROLL = 0x0004, 0x0040
BS_PUSHBUTTON = 0x00000000
SW_SHOWNOACTIVATE = 4
WM_DESTROY, WM_CLOSE, WM_COMMAND = 0x0002, 0x0010, 0x0111

EDIT_ID, BUTTON_ID = 1001, 1002

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)

# Declared rather than left to ctypes' defaults, which are wrong on 64-bit in
# a way that does not announce itself: an undeclared restype is `c_int`, so a
# returned HWND is truncated to 32 bits. The first version of this file left
# them off and produced a real window with no title and a handle that did not
# refer to it — every subsequent call silently addressed nothing.
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.DefWindowProcW.restype = ctypes.c_long
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
user32.SetFocus.argtypes = [wintypes.HWND]
user32.SetFocus.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.LoadCursorW.restype = wintypes.HANDLE
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


def main(title: str) -> int:
    instance = kernel32.GetModuleHandleW(None)

    def wndproc(hwnd, message, wparam, lparam):
        if message in (WM_CLOSE, WM_DESTROY):
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    proc = WNDPROC(wndproc)
    cls = WNDCLASS()
    cls.lpfnWndProc = proc
    cls.hInstance = instance
    cls.hbrBackground = 6                       # COLOR_WINDOW + 1
    cls.hCursor = user32.LoadCursorW(None, 32512)
    cls.lpszClassName = "PrimnoxTestWindow"
    if not user32.RegisterClassW(ctypes.byref(cls)):
        return 1

    hwnd = user32.CreateWindowExW(
        WS_EX_NOACTIVATE, "PrimnoxTestWindow", title, WS_OVERLAPPEDWINDOW,
        120, 120, 640, 420, None, None, instance, None)
    if not hwnd:
        return 2

    # Set again explicitly. The title is how a test finds its own window, and
    # a window that exists under the right class with the wrong name is the
    # hardest version of this to diagnose — it looks like the window was never
    # created at all.
    user32.SetWindowTextW(hwnd, title)

    edit = user32.CreateWindowExW(
        0, "EDIT", "", WS_CHILD | WS_VISIBLE | WS_BORDER | ES_MULTILINE | ES_AUTOVSCROLL,
        16, 16, 590, 280, hwnd, EDIT_ID, instance, None)
    user32.CreateWindowExW(
        0, "BUTTON", "Press Me", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
        16, 312, 160, 40, hwnd, BUTTON_ID, instance, None)

    # Shown without activation, so it is a background window from birth.
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    user32.UpdateWindow(hwnd)
    user32.SetFocus(edit)

    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "Primnox Test Window"))
