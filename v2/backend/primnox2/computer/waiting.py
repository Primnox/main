"""Waiting for the desktop — work the runtime does instead of the model.

A model that needs a dialog to appear has one move available today: read the
window, see it is not there, read it again. Every one of those reads is a full
round-trip through the provider, a tool result appended to the context, and a
model call spent deciding to wait some more. A file dialog that takes four
seconds to open can cost five model calls and five trees, and not one of them
required judgement — the answer was "not yet" every time.

None of that is the model's job. "Wait until the Save button is enabled" is a
predicate, and predicates are exactly what a runtime can evaluate. So a wait
is ONE call: the loop, the backoff, the readiness test and the give-up
condition all live here, and the model is invoked again when the answer has
actually changed.

Two things this must not do, both learned from what the polling loop got right
by accident:

  It must not burn generations. Each poll reads the tree, and if those reads
  went through the session they would advance the generation and invalidate
  every ref the model is holding — the runtime's own bookkeeping would break
  the model's plan. Polling reads are anonymous; exactly one stamped read
  happens at the end, so the model gets a fresh tree and a delta against what
  it last saw.

  It must not wait on something that has stopped existing. A window that has
  closed, or an application that has hung, will satisfy no predicate ever, and
  spending the full timeout discovering that is the difference between a wait
  and a stall. Both are checked every pass, and both cost about a tenth of a
  millisecond.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass

from . import failures, targets, tree

_user32 = ctypes.windll.user32
_user32.IsHungAppWindow.argtypes = [wintypes.HWND]
_user32.IsHungAppWindow.restype = wintypes.BOOL
_user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
_user32.SendMessageTimeoutW.restype = wintypes.LPARAM

WM_NULL = 0x0000
SMTO_ABORTIFHUNG = 0x0002

# How long to give a window to answer a message it does not have to do any
# work for. A responsive application answers WM_NULL in well under a
# millisecond — measured at 0.0-0.1 ms across five real windows — so a
# threshold this generous only fires on an application that is genuinely not
# pumping its message queue.
PING_TIMEOUT_MS = 300

# ── How an application is doing ─────────────────────────────────────────────

RESPONSIVE = "responsive"
BUSY = "busy"                    # answering, but slowly: mid-operation
NOT_RESPONDING = "not_responding"
CLOSED = "closed"


def responsiveness(target: targets.Target) -> str:
    """Whether this window's application is still pumping messages.

    Worth knowing before a wait rather than after it, because the three
    outcomes need three different responses and only one of them is "keep
    waiting". An application saving a large file is BUSY and will come back;
    one that has deadlocked is NOT_RESPONDING and will not.

    The distinction is drawn where Windows itself draws it: `IsHungAppWindow`
    is what the shell uses to decide whether to grey a window out and offer to
    close it.
    """
    import win32gui

    try:
        if not win32gui.IsWindow(target.hwnd):
            return CLOSED
    except Exception:
        return CLOSED
    try:
        if _user32.IsHungAppWindow(target.hwnd):
            return NOT_RESPONDING
    except Exception:
        pass
    result = ctypes.c_size_t(0)
    answered = _user32.SendMessageTimeoutW(
        target.hwnd, WM_NULL, 0, 0, SMTO_ABORTIFHUNG, PING_TIMEOUT_MS,
        ctypes.byref(result))
    return RESPONSIVE if answered else BUSY


# ── Predicates ──────────────────────────────────────────────────────────────

@dataclass
class Predicate:
    """A question about a window that has a yes-or-no answer.

    `description` is not decoration — it is what the timeout message says, and
    a wait that gives up has to be able to state what it was waiting for.
    Without it the model gets "timed out" and has to reconstruct its own
    intent from context, which is a turn spent on something the caller knew.
    """
    description: str
    test: object                 # (Snapshot) -> bool

    def __call__(self, snapshot: tree.Snapshot) -> bool:
        try:
            return bool(self.test(snapshot))
        except Exception:
            # A predicate that raises is answering "not yet" about a window
            # mid-change, not reporting a fault. The timeout is what decides
            # when to stop asking.
            return False


def _matches(element, name: str, role: "str | None") -> bool:
    if role and element.role != role:
        return False
    return name.lower() in (element.name or "").lower()


def element_appears(name: str, *, role: "str | None" = None) -> Predicate:
    what = f"{role} " if role else ""
    return Predicate(
        f"{what}{name!r} to appear",
        lambda s: any(_matches(e, name, role) for e in s.elements))


def element_disappears(name: str, *, role: "str | None" = None) -> Predicate:
    what = f"{role} " if role else ""
    return Predicate(
        f"{what}{name!r} to disappear",
        lambda s: not any(_matches(e, name, role) for e in s.elements))


def element_enabled(name: str, *, role: "str | None" = None) -> Predicate:
    """Enabled is usually the real precondition.

    A Save button that exists but is greyed out is the single most common
    thing worth waiting for, and it is invisible to a predicate that only asks
    whether the control is present.
    """
    what = f"{role} " if role else ""
    return Predicate(
        f"{what}{name!r} to become enabled",
        lambda s: any(_matches(e, name, role) and e.enabled for e in s.elements))


def value_contains(text: str, *, name: "str | None" = None) -> Predicate:
    def test(snapshot):
        for element in snapshot.elements:
            if name and name.lower() not in (element.name or "").lower():
                continue
            if text.lower() in (element.value or "").lower():
                return True
        return False

    where = f" in {name!r}" if name else ""
    return Predicate(f"the text {text!r} to appear{where}", test)


def settled(*, reads: int = 2) -> Predicate:
    """The window stops changing.

    The predicate for "whatever is happening has finished" when there is no
    specific control to name — a page loading, a list populating. Deliberately
    stateful: it holds the last few fingerprints and answers yes once they
    agree, which is why it is built per wait rather than shared.

    Two identical reads is the default and is genuinely enough here, because
    the poll interval backs off — by the time two consecutive reads agree,
    they are most of a second apart.
    """
    history: list = []

    def test(snapshot):
        fingerprint = [(e.role, e.name, e.value, e.enabled) for e in snapshot.elements]
        history.append(fingerprint)
        del history[:-reads]
        return len(history) == reads and all(f == history[0] for f in history)

    return Predicate(f"the window to stop changing ({reads} identical reads)", test)


# ── The wait itself ─────────────────────────────────────────────────────────

# Polling starts fast, because most waits are short and a dialog that opens in
# 200 ms should not cost a full second of latency. It then backs off, because
# a wait that has already run five seconds is unlikely to end in the next
# tenth of one, and reading the tree is not free for the application being
# read.
FIRST_POLL_S = 0.15
POLL_GROWTH = 1.5
MAX_POLL_S = 1.0

DEFAULT_TIMEOUT_S = 15.0
MAX_TIMEOUT_S = 120.0

READY = "ready"
TIMED_OUT = "timed_out"
WINDOW_CLOSED = "window_closed"
APP_HUNG = "app_hung"


@dataclass
class Outcome:
    status: str
    waited_s: float
    polls: int
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == READY

    def code(self) -> "str | None":
        """The taxonomy code for a wait that did not succeed.

        A timeout and a closed window are not the same failure: one may be
        worth waiting for again with a longer limit, the other means the thing
        being waited for cannot happen and the plan needs re-grounding.
        """
        return {
            TIMED_OUT: failures.TIMEOUT,
            WINDOW_CLOSED: failures.WINDOW_CHANGED,
            APP_HUNG: failures.APP_NOT_RESPONDING,
        }.get(self.status)

    def sentence(self, predicate: Predicate) -> str:
        if self.status == READY:
            return (f"waited {self.waited_s:.1f}s for {predicate.description} "
                    f"— it happened")
        if self.status == WINDOW_CLOSED:
            return (f"stopped waiting for {predicate.description} after "
                    f"{self.waited_s:.1f}s: the window closed, so it cannot "
                    "happen now")
        if self.status == APP_HUNG:
            return (f"stopped waiting for {predicate.description} after "
                    f"{self.waited_s:.1f}s: the application has stopped "
                    "responding. Waiting longer will not help — it needs the "
                    "user")
        return (f"waited {self.waited_s:.1f}s for {predicate.description} and "
                f"it did not happen ({self.polls} checks)")


def wait_until(target: targets.Target, predicate: Predicate, *,
               timeout_s: float = DEFAULT_TIMEOUT_S,
               hung_grace_s: float = 5.0) -> Outcome:
    """Poll until the predicate holds, the window goes, or time runs out.

    `hung_grace_s` exists because "not responding" is often exactly what is
    being waited out. An application recalculating a large spreadsheet stops
    pumping messages and Windows calls that hung; it is not, and giving up the
    instant the shell would grey the window would abandon the wait precisely
    when it was working. So a hang has to persist before it ends the wait.
    """
    timeout_s = max(0.0, min(float(timeout_s), MAX_TIMEOUT_S))
    started = time.monotonic()
    interval = FIRST_POLL_S
    polls = 0
    hung_since: "float | None" = None

    while True:
        health = responsiveness(target)
        if health == CLOSED:
            return Outcome(WINDOW_CLOSED, time.monotonic() - started, polls)
        if health == NOT_RESPONDING:
            hung_since = hung_since or time.monotonic()
            if time.monotonic() - hung_since >= hung_grace_s:
                return Outcome(APP_HUNG, time.monotonic() - started, polls)
        else:
            hung_since = None
            # Only read a window that is answering. Reading a hung one blocks
            # the worker on a provider that is not going to reply, which turns
            # a wait with a timeout into a wait without one.
            polls += 1
            try:
                if predicate(tree.read(target)):
                    return Outcome(READY, time.monotonic() - started, polls)
            except LookupError:
                # The window lost its provider mid-wait. Not fatal on its own
                # — some applications drop the tree while busy — so this is
                # another "not yet".
                pass

        waited = time.monotonic() - started
        if waited >= timeout_s:
            detail = "the application was not responding" if hung_since else ""
            return Outcome(TIMED_OUT, waited, polls, detail)
        time.sleep(min(interval, max(0.0, timeout_s - waited)))
        interval = min(interval * POLL_GROWTH, MAX_POLL_S)
