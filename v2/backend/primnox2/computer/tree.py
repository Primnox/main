"""Accessibility tree — reading a window as structure instead of pixels.

This is the half of computer use that actually works. A screenshot tells a
model where things appear to be; the UI Automation tree tells it what they
are, what they are called, whether they are enabled, and — the part that
matters most — which of them can be operated directly. Measured on Windows 11
Notepad while a full-screen game held the foreground, the tree read back
completely: menu items, toolbar buttons with their accelerators in the name,
the document and its text.

The design consequence of that measurement is in `Element.patterns`. A UIA
*control pattern* is a first-class way to operate a control — Invoke a
button, SetValue an edit, Toggle a checkbox — and unlike a synthesised click
it is delivered to the control itself, so it works on an unfocused window and
needs no coordinates. Modern apps make this mandatory rather than merely
nicer: every toolbar button in Notepad reports `NativeWindowHandle == 0`,
because WinUI and XAML controls are painted by their host and have no window
of their own. There is nothing for a mouse message to be posted to. Patterns
are the only way in.

Two traps in the `uiautomation` library, both hit while building this:

  Controls are lazy. A control object re-finds itself by search criteria on
  every property access, and the default timeout is ten seconds — so reading
  `.Name` on a control that has since vanished blocks the worker for ten
  seconds and then raises. The tree is therefore walked ONCE, eagerly, into
  plain dataclasses, and the live COM objects are cached alongside by ref.
  Nothing outside this module ever touches a lazy control.

  Control type is not capability. Notepad's text area is a `DocumentControl`,
  not the `EditControl` a reasonable person would search for. Searching by
  type finds nothing; searching by *pattern* finds it immediately. Elements
  are therefore described and selected by what they can do.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import uiautomation as auto
from comtypes import COMError

from . import targets

# Every property read goes through the lazy re-find described above. One
# second is long enough for a control that exists and short enough that a
# control that does not costs a beat rather than a stall.
SEARCH_TIMEOUT_S = 1.0

# The tree of a rich application is enormous — a browser reports tens of
# thousands of nodes — and all of it would land in the context window. These
# are the two limits that keep a read useful rather than merely complete.
MAX_DEPTH = 12
MAX_ELEMENTS = 400

# A browser's tree is the live DOM, not a fixed set of controls, so it is both
# much deeper and much wider than a native window's — a page nests its useful
# controls well past where a native application would have finished, and a
# results list can carry hundreds of links worth reading. Applying the native
# limits to a browser truncates the page before reaching the content, which
# reads to a model as an empty page rather than as a truncated one.
BROWSER_MAX_DEPTH = 24
BROWSER_MAX_ELEMENTS = 800

# How long to let a browser build its accessibility tree before reading again.
# Chromium enables accessibility on demand and populates it in the renderer,
# so the first read is the request rather than the answer.
BROWSER_ACTIVATION_S = 1.2

# Patterns worth reporting, in the order a model should prefer them. Invoke
# before Toggle before Value is not arbitrary: it is cheapest-and-most-direct
# first, so a button that reports several is described by the one that most
# plainly means "operate this".
INTERESTING_PATTERNS = (
    ("Invoke", "invoke"),
    ("Toggle", "toggle"),
    ("Value", "set_value"),
    ("ExpandCollapse", "expand"),
    ("SelectionItem", "select"),
    ("Text", "read_text"),
)

# ScrollItem is deliberately NOT in that list, and the reason is measured.
# Nearly every element inside a scrollable container supports it — 88 of 89 on
# a real browser window — because "can be scrolled into view" is a property of
# where a thing sits, not of what it does. Reporting it would put `can=` on
# essentially every node, and since `actionable()` is "enabled and has at
# least one pattern", it would make every element in the window actionable and
# the filter that keeps a read readable would stop filtering anything.
#
# It was invisible until the cache work, because the old capability check
# asked the wrapper class rather than UIA, and no wrapper class defines a
# ScrollItem getter. A true capability nobody could see.

# Control types that are pure decoration. Keeping them multiplies the size of
# a read without adding anything actionable — a WinUI toolbar spends most of
# its nodes on icon glyphs whose entire content is a private-use codepoint.
NOISE_TYPES = frozenset({"SeparatorControl", "ThumbControl", "ImageControl"})

_lock = threading.RLock()
_initialised = False

# Which browser windows have already been given the activation grace period,
# and when. Time-boxed rather than permanent because Windows recycles HWNDs:
# a number that named a browser an hour ago can name a different window now,
# and that window deserves its own one chance.
_activated: dict[int, float] = {}
ACTIVATION_MEMORY_S = 600.0


def _claim_activation(hwnd: int) -> bool:
    """True the first time this window is worth waiting for, then False."""
    now = time.time()
    with _lock:
        for stale in [h for h, at in _activated.items()
                      if now - at > ACTIVATION_MEMORY_S]:
            _activated.pop(stale, None)
        if hwnd in _activated:
            return False
        _activated[hwnd] = now
        return True


def _ensure_uia() -> None:
    """UIA is COM, and COM is per-thread.

    Turn workers are pool threads, so a session started on one thread can
    easily be read from another. `uiautomation` initialises COM lazily on
    first use per thread, which is correct; what is not safe is the library's
    global search timeout, a module-level value that must be set before any
    control is touched.
    """
    global _initialised
    with _lock:
        if not _initialised:
            auto.SetGlobalSearchTimeout(SEARCH_TIMEOUT_S)
            # The library writes `@AutomationLog.txt` into the current working
            # directory whenever a lookup times out, and prints the same lines
            # to stdout. A control that has vanished is an ordinary outcome
            # here — the walk skips it — so this is not error reporting, it is
            # a file appearing in whatever directory Primnox happened to be
            # started from. `''` disables the file; the timeouts still surface
            # as exceptions where they are actually handled.
            auto.Logger.SetLogFile("")
            _initialised = True


@dataclass
class Element:
    """One node, flattened. Everything here was read eagerly."""
    ref: str                       # stable within one read, e.g. "e12"
    role: str                      # UIA control type, minus the "Control"
    name: str
    value: str
    patterns: list[str]            # actions this element genuinely supports
    bounds: tuple[int, int, int, int]
    enabled: bool
    depth: int
    hwnd: int                      # 0 for XAML/WinUI elements — see docstring
    control: object = field(repr=False, default=None)   # live COM handle

    def actionable(self) -> bool:
        return self.enabled and bool(self.patterns)

    def qualified(self, generation: "int | None") -> str:
        """The ref as the model should see it: `e12@481`.

        The generation is not decoration. A bare `e12` means "the twelfth node
        of some read", and there is no way to tell which read — so a ref quoted
        back after the window changed lands on whatever is twelfth NOW. That is
        a silent misclick, and it is the failure mode with the worst shape: it
        succeeds, it verifies, and it is wrong. Stamping the read the ref came
        from turns it into a detectable one.
        """
        return self.ref if generation is None else f"{self.ref}@{generation}"

    def describe(self, generation: "int | None" = None) -> str:
        """One line, written to be read by a model choosing what to click."""
        label = self.name or self.value or "(unlabelled)"
        if len(label) > 70:
            label = label[:70] + "…"
        parts = [f"[{self.qualified(generation)}]", self.role, repr(label)]
        if self.patterns:
            parts.append("can=" + ",".join(self.patterns))
        if not self.enabled:
            parts.append("DISABLED")
        return "  " * min(self.depth, 8) + " ".join(parts)

    def to_json(self) -> dict:
        return {
            "ref": self.ref, "role": self.role, "name": self.name,
            "value": self.value, "patterns": self.patterns,
            "bounds": list(self.bounds), "enabled": self.enabled,
            "depth": self.depth,
        }


@dataclass
class Snapshot:
    """One read of one window. Refs are only meaningful against this read."""
    handle: str
    title: str
    elements: list[Element]
    truncated: bool = False
    # Which read this is, counted per session. 0 means "unstamped" — a bare
    # `tree.read` outside a session, where there is nothing to be stale
    # against and the qualified form would be a promise nobody can keep.
    generation: int = 0

    def by_ref(self, ref: str) -> "Element | None":
        return next((e for e in self.elements if e.ref == ref), None)

    def actionable(self) -> list[Element]:
        return [e for e in self.elements if e.actionable()]

    @property
    def blind(self) -> bool:
        """True when this window cannot be operated by element at all.

        Games and custom-drawn applications ship no UI Automation provider,
        so the tree is empty or decorative. Measured on a running title: the
        read returned zero elements. That is not a failure to report as an
        error — the window is still there and still clickable — but it does
        mean the caller has to fall back to coordinates, and it has to KNOW
        that rather than concluding the window is empty.
        """
        return not any(e.actionable() for e in self.elements)

    def render(self, *, only_actionable: bool = False) -> str:
        rows = self.actionable() if only_actionable else self.elements
        stamp = self.generation or None
        lines = [e.describe(stamp) for e in rows]
        if self.truncated:
            lines.append(
                f"… tree truncated at {len(self.elements)} elements. Narrow the read "
                "to a region, or act on what is listed.")
        if not lines:
            return "(this window exposes no accessible elements)"
        return "\n".join(lines)


def _pattern_names(control) -> list[str]:
    """Which patterns this control really supports — asked of UIA, not of the
    wrapper class.

    This used to do `getattr(control, "GetInvokePattern", None)` and skip the
    pattern when the attribute was missing. That reads as defensive and is
    silently lossy, because `uiautomation` defines those getters on
    control-type SUBCLASSES: `ButtonControl` has `GetInvokePattern`,
    `PaneControl` has no pattern getters at all. So capability was being
    decided by control type — the precise mistake this module's docstring
    opens by warning about, made one layer further down where nothing showed
    it.

    Measured on the Claude window: four elements supporting Invoke, one
    supporting Value and one supporting Text came back with NO patterns, so
    they were not actionable, so `blind` was prepared to call a window with
    working buttons unreadable.

    `GetPattern` goes to `IUIAutomationElement::GetCurrentPattern`, which is
    UIA answering about the element rather than Python answering about its own
    class. The question is still "does an object come back" — several WinUI
    controls advertise a pattern and then hand back None — which is why this
    asks for the pattern rather than reading the IsXxxPatternAvailable flag.
    """
    supported = []
    for pattern, action in INTERESTING_PATTERNS:
        try:
            if control.GetPattern(_PATTERN_IDS[pattern]) is not None:
                supported.append(action)
        except Exception:
            # An unsupported pattern raises COMError, which is a normal
            # answer of "no", not a failure of the read.
            continue
    return supported


def _read_value(control, patterns: list[str]) -> str:
    if "set_value" not in patterns:
        return ""
    try:
        return (control.GetValuePattern().Value or "")[:400]
    except Exception:
        return ""


def live_value(element: "Element") -> "str | None":
    """Re-read an element's value from the live control, now.

    `Element.value` is a snapshot taken during the walk, so comparing a write
    against it compares the write to what was true beforehand — which will
    agree with itself whether or not anything happened. Verification has to ask
    the control, not the record of the control.

    None means "could not be read", which is different from "" meaning "read,
    and empty". A verifier must not treat the first as evidence of anything.
    """
    if "set_value" not in element.patterns or element.control is None:
        return None
    try:
        return element.control.GetValuePattern().Value or ""
    except Exception:
        return None


def live_toggle(element: "Element") -> "str | None":
    """The live ToggleState, as a string, or None if it cannot be read."""
    if "toggle" not in element.patterns or element.control is None:
        return None
    try:
        return str(element.control.GetTogglePattern().ToggleState)
    except Exception:
        return None


# ── Cached reads ────────────────────────────────────────────────────────────
#
# The walk above asks the provider one question at a time, and every question
# is a cross-process call into the application being read. Per element that is
# five property reads plus one call per pattern tried — around a dozen — so a
# 221-element window costs roughly 2,600 round-trips, and the cost is paid in
# the target application's UI thread, which is why a busy app makes a read
# slow rather than the other way round.
#
# UIA has a first-class answer: a cache request names everything wanted up
# front, and `BuildUpdatedCache` fetches the whole subtree in ONE call. The
# properties then read out of local memory.
#
# The elements come back in AutomationElementMode_Full, which matters: mode
# None is cheaper still and hands back inert elements that cannot be operated,
# which would make every read a read-only read. The saving here is in the
# number of round-trips, not in giving up the ability to act.

VALUE_VALUE_PROPERTY = 30045          # UIA_ValueValuePropertyId
TREE_SCOPE_ELEMENT = 1                # TreeScope_Element
TREE_SCOPE_CHILDREN = 2               # TreeScope_Children

_CACHED_PROPERTIES = (
    auto.PropertyId.NameProperty,
    auto.PropertyId.ControlTypeProperty,
    auto.PropertyId.BoundingRectangleProperty,
    auto.PropertyId.IsEnabledProperty,
    auto.PropertyId.NativeWindowHandleProperty,
    VALUE_VALUE_PROPERTY,
)

# The pattern ids behind INTERESTING_PATTERNS, in the same order, so a cached
# node answers "what can this do" from memory instead of a call per pattern.
_PATTERN_IDS = {
    "Invoke": auto.PatternId.InvokePattern,
    "Toggle": auto.PatternId.TogglePattern,
    "Value": auto.PatternId.ValuePattern,
    "ExpandCollapse": auto.PatternId.ExpandCollapsePattern,
    "SelectionItem": auto.PatternId.SelectionItemPattern,
    "Text": auto.PatternId.TextPattern,
}

# How `actions.py` asks for a pattern. Kept as a mapping rather than written
# out as seven methods because the list must stay in step with
# INTERESTING_PATTERNS, and two lists that must agree should be one list.
_PATTERN_METHODS = {f"Get{name}Pattern": pattern_id
                    for name, pattern_id in _PATTERN_IDS.items()}


class _Cached:
    """One node of a cached walk, wearing the interface the walk already uses.

    The point of the adapter is that `visit` does not change. Every filtering
    rule — noise types, depth, element cap, the browser retry — keeps working
    on exactly the same code path, so switching a read to the cache cannot
    quietly change WHICH elements come back, only how fast they arrive. A
    faster read that returns a different tree would not be an optimisation.

    Reads are cached; ACTIONS are live. `GetInvokePattern` and friends fetch
    the current pattern, because operating a control through a snapshot taken
    some milliseconds ago is the sort of shortcut that works until a button
    moves. Verification is live for the same reason — see `live_value`.
    """
    __slots__ = ("_element", "_request", "_client")

    def __init__(self, element, request, client) -> None:
        self._element = element
        self._request = request
        self._client = client

    # ── Cached property reads ───────────────────────────────────────────
    @property
    def ControlTypeName(self) -> str:
        return auto.ControlTypeNames.get(self._element.CachedControlType, "")

    @property
    def Name(self) -> str:
        return self._element.CachedName or ""

    @property
    def BoundingRectangle(self):
        return self._element.CachedBoundingRectangle

    @property
    def IsEnabled(self) -> bool:
        return bool(self._element.CachedIsEnabled)

    @property
    def NativeWindowHandle(self) -> int:
        return self._element.CachedNativeWindowHandle or 0

    def GetChildren(self) -> list:
        """This node's children, with every property and pattern already in
        hand, in ONE call.

        Per level rather than per subtree, and that is the whole design.
        `BuildUpdatedCache` with TreeScope_Subtree fetches everything beneath
        the window whatever depth limit the caller intends to apply — measured
        on the Claude window, that made a read of thirty elements take 139 ms
        against 43 ms uncached, because an Electron window's raw subtree runs
        to thousands of nodes and all of them were being cached to surface
        thirty.

        Asking level by level keeps the caps meaningful: nothing is fetched
        below the depth the walk actually descends to, and the round-trip
        count still drops from about a dozen per element to one per node.
        """
        try:
            found = self._element.FindAllBuildCache(
                TREE_SCOPE_CHILDREN, self._client.RawViewCondition,
                self._request)
            count = found.Length
        except (ValueError, AttributeError, COMError):
            # A leaf hands back a NULL array and comtypes raises on touching
            # it. That is the ordinary end of a branch, not an error.
            return []
        return [_Cached(found.GetElement(i), self._request, self._client)
                for i in range(count)]

    def cached_patterns(self) -> list[str]:
        """What this element can do, answered from the cache.

        Same question as `_pattern_names` asks — does an object come back —
        which matters, because several WinUI controls advertise a pattern and
        then hand back nothing. Asking for the object rather than the
        availability flag is what makes the two paths agree.
        """
        supported = []
        for pattern, action in INTERESTING_PATTERNS:
            try:
                if self._element.GetCachedPattern(_PATTERN_IDS[pattern]):
                    supported.append(action)
            except (ValueError, COMError, KeyError):
                continue
        return supported

    def cached_value(self) -> str:
        try:
            value = self._element.GetCachedPropertyValue(VALUE_VALUE_PROPERTY)
        except (ValueError, COMError):
            return ""
        return (value or "")[:400] if isinstance(value, str) else ""

    # ── Live patterns, for acting and for verifying ─────────────────────
    def __getattr__(self, name: str):
        pattern_id = _PATTERN_METHODS.get(name)
        if pattern_id is None:
            raise AttributeError(name)

        def getter():
            raw = self._element.GetCurrentPattern(pattern_id)
            return auto.CreatePattern(pattern_id, raw) if raw else None

        return getter


def _cached_root(hwnd: int) -> "_Cached | None":
    """The window, ready to be walked one cached level at a time."""
    try:
        client = _uia_client()
        request = client.CreateCacheRequest()
        request.AutomationElementMode = 1          # Full: still operable
        # ELEMENT, not CHILDREN, and the difference is not obvious: the
        # request's TreeScope says what to cache RELATIVE TO each element the
        # search returns. Children would cache the children of every match and
        # not the matches themselves, so every property read came back
        # "The parameter is incorrect" — the element was found, and nothing
        # about it had been fetched. The SEARCH scope is the separate argument
        # to FindAllBuildCache.
        request.TreeScope = TREE_SCOPE_ELEMENT
        # RawView, matching what the uncached walk sees. `uiautomation`
        # hard-codes `RawViewWalker` in its automation client (the
        # ControlViewWalker line is commented out in the library), so a cache
        # request built on ControlViewCondition returns a DIFFERENT tree -
        # measured on a browser window, 89 elements against 221, missing real
        # controls including the title bar's Restore button. Faster and
        # different is not an optimisation.
        request.TreeFilter = client.RawViewCondition
        for prop in _CACHED_PROPERTIES:
            request.AddProperty(prop)
        for pattern_id in _PATTERN_IDS.values():
            request.AddPattern(pattern_id)
        return _Cached(client.ElementFromHandle(hwnd), request, client)
    except Exception:
        # Any failure here is a performance disappointment, never a broken
        # read: the caller falls back to the uncached walk, which is the path
        # that has always worked.
        return None


def _uia_client():
    from uiautomation import uiautomation as _internal
    return _internal._AutomationClient.instance().IUIAutomation


def read(target: targets.Target, *, max_depth: "int | None" = None,
         max_elements: "int | None" = None, cached: bool = True) -> Snapshot:
    """Walk one window's tree eagerly and return it flattened.

    Works on a window that is unfocused, occluded, or minimized — the tree is
    a structural query, not a rendering one, which is exactly why it is the
    reliable half of this subsystem.
    """
    _ensure_uia()
    if max_depth is None:
        max_depth = BROWSER_MAX_DEPTH if target.is_browser else MAX_DEPTH
    if max_elements is None:
        max_elements = BROWSER_MAX_ELEMENTS if target.is_browser else MAX_ELEMENTS

    root = _cached_root(target.hwnd) if cached else None
    if root is None:
        root = auto.ControlFromHandle(target.hwnd)
    if root is None:
        raise LookupError(
            f"{target.label()} exposes no accessibility information at all. "
            "Some games and custom-drawn applications implement no UI "
            "Automation provider; there is nothing to read and no way to "
            "operate them by element. A screenshot is the only view of this "
            "window.")

    elements: list[Element] = []
    truncated = False

    def walk() -> None:
        nonlocal elements, truncated
        elements, truncated = [], False
        visit(root, 0)

    def visit(control, depth: int) -> None:
        nonlocal truncated
        if depth > max_depth or truncated:
            return
        try:
            children = control.GetChildren()
        except Exception:
            # A control can be destroyed mid-walk — a menu closing, a page
            # navigating. Losing that subtree is correct; failing the whole
            # read because one node went away is not.
            return
        for child in children:
            if len(elements) >= max_elements:
                truncated = True
                return
            try:
                role = child.ControlTypeName.replace("Control", "")
                if role + "Control" in NOISE_TYPES:
                    continue
                if isinstance(child, _Cached):
                    patterns = child.cached_patterns()
                    value = child.cached_value() if "set_value" in patterns else ""
                else:
                    patterns = _pattern_names(child)
                    value = _read_value(child, patterns)
                rect = child.BoundingRectangle
                element = Element(
                    ref=f"e{len(elements) + 1}",
                    role=role,
                    name=(child.Name or "")[:200],
                    value=value,
                    patterns=patterns,
                    bounds=(rect.left, rect.top, rect.right, rect.bottom),
                    enabled=bool(child.IsEnabled),
                    depth=depth,
                    hwnd=child.NativeWindowHandle or 0,
                    control=child,
                )
            except Exception:
                continue
            elements.append(element)
            visit(child, depth + 1)

    walk()

    # Chromium ships an accessibility STUB until a client asks for the real
    # thing, and then builds it asynchronously in the renderer. Measured on a
    # browser showing a YouTube page: the first read returned 7 elements and
    # nothing operable, which `blind` correctly reported and which was
    # nonetheless wrong about the window — the page was full of links.
    #
    # The first walk is itself the request that switches it on, so the fix is
    # to give the renderer a moment and ask again. Done only for browsers, and
    # only when the first answer was a stub, so a genuinely tree-less window
    # (a game) still costs one read rather than two.
    #
    # Paid ONCE per window, not once per read, and that distinction was
    # invisible until the KPI harness measured it: a browser window whose page
    # genuinely has nothing actionable — a blank tab, a background window —
    # never stops looking like a stub, so it re-earned the grace period on
    # every single read. Measured at 1,216 ms per read of a seven-element
    # Opera window, forever.
    #
    # Once is also the correct number on the merits. The sleep exists to let
    # the renderer answer a request that the first walk itself made, and
    # accessibility STAYS on once switched on. A page that loads content later
    # is read normally on the next pass, with no waiting needed.
    if (target.is_browser and not any(e.actionable() for e in elements)
            and _claim_activation(target.hwnd)):
        time.sleep(BROWSER_ACTIVATION_S)
        walk()

    return Snapshot(handle=target.handle, title=target.title,
                    elements=elements, truncated=truncated)


@dataclass
class Change:
    """One difference between two reads of the same window."""
    kind: str                      # "added" | "gone" | "changed"
    element: "Element | None"      # the element as it is NOW; None when gone
    was: dict = field(default_factory=dict)
    label: str = ""                # how to name it when there is no element

    def describe(self, generation: "int | None" = None) -> str:
        if self.kind == "gone":
            return f"  GONE    {self.label}"
        assert self.element is not None
        head = f"[{self.element.qualified(generation)}] {self.element.role}"
        name = self.element.name or self.element.value or "(unlabelled)"
        if self.kind == "added":
            can = (" can=" + ",".join(self.element.patterns)
                   if self.element.patterns else "")
            return f"  ADDED   {head} {name!r}{can}"
        parts = []
        for attribute, now in (("value", self.element.value),
                               ("name", self.element.name),
                               ("enabled", self.element.enabled)):
            if attribute in self.was:
                parts.append(f"{attribute} {self.was[attribute]!r} -> {now!r}")
        return f"  CHANGED {head} {name!r}: " + "; ".join(parts)


def _identity(element: "Element") -> tuple:
    """What makes an element the same element across two reads.

    Deliberately NOT the ref, which is a position in a walk, and not the
    value, which is the thing most likely to be what changed. Role, name and
    ordinal is the same identity `selector_for` uses, so an element that
    survives a re-read is recognised by the diff and by a replayed workflow in
    the same terms.
    """
    return (element.role, element.name, element.depth)


def diff(before: "Snapshot | None", after: "Snapshot") -> "list[Change]":
    """What changed between two reads, and nothing else.

    A window's tree is mostly furniture. Re-reading Notepad after typing one
    word sends back every menu item, every toolbar button and the document, to
    say that one value moved — and the model then has to find the difference
    itself, in a context window that just grew by the size of the whole tree.
    On the second read of a real Explorer window that is around two thousand
    characters to communicate one fact.

    So the interesting output is the delta. It is also more USEFUL than the
    tree: "the display now reads 391" is the answer to what the model was
    doing, whereas the full tree is the haystack the answer is in. This is the
    single cheapest thing available for small local models, which spend most
    of their attention budget re-reading things they already knew.
    """
    if before is None:
        return []
    old = {}
    for element in before.elements:
        old.setdefault(_identity(element), []).append(element)
    seen: dict[tuple, int] = {}
    changes: list[Change] = []
    matched: set[int] = set()

    for element in after.elements:
        key = _identity(element)
        index = seen.get(key, 0)
        seen[key] = index + 1
        candidates = old.get(key) or []
        if index >= len(candidates):
            changes.append(Change("added", element))
            continue
        previous = candidates[index]
        matched.add(id(previous))
        was = {}
        if previous.value != element.value:
            was["value"] = previous.value
        if previous.enabled != element.enabled:
            was["enabled"] = previous.enabled
        if was:
            changes.append(Change("changed", element, was))

    for element in before.elements:
        if id(element) not in matched:
            name = element.name or element.value or "(unlabelled)"
            changes.append(Change("gone", None,
                                  label=f"{element.role} {name!r}"))
    return changes


def render_diff(changes: "list[Change]", *, generation: "int | None" = None,
                against: "int | None" = None) -> str:
    """The delta as the model reads it."""
    if not changes:
        return (f"Nothing changed since read {against}."
                if against else "Nothing changed.")
    header = (f"Changes since read {against}:" if against else "Changes:")
    return "\n".join([header] + [c.describe(generation) for c in changes])


def parse_ref(text: str) -> "tuple[str, int | None]":
    """Split `e12@481` into its ref and the read it was taken from.

    Tolerant on purpose. A model that has only ever seen `e12` in an older
    conversation, or that drops the suffix while copying, is not making an
    error worth refusing — it is making a claim with less information in it,
    and the right response is to resolve it against the current read and say
    so. What must never happen is the reverse: a stamped ref silently treated
    as unstamped, because that discards the only evidence that it is stale.
    """
    raw = (text or "").strip()
    ref, _, stamp = raw.partition("@")
    ref = ref.strip().lstrip("[").rstrip("]")
    if not stamp:
        return ref, None
    try:
        return ref, int(stamp.strip().rstrip("]"))
    except ValueError:
        # `e12@banana` is a malformed stamp, not a missing one. Dropping it
        # would promote a nonsense ref to an unstamped one and act on it.
        raise ValueError(
            f"{raw!r} is not an element ref. Refs look like 'e12@481' — the "
            "number after @ is the read they came from.")


def selector_for(snapshot: Snapshot, element: Element) -> dict:
    """A way of naming an element that survives the window being re-read.

    Refs cannot do this. `e12` means "the twelfth node of that particular
    walk", so it is meaningless the moment a dialog opens or a list scrolls —
    which is exactly the situation a recorded workflow is replayed into.

    Role plus name plus ordinal is what a person would use: "the second
    button called Save". The ordinal matters more than it looks like it
    should — toolbars routinely carry several identically named controls, and
    without it a replay picks whichever happens to be walked first.
    """
    same = [e for e in snapshot.elements
            if e.role == element.role and e.name == element.name]
    return {
        "role": element.role,
        "name": element.name,
        "ordinal": same.index(element) if element in same else 0,
        # Kept for the message shown when resolution fails, never for matching:
        # a ref that no longer means anything is still a useful thing to say.
        "recorded_ref": element.ref,
    }


def resolve_selector(snapshot: Snapshot, selector: dict) -> "Element | None":
    """Find the element a selector names in a fresh read, or nothing."""
    matches = [e for e in snapshot.elements
               if e.role == selector.get("role") and e.name == selector.get("name")]
    if not matches:
        return None
    ordinal = selector.get("ordinal") or 0
    # Falling back to the first match when the ordinal is out of range is
    # deliberate: a toolbar that lost one of three identical buttons should
    # still replay against the ones that remain, rather than failing outright.
    return matches[ordinal] if ordinal < len(matches) else matches[0]


# Roles that expose ValuePattern and are emphatically not somewhere a person
# asked to type. Measured in Paint: the largest value-accepting element in the
# window is the Opacity slider, so ranking purely by capability and size picked
# it, and a type_into with no ref would have moved a tool setting while
# reporting that it had typed.
NOT_TEXT_ROLES = frozenset({"Slider", "ScrollBar", "ProgressBar", "Spinner"})

# Roles that ARE a text surface, and the only ones this returns. Anything else
# that merely accepts a value was tried as a fallback and dropped: with sliders
# excluded, Paint's next-largest value-accepting element is a ComboBox named
# "Zoom", which is no more a place to type HELLO than the slider was. A window
# with no text surface should say so.
TEXT_ROLES = ("Document", "Edit")


def find_text_target(snapshot: Snapshot) -> "Element | None":
    """The element text should be typed into, if the window has an obvious one.

    Capability first: anything that accepts a value is a candidate, whatever its
    control type. Selecting by control type alone is what fails on Notepad,
    whose editor is a `DocumentControl`.

    Capability alone is not enough, though, and the failure it produces is the
    bad kind — silent and wrong rather than loud and wrong. Sliders and
    scrollbars expose ValuePattern too, so "largest element accepting a value"
    selected Paint's Opacity slider; the only genuinely text-shaped controls in
    that window are two `Edit` controls named "Zoom" that report zero area and
    lose a size contest to it. The corrected order is: discard what cannot be a
    text surface, discard what has no area on screen, prefer text-shaped roles,
    and only then take the largest.

    Returning None is a perfectly good answer. A window with no text surface
    — Paint is one — should say so, because the caller's refusal names the
    route that does work (read the window, pass a ref) and a wrong guess does
    not.
    """
    def area(element: Element) -> int:
        left, top, right, bottom = element.bounds
        return max(0, right - left) * max(0, bottom - top)

    candidates = [e for e in snapshot.elements
                  if "set_value" in e.patterns
                  and e.enabled
                  and e.role not in NOT_TEXT_ROLES
                  and area(e) > 0]
    if not candidates:
        return None

    text_shaped = [e for e in candidates if e.role in TEXT_ROLES]
    return max(text_shaped, key=area) if text_shaped else None
