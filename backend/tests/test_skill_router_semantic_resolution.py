"""Tests for skill_router.resolve_skill_for_message() — the semantic-first
resolver core.py uses for plain chat messages.

The contract that matters: semantic routing is an *upgrade*, never a new
single point of failure. When the model is unreachable, returns nothing
usable, or names something that doesn't resolve, routing must fall back to
the old trigger-word path rather than losing the turn — an offline session
keeps exactly the routing it had before this existed.
"""
import pytest

from skills import skill_router
from skills.skill_router import resolve_skill_for_message


@pytest.fixture
def no_semantic(monkeypatch):
    """Model unavailable — classify() returns None, as it does on any
    provider failure."""
    monkeypatch.setattr("skills.semantic_router.classify", lambda text: None)


class TestSemanticResultWins:
    def test_resolves_the_skill_the_model_named(self, monkeypatch):
        monkeypatch.setattr("skills.semantic_router.classify", lambda text: "pdf")
        entry = resolve_skill_for_message("whip something up for me")
        assert entry is not None
        assert entry.name.lower() == "pdf"

    def test_trigger_words_are_not_consulted_when_semantic_matches(self, monkeypatch):
        monkeypatch.setattr("skills.semantic_router.classify", lambda text: "pdf")

        def boom(text):
            raise AssertionError("trigger-word path should not run after a semantic match")

        monkeypatch.setattr(skill_router, "get_skill_for_trigger", boom)
        assert resolve_skill_for_message("anything at all") is not None

    def test_reaches_a_claude_skill_that_has_no_trigger_words(self, monkeypatch):
        # The whole point: SKILL.md packages carry no trigger words, so
        # before semantic routing they were unreachable from chat entirely.
        monkeypatch.setattr("skills.semantic_router.classify", lambda text: "xlsx")
        entry = resolve_skill_for_message("put these numbers in a sheet")
        assert entry is not None
        assert entry.name.lower() == "xlsx"
        assert tuple(entry.trigger_words) == ()


class TestFallsBackToTriggerWords:
    def test_no_semantic_match_falls_back_to_trigger_words(self, no_semantic):
        # "explain this code" is a literal CodeSkill trigger phrase.
        entry = resolve_skill_for_message("explain this code")
        assert entry is not None
        assert entry.name == "Code Analyst"

    def test_unresolvable_semantic_name_falls_back_instead_of_failing(self, monkeypatch):
        monkeypatch.setattr("skills.semantic_router.classify", lambda text: "not_a_real_skill")
        entry = resolve_skill_for_message("explain this code")
        assert entry is not None
        assert entry.name == "Code Analyst"

    def test_returns_none_when_neither_path_matches(self, no_semantic):
        assert resolve_skill_for_message("hey, how was your weekend") is None

    def test_blank_message_returns_none_without_consulting_anything(self, monkeypatch):
        def boom(text):
            raise AssertionError("nothing should be consulted for an empty message")

        monkeypatch.setattr("skills.semantic_router.classify", boom)
        assert resolve_skill_for_message("") is None
