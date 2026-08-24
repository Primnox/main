"""Cached reads — same tree, fewer round-trips.

The uncached walk asks the target application one question per property and
one per pattern, and every question is a cross-process call served on that
application's UI thread. A UIA cache request names everything wanted up front
and answers a whole level in one call.

The only thing that makes this an optimisation rather than a rewrite is that
it returns the SAME tree. A faster read that quietly drops a button, or that
reports a capability the other path does not, is a correctness regression
wearing a benchmark as a disguise — so that is what most of this file checks.

Measured on this machine while building it, uncached against cached:

    Claude (Electron)      30 els     40 ms  ->  16 ms
    Ollama                167 els    230 ms  ->  63 ms
    Opera (GX Corner)     221 els    310 ms  ->  83 ms

Three things had to be right before those numbers meant anything, and each
was wrong first:

  The cache request's TreeFilter must be RawView, because `uiautomation`
  hard-codes RawViewWalker. ControlView returned 89 elements against 221.

  The request's TreeScope must be ELEMENT, not CHILDREN. It says what to cache
  relative to each match — Children cached the children of every match and not
  the matches, so every element was found and none of it had been fetched.

  Caching must be per LEVEL, not the whole subtree. Claude's raw subtree is
  3,428 nodes; caching all of it to surface thirty made the read slower than
  not caching at all.
"""
from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Computer Use is Windows-only")

from primnox2.computer import tree
from test_computer_use import window            # noqa: F401  (fixture)


def fingerprint(snapshot):
    return [(e.role, e.name, tuple(e.patterns), e.enabled, e.depth)
            for e in snapshot.elements]


# ── Equivalence, which is the whole argument ────────────────────────────────

def test_the_cached_read_returns_the_same_tree(window):              # noqa: F811
    uncached = tree.read(window, cached=False)
    cached = tree.read(window, cached=True)
    assert fingerprint(cached) == fingerprint(uncached)


def test_the_cached_read_is_the_default(window):                     # noqa: F811
    """The fast path has to be what actually runs, or the measurement is about
    code nobody reaches."""
    assert fingerprint(tree.read(window)) == \
        fingerprint(tree.read(window, cached=True))


def test_a_cache_failure_falls_back_rather_than_failing(monkeypatch, window):  # noqa: F811
    """A cache request is an optimisation. Losing it must cost speed and
    nothing else — a read that fails because the fast path was unavailable
    would be a worse outcome than never having built it."""
    monkeypatch.setattr(tree, "_cached_root", lambda hwnd: None)
    snapshot = tree.read(window)
    assert snapshot.elements, "the fallback walk returned nothing"


def test_a_cached_element_can_still_be_operated(window):             # noqa: F811
    """Reads come from the cache; ACTIONS must not. Operating a control
    through a snapshot taken milliseconds ago works right up until a button
    moves, and then it does the wrong thing quietly."""
    from primnox2.computer import actions

    snapshot = tree.read(window, cached=True)
    field = tree.find_text_target(snapshot)
    assert field is not None
    actions.set_value(field, "through the cache")
    assert tree.live_value(field) == "through the cache"


def test_live_value_reads_through_a_cached_element(window):          # noqa: F811
    """Verification asks the control, not the record of the control — that has
    to remain true when the record came from a cache."""
    from primnox2.computer import actions

    field = tree.find_text_target(tree.read(window, cached=True))
    assert field is not None
    actions.set_value(field, "first")
    assert tree.live_value(field) == "first"
    actions.set_value(field, "second")
    assert tree.live_value(field) == "second", "the cached value was returned"


# ── Capability discovery, which the cache work exposed as broken ────────────

class _WrapperWithoutGetters:
    """A control shaped like `uiautomation.PaneControl`: it has `GetPattern`
    and none of the per-pattern getter methods."""

    def __init__(self, supported):
        self._supported = supported

    def GetPattern(self, pattern_id):
        return object() if pattern_id in self._supported else None


def test_capability_is_asked_of_uia_not_of_the_wrapper_class():
    """The bug this replaced: `getattr(control, "GetInvokePattern", None)`
    skipped the pattern when the attribute was missing — and `uiautomation`
    defines those getters on control-type SUBCLASSES, so a `PaneControl` that
    genuinely supports Invoke reported no patterns, was not actionable, and
    could make a window with working buttons read as blind."""
    import uiautomation as auto

    control = _WrapperWithoutGetters({auto.PatternId.InvokePattern})
    assert not hasattr(control, "GetInvokePattern")
    assert tree._pattern_names(control) == ["invoke"]


def test_an_unsupported_pattern_is_a_no_not_an_error():
    control = _WrapperWithoutGetters(set())
    assert tree._pattern_names(control) == []


def test_scroll_item_is_not_treated_as_a_capability():
    """It is supported by nearly every element inside a scrollable container —
    88 of 89 on a real browser window — because it describes where a thing
    sits, not what it does. Reporting it would make every element actionable
    and the actionable filter would stop filtering."""
    assert "scroll_to" not in [action for _, action in tree.INTERESTING_PATTERNS]
    assert "ScrollItem" not in tree._PATTERN_IDS


def test_the_cache_request_asks_for_every_pattern_it_reports():
    """The cached path answers capability from what the request fetched. A
    pattern in INTERESTING_PATTERNS with no id would silently never be
    reported by the fast path and always by the slow one."""
    for pattern, _ in tree.INTERESTING_PATTERNS:
        assert pattern in tree._PATTERN_IDS, f"{pattern} is never cached"


# ── The browser activation grace period ────────────────────────────────────

def test_a_browser_window_earns_its_grace_period_once():
    """Chromium builds its accessibility tree on demand, so the first read of
    a browser is the request rather than the answer, and waiting 1.2s before
    asking again is right. Waiting EVERY time is not.

    Found by the KPI harness, not by a test: a browser window whose page
    genuinely has nothing actionable never stops looking like a stub, so it
    re-earned the grace period on every read — 1,216 ms per read of a
    seven-element Opera window, forever. p95 read latency dropped to 83 ms
    when this became once-per-window.
    """
    tree._activated.pop(4242, None)
    assert tree._claim_activation(4242) is True
    assert tree._claim_activation(4242) is False


def test_the_grace_period_is_re_earned_after_the_memory_expires():
    """Windows recycles HWNDs. A number that named a browser ten minutes ago
    can name a different window now, and that one deserves its own chance."""
    import time as _time

    tree._activated[4243] = _time.time() - tree.ACTIVATION_MEMORY_S - 1
    assert tree._claim_activation(4243) is True


def test_actions_can_reach_every_cached_pattern():
    """`actions.py` asks for patterns by method name. A name the adapter does
    not answer would raise AttributeError at the moment of acting."""
    for pattern in tree._PATTERN_IDS:
        assert f"Get{pattern}Pattern" in tree._PATTERN_METHODS
