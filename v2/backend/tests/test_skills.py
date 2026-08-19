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
    assert "design-routes" in index, "both slide paths should be discoverable"
    # Seven skills, 709 chars. Two paths to slides: code generation (35-40% on
    # 0.5B) via themed-documents, and design routing (70-85% target) via
    # design-routes. The index cost is still an order of magnitude under
    # inlining the bodies.
    assert len(index) < 800, f"skill index has grown to {len(index)} chars"
    for line in index.splitlines():
        if line.startswith("- "):
            assert len(line) < 110, f"a description sprawled: {line}"


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


@pytest.mark.parametrize("request_text, expected", [
    ("what is the average of column B in this csv", "data-analysis"),
    ("analyse this spreadsheet for a correlation", "data-analysis"),
    ("build me a small app to split a bill", "interactive-apps"),
    ("draw a flowchart of the pipeline", "interactive-apps"),
    ("remember that I work on Windows", "memory-and-recall"),
    ("search the knowledge graph for ingest_bytes", "memory-and-recall"),
    ("run the tests", "running-commands"),
    ("can you do git status", "running-commands"),
])
def test_the_added_skills_are_reachable(request_text, expected):
    """A skill nothing selects is a skill that exists only in the index, where
    it is pure cost."""
    assert [s.name for s in loader.select(request_text)] == [expected]


def test_no_two_skills_claim_the_same_trigger():
    """Identical triggers tie on specificity, so both bodies load and the model
    is handed two sets of instructions for one sentence. Overlap has to be by
    length — `deck` vs `html deck` — never by collision."""
    seen: dict[str, str] = {}
    for skill in loader.all_skills().values():
        for trigger in skill.triggers:
            assert trigger not in seen, (
                f"{trigger!r} is claimed by both {seen[trigger]} and {skill.name}")
            seen[trigger] = skill.name


def test_an_unrelated_request_selects_nothing():
    assert loader.select("what is the capital of Peru") == []
    assert loader.select("") == []
    assert loader.select("explain recursion in two sentences") == []


def test_selection_stays_within_the_inline_budget():
    """Bodies are inlined into the prompt, so selection is prompt size."""
    for text in ("deck", "slides presentation pdf docx chart html deck"):
        total = sum(len(s.body) for s in loader.select(text))
        assert total <= loader.INLINE_BUDGET_CHARS or len(loader.select(text)) == 1


def test_the_deck_body_stays_small_enough_for_a_small_model():
    """Length is the lever, not wording. Measured on qwen2.5:0.5b, 20 runs each
    through the real system prompt: a 4,967-char body produced 0 decks; trimmed
    to 1,262 chars produces 7-8 decks (35-40% success). Everything past the
    opening template belongs in a supporting file where only turns that need it
    pay for it."""
    body = loader.get("themed-documents").body
    assert len(body) < 1400, f"themed-documents body is {len(body)} chars"


def test_themed_documents_ships_what_its_body_points_at():
    skill = loader.get("themed-documents")
    assert set(skill.assets()) >= {"layouts.md", "pdf-and-word.md"}
    assert skill.read_asset("layouts.md")
    assert skill.read_asset("pdf-and-word.md")


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
