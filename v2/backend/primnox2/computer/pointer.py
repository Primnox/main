"""The agent's cursor — a second pointer you can watch, and cannot bump into.

Windows has one system cursor and will not be given another. What it will be
given is a window that looks like one, which is exactly how Microsoft Teams
shows a remote participant's pointer during Give Control: the host keeps their
own cursor, and the controller's is painted on top with a name beside it. This
is that, for Primnox.

The point is not decoration. Everything else in this package works invisibly —
`actions.py` delivers through control patterns and posted messages, so nothing
moves and nothing flashes — and the cost of that is a user who cannot tell the
difference between an agent working carefully in their spreadsheet and an
agent doing nothing at all. The timeline in the UI says what happened; this
says WHERE, while it happens, in the window it is happening to.

Three window styles carry the whole safety argument, and each is load-bearing:

  WS_EX_TRANSPARENT — the window is invisible to hit-testing, so every click
  and every hover passes straight through to whatever is underneath. This is
  what makes the overlay incapable of stealing a click even in principle: it
  is not that it declines to handle the mouse, it is that the mouse never
  reaches it.

  WS_EX_NOACTIVATE — it can never take the foreground, so it cannot interrupt
  typing, and it never appears in Alt-Tab.

  WS_EX_LAYERED with per-pixel alpha — the glyph is drawn antialiased over
  whatever is behind it, with no rectangle of background around it.

It also runs on its own thread with its own message pump, because a window
belongs to the thread that created it: pumped from a turn worker, the pointer
would freeze for exactly as long as the worker was busy doing the thing the
pointer exists to show.
"""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

from PIL import Image, ImageChops, ImageDraw

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_POPUP = 0x80000000
ULW_ALPHA = 0x00000002
AC_SRC_OVER, AC_SRC_ALPHA = 0x00, 0x01
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010

# How long the pointer takes to travel between two targets, and it is the real
# arrival time rather than a nominal one. Long enough to be followed by eye,
# short enough not to pace the work — the agent is not waiting for it, the
# glide runs on the overlay's own thread while the action proceeds. Instant
# teleporting was tried first and reads as flicker rather than as movement:
# the eye needs the path to understand that the thing at the new place is the
# same thing that was at the old one.
#
# The first version moved a FRACTION of the remaining distance each frame,
# which is the obvious way to write an ease-out and is wrong in a way that
# does not show up by watching: a constant fraction of a shrinking gap never
# reaches zero, so the pointer crept for ~0.8s to cover a 0.22s glide and
# arrived only when the per-frame step rounded below a pixel. The curve is now
# a function of elapsed TIME, so GLIDE_S is what it says, arrival is exact,
# and a frame the pump happens to miss costs smoothness rather than accuracy.
GLIDE_S = 0.22
FRAMES = 14                      # frames per glide, i.e. how often _tick runs

# How long the pointer lingers after the last action before fading out. A
# pointer that vanishes the instant an action completes leaves the user
# looking at the place where something just happened with no marker on it.
LINGER_S = 2.5

WIDTH, HEIGHT = 132, 46          # canvas: arrow plus its label
HOTSPOT = (6, 4)                 # where the arrow tip sits within the canvas

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


# Declared, never left to ctypes' defaults. An undeclared restype is a 32-bit
# int, which silently truncates every HWND and HDC on a 64-bit build — the
# same trap that produced a real window with a handle pointing at nothing
# while building the test harness.
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.DefWindowProcW.restype = ctypes.c_long
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.RegisterClassW.restype = wintypes.ATOM
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

# The ARGUMENT side of the same trap, and it bites harder than the return
# side because it is silent right up until it is fatal. An undeclared
# argument is passed as a 32-bit int, so a call taking a handle works for as
# long as the handles the process happens to be issued stay small, and raises
# `OverflowError: int too long to convert` the first time one does not. That
# is a bug that passes review, passes a smoke test, and fails on a machine
# that has been up for a week — so every handle-taking call used here is
# declared, including the teardown ones nobody watches.
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
    ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
    ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]


def _render(label: str, colour: tuple[int, int, int]) -> Image.Image:
    """Draw the pointer once. RGBA, premultiplied at blit time.

    A plain arrow with a name beside it, because that is the shape everyone
    already reads as "somebody else's cursor" — the Teams convention, and
    Google Docs', and every multiplayer editor since. Inventing a new visual
    language for this would only mean the user has to learn one.
    """
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # The label chip first, so the arrow sits on top of its corner.
    text = label[:14]
    chip_left, chip_top = 18, 14
    chip_width = 12 + 7 * len(text)
    draw.rounded_rectangle(
        [chip_left, chip_top, chip_left + chip_width, chip_top + 20],
        radius=9, fill=(*colour, 235))
    draw.text((chip_left + 7, chip_top + 5), text, fill=(255, 255, 255, 255))

    # The arrow: a filled polygon with a light outline, so it stays visible
    # against both a white document and a dark editor.
    arrow = [(6, 4), (6, 26), (12, 20), (16, 29), (20, 27), (16, 18), (24, 18)]
    draw.polygon(arrow, fill=(*colour, 255))
    draw.line(arrow + [arrow[0]], fill=(255, 255, 255, 230), width=1)
    return image


