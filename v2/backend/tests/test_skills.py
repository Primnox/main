"""Skill loading, selection, and supporting-file access.

Selection is what decides which instructions a turn is given, and it had no
tests at all before `frontend-slides` was vendored in — at which point two
skills started claiming the same sentences and the defect was immediate.
"""
from __future__ import annotations

import pytest

from primnox2.skills import loader
from primnox2.tools import registry
from primnox2.tools import runtime  # noqa: F401 — importing is what registers the builtins


@pytest.fixture(autouse=True)
def fresh_skills():
    loader.all_skills(refresh=True)
    yield


def test_both_shipped_skills_load():
    names = set(loader.all_skills())
    assert {"frontend-slides", "themed-documents"} <= names


def test_the_always_on_index_stays_small():
    """One line per skill is charged to every turn forever, including the ones
    that will never make a document."""
    index = loader.index()
    assert "frontend-slides" in index and "themed-documents" in index
    assert len(index) < 600, f"skill index has grown to {len(index)} chars"


# ── selection ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("request_text, expected", [
    ("make me an animated html deck about mars", "frontend-slides"),
    ("create a pitch deck for investors", "frontend-slides"),
    ("convert pptx to html", "frontend-slides"),
    ("build a pptx report", "themed-documents"),
    ("write a pdf briefing", "themed-documents"),
    ("make a slide deck", "themed-documents"),
])
def test_the_more_specific_skill_wins(request_text, expected):
    chosen = loader.select(request_text)
    assert [s.name for s in chosen] == [expected], (
        f"{request_text!r} selected {[s.name for s in chosen]}")


def test_competing_skills_do_not_both_load():
    """Regression: themed-documents declares the bare word `deck`, a substring
    of every deck phrase, so it rode along on every frontend-slides request and
    the model got instructions for two different output formats at once."""
    for text in ("create a pitch deck", "build an html deck", "keynote slides"):
        assert len(loader.select(text)) <= 1, text


def test_an_unrelated_request_selects_nothing():
    assert loader.select("what is the capital of Peru") == []
    assert loader.select("") == []


def test_selection_stays_within_the_inline_budget():
    """Bodies are inlined into the prompt, so selection is prompt size."""
    for text in ("deck", "slides presentation pdf docx chart html deck"):
        total = sum(len(s.body) for s in loader.select(text))
        assert total <= loader.INLINE_BUDGET_CHARS or len(loader.select(text)) == 1


# ── supporting files ─────────────────────────────────────────────────────────
def test_frontend_slides_ships_its_stylesheet():
    """Its instructions say to include this file's full contents in every deck,
    so a deck built without it is broken by the skill's own definition."""
    skill = loader.get("frontend-slides")
    css = skill.read_asset("viewport-base.css")
    assert css and "1920" in css


def test_templates_came_across():
    skill = loader.get("frontend-slides")
    assets = skill.assets()
    designs = [a for a in assets if a.endswith("/design.md")]
    assert len(designs) >= 30, f"only {len(designs)} templates vendored"


def test_path_traversal_is_refused():
    skill = loader.get("frontend-slides")
    for attack in ("../../../../Windows/System32/drivers/etc/hosts",
                   "..\\..\\..\\loader.py",
                   "/etc/passwd"):
        assert skill.read_asset(attack) is None, attack


def test_only_declared_suffixes_are_readable():
    """The skill ships shell scripts. Reading files out of a skill directory is
    not a general file-read tool."""
    skill = loader.get("frontend-slides")
    assert skill.read_asset("scripts/export-pdf.sh") is None
    assert skill.read_asset("LICENSE") is None


# ── the tool the model actually calls ────────────────────────────────────────
def test_read_skill_lists_its_supporting_files():
    ctx = registry.ToolContext()
    out = registry.get("read_skill").handler({"name": "frontend-slides"}, ctx)
    assert out["status"] == "success"
    assert "viewport-base.css" in out["output"], \
        "the model is never told the supporting files exist"


def test_read_skill_returns_one_supporting_file():
    ctx = registry.ToolContext()
    out = registry.get("read_skill").handler(
        {"name": "frontend-slides", "file": "viewport-base.css"}, ctx)
    assert out["status"] == "success"
    assert "1920" in out["output"]


def test_read_skill_rejects_an_unknown_file_without_crashing():
    ctx = registry.ToolContext()
    out = registry.get("read_skill").handler(
        {"name": "frontend-slides", "file": "nope.css"}, ctx)
    assert out["status"] == "error"
