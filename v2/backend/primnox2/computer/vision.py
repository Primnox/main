"""Window capture — a picture of one window, not of the screen.

Capturing the *screen* would be the easy version and the wrong one. A desktop
screenshot picks up every other window the user has open — messages, mail,
whatever is behind the target — and hands all of it to a model that was
granted authority over exactly one application. Capture here goes through
`PrintWindow`, which asks a specific window to draw itself into a bitmap the
agent owns. Occluded windows still render. The desktop behind them does not.

Two things about this were measured on this machine rather than assumed, and
both changed the implementation:

  PW_RENDERFULLCONTENT (0x2) is MANDATORY, not an optimisation. Without it
  every DWM-composited window — anything on Electron, WinUI, or a GPU
  renderer — returns a bitmap that is uniformly black while PrintWindow
  still reports success. Measured on Claude (Electron) and Windows Terminal:
  plain PrintWindow returned 1 and an all-zero image; with the flag, the same
  window returned real pixels. A caller trusting the return code alone gets a
  black rectangle and no error.

  Some windows cannot be captured at all. Task Manager returned PrintWindow=0
  and an empty bitmap: it runs elevated, and an unelevated process is not
  permitted to make it draw. This is not a bug to route around — it is the OS
  refusing, and the honest response is to say so.

Which is why every capture is checked for content before it is returned. A
blank result is reported as a failure with its likely cause, because the one
outcome worse than no screenshot is a black one described as a screenshot:
the model reads an empty image as an empty window and acts on that.
"""
from __future__ import annotations

import ctypes
import io

import win32con
import win32gui
import win32ui
from PIL import Image

from . import targets

PW_RENDERFULLCONTENT = 0x00000002

# How much luminance spread a capture needs before it counts as an image.
# A window genuinely showing a flat colour is rare; a failed PrintWindow is
# exactly uniform. Eight levels is comfortably above sensor-free bitmap noise
# and far below anything with content in it.
MIN_LUMINANCE_SPREAD = 8

# Captures are downscaled before they reach a model. A 4K window is 8M pixels
# of mostly-empty chrome, and vision tokens are the most expensive thing in
# the pipeline. The accessibility tree carries the precise structure anyway
# (`tree.py`); the image is for the parts a tree cannot express.
MAX_EDGE = 1600


class CaptureError(RuntimeError):
    """The window could not be drawn. The message is written for the model."""


def capture(target: targets.Target) -> Image.Image:
    """Render one window to an image, or raise with a reason worth reading."""
    if target.minimized:
        raise CaptureError(
            f"{target.label()} is minimized, so there is nothing to capture. "
            "A minimized window has no rendered surface at all — this is not "
            "a permissions problem and retrying will not help. Read its "
            "accessibility tree instead, which works while minimized, or ask "
            "the user to restore the window.")

    left, top, right, bottom = win32gui.GetClientRect(target.hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise CaptureError(f"{target.label()} has no drawable area.")

    window_dc = mfc_dc = save_dc = bitmap = None
    try:
        window_dc = win32gui.GetWindowDC(target.hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(window_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)

        drawn = ctypes.windll.user32.PrintWindow(
            target.hwnd, save_dc.GetSafeHdc(), PW_RENDERFULLCONTENT)

        info = bitmap.GetInfo()
        image = Image.frombuffer(
            "RGB", (info["bmWidth"], info["bmHeight"]),
            bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    finally:
        # Every one of these leaks a GDI object on failure, and the per-process
        # GDI handle limit (10,000) is reachable in a long session that
        # captures on a loop. Released in reverse order of acquisition.
        if bitmap is not None:
            win32gui.DeleteObject(bitmap.GetHandle())
        if save_dc is not None:
            save_dc.DeleteDC()
        if mfc_dc is not None:
            mfc_dc.DeleteDC()
        if window_dc is not None:
            win32gui.ReleaseDC(target.hwnd, window_dc)

    if not _has_content(image):
        raise CaptureError(_blank_reason(target, bool(drawn)))

    image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    return image


def _has_content(image: Image.Image) -> bool:
    low, high = image.convert("L").getextrema()
    return (high - low) >= MIN_LUMINANCE_SPREAD


def _blank_reason(target: targets.Target, drawn: bool) -> str:
    """Say which of the two failures happened, because the answers differ.

    PrintWindow returning 0 means the OS refused outright — an elevated or
    protected process. Returning 1 with a blank bitmap means it drew nothing,
    which is what a window does before it has painted, or when it renders
    through an overlay the compositor owns (full-screen games, hardware video).
    Retrying helps in the second case and never in the first.
    """
    if not drawn:
        return (
            f"Windows refused to render {target.label()}. This happens with "
            "elevated or protected processes — Task Manager, UAC dialogs, "
            "anti-cheat-protected games — which an unelevated program is not "
            "allowed to capture. Do not retry; it will fail identically. Its "
            "accessibility tree may still be readable.")
    return (
        f"{target.label()} rendered an empty image. The window drew nothing, "
        "which usually means it has not painted yet, or it renders through a "
        "hardware overlay that PrintWindow cannot see (full-screen games, "
        "some video players). Its accessibility tree is the reliable way to "
        "read this window.")


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def client_origin(target: targets.Target) -> tuple[int, int]:
    """Screen coordinates of the window's client area top-left.

    Everything the accessibility tree reports is in screen coordinates;
    everything posted to a window as a mouse message is in client
    coordinates. This is the conversion between them, and getting it wrong is
    the single easiest way to click the wrong thing — the offset is the title
    bar and border, so a naive implementation lands roughly one menu row high.
    """
    return win32gui.ClientToScreen(target.hwnd, (0, 0))