class Pointer:
    """One overlay window, living on its own thread."""

    def __init__(self, label: str = "Primnox",
                 colour: tuple[int, int, int] = (99, 102, 241)) -> None:
        self.label = label
        self.colour = colour
        self._hwnd = 0
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._target: "tuple[int, int] | None" = None
        self._position: "tuple[int, int] | None" = None
        self._origin: "tuple[int, int] | None" = None
        self._departed_at = 0.0
        self._hide_at = 0.0
        self._lock = threading.RLock()
        self._thread: "threading.Thread | None" = None
        self._failed = ""
        self._memory_dc = None
        self._bitmap = None
        self._previous_bitmap = None

    # ── Public surface ──────────────────────────────────────────────────────

    def start(self) -> bool:
        """Bring the overlay up. False if this machine will not have it.

        Never raises. A pointer that cannot be drawn is a missing convenience,
        and taking down a control session over it would trade the feature for
        the decoration.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._hwnd != 0
            self._stop.clear()
            self._ready.clear()
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="primnox-pointer")
            self._thread.start()
        self._ready.wait(timeout=3.0)
        return self._hwnd != 0

    def move_to(self, x: int, y: int) -> None:
        """Send the pointer to a screen coordinate and keep it there."""
        if self._hwnd == 0:
            return
        with self._lock:
            self._target = (int(x), int(y))
            # The journey restarts from wherever the pointer actually IS, not
            # from where the last one was headed — retargeting mid-flight is
            # the normal case when actions land faster than the glide.
            self._origin = self._position
            self._departed_at = time.time()
            self._hide_at = time.time() + LINGER_S

    def hide(self) -> None:
        """Off screen, and forget where it was.

        Forgetting matters: the position is the origin of the next glide, so
        keeping it would make the first action of the NEXT session fly in from
        the last window of the previous one — a movement across the screen
        that corresponds to nothing that happened. Cleared here, the next
        appearance is instant and in the right place.
        """
        if self._hwnd == 0:
            return
        with self._lock:
            self._target = None
            self._position = None
            self._origin = None
            self._hide_at = 0.0
        user32.ShowWindow(self._hwnd, SW_HIDE)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    @property
    def failed(self) -> str:
        return self._failed

    # ── The thread ──────────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            self._create()
        except Exception as exc:                        # pragma: no cover
            self._failed = f"{type(exc).__name__}: {exc}"
            self._release_surface()
            if self._hwnd:
                user32.DestroyWindow(self._hwnd)
                self._hwnd = 0
            self._ready.set()
            return
        self._ready.set()

        message = wintypes.MSG()
        while not self._stop.is_set():
            # Non-blocking pump: PeekMessage rather than GetMessage, because
            # GetMessage sleeps until a message arrives and this window
            # receives almost none — the glide has to run whether or not
            # Windows has anything to say.
            while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
            self._tick()
            time.sleep(GLIDE_S / FRAMES)

        self._release_surface()
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)
            self._hwnd = 0

    def _create(self) -> None:
        instance = kernel32.GetModuleHandleW(None)

        def proc(hwnd, message, wparam, lparam):
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        self._proc = WNDPROC(proc)         # kept alive; a GC'd wndproc crashes
        cls = WNDCLASS()
        cls.lpfnWndProc = self._proc
        cls.hInstance = instance
        cls.lpszClassName = "PrimnoxPointer"
        user32.RegisterClassW(ctypes.byref(cls))       # already-registered is fine

        self._hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
            | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
            "PrimnoxPointer", "Primnox pointer", WS_POPUP,
            0, 0, WIDTH, HEIGHT, None, None, instance, None)
        if not self._hwnd:
            raise OSError("could not create the pointer window")

        self._build_surface()
        self._blit(0, 0)
        user32.SetWindowPos(self._hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _tick(self) -> None:
        """One frame: glide toward the target, or fade out after lingering."""
        with self._lock:
            target, position = self._target, self._position
            origin, departed, hide_at = (self._origin, self._departed_at,
                                         self._hide_at)

        if target is None:
            return

        if hide_at and time.time() > hide_at:
            self.hide()
            return

        if position is None or origin is None:
            # First appearance, or the first move after a fade: no glide, or
            # it flies in from the corner of the screen, which reads as a bug
            # rather than as movement.
            self._place(target)
            return
        if position == target:
            return

        progress = min(1.0, (time.time() - departed) / GLIDE_S)
        eased = 1 - (1 - progress) ** 3       # cubic ease-out: fast, then settles
        self._place((round(origin[0] + (target[0] - origin[0]) * eased),
                     round(origin[1] + (target[1] - origin[1]) * eased)))

    def _place(self, point: tuple[int, int]) -> None:
        with self._lock:
            self._position = point
        self._blit(point[0] - HOTSPOT[0], point[1] - HOTSPOT[1])
        user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)

    def _build_surface(self) -> None:
        """Draw the glyph into a DIB once, and keep it for the window's life.

        UpdateLayeredWindow wants premultiplied BGRA in a bottom-up DIB, and
        gets all three of those wrong by default — Pillow hands over top-down
        straight-alpha RGBA, so the conversion is explicit here rather than
        left to look like it worked. Unpremultiplied pixels render as a bright
        halo around the glyph, which is subtle enough to ship by accident.

        Doing it here rather than in `_blit` is the difference between paying
        for it once and paying for it fourteen times a glide: the pixels never
        change, only the coordinate the bitmap is stamped at, so a per-frame
        premultiply over six thousand pixels — plus a DIB and a DC allocated
        and freed each time — would be spent reproducing the image already on
        screen. On the one thread whose whole job is to move smoothly, that is
        the wrong place to be doing arithmetic.
        """
        image = _render(self.label, self.colour)
        # Per-band rather than per-pixel: ImageChops.multiply IS (v * a) // 255
        # over a whole band at C speed, and it avoids reaching for numpy, which
        # nothing else in this package imports. Verified byte-identical to the
        # per-pixel form over all 65536 value/alpha pairs — worth checking,
        # because a rounding difference here shows up as a halo at some alphas
        # and not others.
        red, green, blue, alpha = image.split()
        premultiplied = Image.merge("RGBA", (
            ImageChops.multiply(red, alpha), ImageChops.multiply(green, alpha),
            ImageChops.multiply(blue, alpha), alpha))
        # BGRA and bottom-up: the two things a DIB wants and Pillow does not
        # give by default. Asking tobytes for the byte order directly, rather
        # than smuggling B into the red channel and relying on nobody reading
        # the image afterwards.
        raw = premultiplied.transpose(Image.FLIP_TOP_BOTTOM).tobytes("raw", "BGRA")

        # Compatible with the display rather than with a borrowed screen DC:
        # GetDC(None) hands out of a small system-wide cache, and holding one
        # for the life of the process is how a machine runs out of them.
        self._memory_dc = gdi32.CreateCompatibleDC(None)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = WIDTH
        info.bmiHeader.biHeight = HEIGHT
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0            # BI_RGB
        bits = ctypes.c_void_p()
        self._bitmap = gdi32.CreateDIBSection(
            self._memory_dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
        if not self._bitmap:
            raise OSError("could not allocate the pointer bitmap")
        self._previous_bitmap = gdi32.SelectObject(self._memory_dc, self._bitmap)
        ctypes.memmove(bits, raw, len(raw))

    def _release_surface(self) -> None:
        """Give the GDI objects back. Runs on the pointer's own thread."""
        if self._memory_dc:
            if self._previous_bitmap:
                gdi32.SelectObject(self._memory_dc, self._previous_bitmap)
            if self._bitmap:
                gdi32.DeleteObject(self._bitmap)
            gdi32.DeleteDC(self._memory_dc)
        self._memory_dc = self._bitmap = self._previous_bitmap = None

    def _blit(self, left: int, top: int) -> None:
        """Stamp the cached glyph at a screen point."""
        if not self._memory_dc:
            return
        size = wintypes.SIZE(WIDTH, HEIGHT)
        source = wintypes.POINT(0, 0)
        destination = wintypes.POINT(int(left), int(top))
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        # hdcDst NULL: the call wants it only to learn the screen's colour
        # format, and passing None asks Windows for the same default screen DC
        # this would otherwise borrow and have to remember to release.
        user32.UpdateLayeredWindow(
            self._hwnd, None, ctypes.byref(destination), ctypes.byref(size),
            self._memory_dc, ctypes.byref(source), 0, ctypes.byref(blend),
            ULW_ALPHA)


