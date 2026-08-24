"""Semantic diffing — say what moved, not what exists.

Re-reading a window is the most common thing a model does with Computer Use
and the most wasteful. Almost nothing changes between two reads except the
part the model just acted on, and re-sending the tree to communicate that
costs the whole tree — around two thousand characters on a real Explorer
window to say that one value moved. It also buries the answer: the delta IS
what the model wanted to know; the tree is the haystack it is in.

The failure mode to guard against is not "the diff is wrong". It is "the diff
is confidently wrong about identity" — an element matched to the wrong
predecessor reports a change that never happened, or misses one that did, and
either way the model is now reasoning about a window that does not exist.

Pure structure, no windows: a diff is arithmetic on two reads and should be
checkable anywhere.
"""
from __future__ import annotations

from primnox2.computer import tree


def element(ref: str, role: str, name: str, *, value: str = "",
            enabled: bool = True, depth: int = 1,
            patterns: "tuple[str, ...]" = ("invoke",)) -> tree.Element:
    return tree.Element(ref=ref, role=role, name=name, value=value,
                        patterns=list(patterns), bounds=(0, 0, 10, 10),
                        enabled=enabled, depth=depth, hwnd=0)


def snapshot(elements: list, generation: int) -> tree.Snapshot:
    return tree.Snapshot(handle="win_1_1", title="Window",
                         elements=elements, generation=generation)


# ── The three kinds of change ───────────────────────────────────────────────

def test_a_changed_value_is_reported_with_both_sides():
    """"the display now reads 391" is useless without what it read before —
    that is the half that tells the model its action landed."""
    before = snapshot([element("e1", "Text", "Display", value="17 x 23",
                               patterns=("set_value",))], 3)
    after = snapshot([element("e1", "Text", "Display", value="391",
                              patterns=("set_value",))], 4)
    changes = tree.diff(before, after)
    assert len(changes) == 1
    described = changes[0].describe(4)
    assert "17 x 23" in described and "391" in described


def test_a_new_element_is_reported_with_what_it_can_do():
    """An added control the model cannot act on is just noise; the patterns
    are the reason it is worth mentioning at all."""
    before = snapshot([element("e1", "Button", "Save")], 1)
    after = snapshot([element("e1", "Button", "Save"),
                      element("e2", "Button", "Publish")], 2)
    described = tree.render_diff(tree.diff(before, after), generation=2)
    assert "ADDED" in described and "Publish" in described
    assert "can=invoke" in described


def test_a_vanished_element_is_named_without_a_ref():
    """A ref for something that is gone would be a handle to nothing, and a
    model handed one will try to use it."""
    before = snapshot([element("e1", "Button", "Cancel")], 1)
    after = snapshot([], 2)
    changes = tree.diff(before, after)
    assert changes[0].kind == "gone"
    assert changes[0].element is None
    assert "Cancel" in changes[0].describe(2)


def test_a_disabled_control_is_a_change_worth_reporting():
    """Enablement is usually the precondition the model is waiting on."""
    before = snapshot([element("e1", "Button", "Send", enabled=False)], 1)
    after = snapshot([element("e1", "Button", "Send", enabled=True)], 2)
    assert "enabled" in tree.diff(before, after)[0].describe(2)


# ── Identity, which is where a diff goes quietly wrong ──────────────────────

def test_elements_are_matched_by_what_they_are_not_by_their_ref():
    """Refs are positions in a walk. An element that keeps its identity while
    its ref moves must NOT read as one thing vanishing and another appearing —
    that is a two-line diff for a window in which nothing happened."""
    before = snapshot([element("e1", "Button", "Save")], 1)
    after = snapshot([element("e7", "Button", "Save")], 2)
    assert tree.diff(before, after) == []


def test_identically_named_controls_are_matched_in_order():
    """Toolbars carry several controls with the same name, and matching them
    as a set would report a change on whichever happened to be walked first."""
    before = snapshot([element("e1", "Button", "Tab", value="a",
                               patterns=("set_value",)),
                       element("e2", "Button", "Tab", value="b",
                               patterns=("set_value",))], 1)
    after = snapshot([element("e1", "Button", "Tab", value="a",
                              patterns=("set_value",)),
                      element("e2", "Button", "Tab", value="CHANGED",
                              patterns=("set_value",))], 2)
    changes = tree.diff(before, after)
    assert len(changes) == 1
    assert changes[0].was["value"] == "b"


def test_the_same_name_at_a_different_depth_is_a_different_element():
    """A menu item and the toolbar button that mirrors it share a name and are
    not the same control; treating them as one hides a real change."""
    before = snapshot([element("e1", "Button", "Save", depth=1)], 1)
    after = snapshot([element("e1", "Button", "Save", depth=4)], 2)
    kinds = sorted(c.kind for c in tree.diff(before, after))
    assert kinds == ["added", "gone"]


# ── The empty answer, which is the valuable one ─────────────────────────────

def test_nothing_changed_is_a_real_answer():
    """A model polling for a download to finish pays a whole tree per check
    without this."""
    same = [element("e1", "Button", "Save")]
    assert tree.diff(snapshot(same, 1), snapshot(list(same), 2)) == []
    assert "Nothing changed" in tree.render_diff([], against=1)


def test_there_is_no_diff_against_a_window_never_read():
    """The first read has nothing to be a delta from, and inventing one would
    report every element in the window as newly added."""
    assert tree.diff(None, snapshot([element("e1", "Button", "Save")], 1)) == []


def test_the_delta_names_which_read_it_is_against():
    """A delta with no anchor is unreadable — the model has to know which of
    its own reads this is relative to."""
    before = snapshot([element("e1", "Button", "Save")], 3)
    after = snapshot([element("e1", "Button", "Save"),
                      element("e2", "Button", "New")], 4)
    assert "read 3" in tree.render_diff(tree.diff(before, after), against=3)
