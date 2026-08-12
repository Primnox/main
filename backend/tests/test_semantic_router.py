"""Tests for semantic_router.py — model-based skill routing.

The router replaced substring matching against hardcoded trigger phrases,
which failed both ways: "whip up a deck for standup" matched nothing and
fell through to plain chat, while an incidental "calendar" anywhere in a
sentence hijacked the turn.

Every test here mocks brain.think — a router test that reached a real
provider would be slow, non-deterministic, and would spend the user's
tokens. What's actually under test is the reply-validation logic: a model
that hallucinates a skill name, hedges between two, or fails outright must
degrade to "no match" rather than routing somewhere wrong.
"""
import pytest

import brain
from skills import semantic_router
from skills.semantic_router import classify, _match_name, _catalog


CATALOG = [
    {"name": "pdf", "description": "Anything involving PDF files."},
    {"name": "pptx", "description": "Slide decks and presentations."},
    {"name": "calendar", "description": "Schedule and upcoming events."},
]


@pytest.fixture
def fixed_catalog(monkeypatch):
    monkeypatch.setattr(semantic_router, "_catalog", lambda: CATALOG)


def _reply(text: str):
    """A think()-shaped success response."""
    return {"choices": [{"message": {"content": text}}]}


def _mock_think(monkeypatch, response):
    calls = []

    def fake_think(prompt, **kwargs):
        calls.append((prompt, kwargs))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(brain, "think", fake_think)
    return calls


class TestClassifyHappyPath:
    def test_bare_skill_name_routes(self, monkeypatch, fixed_catalog):
        _mock_think(monkeypatch, _reply("pdf"))
        assert classify("generate me a pdf") == "pdf"

    def test_reply_is_case_and_whitespace_insensitive(self, monkeypatch, fixed_catalog):
        _mock_think(monkeypatch, _reply("  PPTX \n"))
        assert classify("make a deck") == "pptx"

    def test_wrapped_reply_still_resolves(self, monkeypatch, fixed_catalog):
        # Small local models often ignore "output only the name".
        _mock_think(monkeypatch, _reply("Skill: `pdf`."))
        assert classify("turn this into a pdf") == "pdf"

    def test_catalog_and_message_both_reach_the_model(self, monkeypatch, fixed_catalog):
        calls = _mock_think(monkeypatch, _reply("pdf"))
        classify("build me a report")

        prompt, kwargs = calls[0]
        assert "pdf" in prompt and "pptx" in prompt
        assert "build me a report" in prompt
        assert "system_override" in kwargs


class TestClassifyRefusesBadAnswers:
    def test_none_reply_means_no_match(self, monkeypatch, fixed_catalog):
        _mock_think(monkeypatch, _reply("NONE"))
        assert classify("hey how's it going") is None

    def test_hallucinated_skill_name_is_rejected(self, monkeypatch, fixed_catalog):
        _mock_think(monkeypatch, _reply("video_editor"))
        assert classify("edit my video") is None

    def test_ambiguous_reply_naming_two_skills_is_rejected(self, monkeypatch, fixed_catalog):
        # Routing to whichever happened to be mentioned first would be a
        # coin flip; no-match lets the trigger-word fallback have a turn.
        _mock_think(monkeypatch, _reply("either pdf or pptx would work"))
        assert classify("make me a document") is None

    def test_empty_reply_is_rejected(self, monkeypatch, fixed_catalog):
        _mock_think(monkeypatch, _reply(""))
        assert classify("do something") is None

    def test_provider_failure_response_does_not_route(self, monkeypatch, fixed_catalog):
        # think() reports a missing-key failure as a 200 whose content is a
        # human-readable apology. Routing on that text could match a skill
        # name mentioned inside the apology — resolve_think_text is what
        # keeps this honest.
        _mock_think(monkeypatch, {
            "error": "no api key",
            "choices": [{"message": {"content": "I can't do that — please add a pdf API key in Settings."}}],
        })
        assert classify("generate me a pdf") is None

    def test_exception_from_provider_returns_none(self, monkeypatch, fixed_catalog):
        _mock_think(monkeypatch, RuntimeError("connection refused"))
        assert classify("generate me a pdf") is None


class TestClassifyShortCircuits:
    def test_blank_message_never_calls_the_model(self, monkeypatch, fixed_catalog):
        calls = _mock_think(monkeypatch, _reply("pdf"))
        assert classify("   ") is None
        assert calls == []

    def test_empty_catalog_never_calls_the_model(self, monkeypatch):
        monkeypatch.setattr(semantic_router, "_catalog", lambda: [])
        calls = _mock_think(monkeypatch, _reply("pdf"))
        assert classify("generate me a pdf") is None
        assert calls == []


class TestMatchName:
    def test_unknown_token_returns_none(self):
        assert _match_name("banana", CATALOG) is None

    def test_none_keyword_wins_even_alongside_a_skill_name(self):
        assert _match_name("NONE", CATALOG) is None


class TestCatalogShape:
    def test_descriptions_are_capped(self, monkeypatch):
        # Anthropic's SKILL.md descriptions run several hundred characters;
        # sending them whole would bloat every routing call.
        long_desc = "word " * 200
        monkeypatch.setattr(
            "skills.skill_router.list_skills",
            lambda: [{"name": "verbose", "description": long_desc, "triggers": {}}],
        )
        entry = _catalog()[0]
        assert len(entry["description"]) <= semantic_router._DESCRIPTION_CAP + 1

    def test_entries_without_a_name_are_dropped(self, monkeypatch):
        monkeypatch.setattr(
            "skills.skill_router.list_skills",
            lambda: [{"name": "", "description": "nameless"}, {"name": "pdf", "description": "ok"}],
        )
        assert [c["name"] for c in _catalog()] == ["pdf"]