# One pointer for the process. Several agents pointing at once would be
# several overlays fighting over the same screen, and the thing being shown —
# "here is where Primnox is working" — has only one answer at a time.
_pointer: "Pointer | None" = None
_pointer_lock = threading.RLock()

# Why a machine that cannot host the overlay is remembered rather than retried:
# `acquire` is called on the path of every action, and a Pointer that fails to
# start has already spent a thread and a three-second wait finding that out.
# Retrying per click would turn one missing convenience into a per-action
# stall. A service session or a locked workstation does not become able to
# draw halfway through a task — and if the process outlives whatever made it
# impossible, `shutdown` clears this and the next session tries again.
_unavailable = ""


def acquire() -> "Pointer | None":
    """The shared pointer, started on first use. None if it cannot run."""
    global _pointer, _unavailable
    with _pointer_lock:
        if _pointer is None and not _unavailable:
            candidate = Pointer()
            if candidate.start():
                _pointer = candidate
            else:
                _unavailable = candidate.failed or "the overlay would not start"
        return _pointer


def unavailable() -> str:
    """Why there is no pointer, if there is none. Empty when all is well."""
    return _unavailable


def release() -> None:
    """Take the pointer off screen. Kept alive for the next session."""
    with _pointer_lock:
        if _pointer is not None:
            _pointer.hide()


def shutdown() -> None:
    global _pointer, _unavailable
    with _pointer_lock:
        if _pointer is not None:
            _pointer.stop()
            _pointer = None
        _unavailable = ""
