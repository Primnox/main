"""Tests for emotion_agent.run_emotion_analysis().

This agent had never completed a single run in production. Its first
statement indexed get_all_sessions() — which returns a
{"sessions": [...], "folders": [...]} dict — as if it were a list, so every
invocation raised KeyError: 0 straight into a broad `except` that logged
"Emotion analysis failed: 0" and moved on. The mood system it feeds was
silently dead, and the log line said nothing about why.

So the tests that matter here are the boring ones: does it get as far as
calling the model, and does it write the mood when the model answers.
"""
import json

import pytest

import emotion_agent
from emotion_agent import _strip_code_fence, run_emotion_analysis

_GOOD_JSON = {
    "probabilities": {"Anger": 85},
    "dominant_emotion": "Anger",
    "confidence": 85,
    "reasoning": "short blunt commands",
}


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """A realistic chat history plus an isolated settings file."""
    monkeypatch.setattr(emotion_agent, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(emotion_agent, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(emotion_agent, "get_all_sessions", lambda: {
        "sessions": [{"id": "s1", "title": "Chat", "date": "now"}],
        "folders": [],
    })
    monkeypatch.setattr(emotion_agent, "get_session_messages", lambda sid: [
        {"speaker": "You", "text": "this is broken again"},
        {"speaker": "Primnox", "text": "let me look"},
    ])


def _answers(monkeypatch, content):
    seen = []

    def fake_think(prompt, **kw):
        seen.append(prompt)
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(emotion_agent, "think", fake_think)
    return seen


class TestItActuallyRuns:
    def test_the_model_is_reached_at_all(self, monkeypatch, wired):
        # The regression that matters: before the fix this never got here.
        seen = _answers(monkeypatch, json.dumps(_GOOD_JSON))
        run_emotion_analysis()
        assert seen, "run_emotion_analysis never reached the model"
        assert "this is broken again" in seen[0]

    def test_a_confident_reading_updates_the_mood(self, monkeypatch, wired):
        _answers(monkeypatch, json.dumps(_GOOD_JSON))
        run_emotion_analysis()
        assert emotion_agent.load_settings()["current_mood"] == "Anger"

    def test_a_fenced_reply_is_still_parsed(self, monkeypatch, wired):
        # Models wrap JSON in ```json fences constantly; the old stripping
        # tested for one backtick while slicing three, so this always failed.
        _answers(monkeypatch, f"```json\n{json.dumps(_GOOD_JSON)}\n```")
        run_emotion_analysis()
        assert emotion_agent.load_settings()["current_mood"] == "Anger"

    def test_low_confidence_leaves_the_mood_alone(self, monkeypatch, wired):
        _answers(monkeypatch, json.dumps({**_GOOD_JSON, "confidence": 40}))
        run_emotion_analysis()
        assert "current_mood" not in emotion_agent.load_settings()

    def test_an_unknown_emotion_label_is_ignored(self, monkeypatch, wired):
        _answers(monkeypatch, json.dumps({**_GOOD_JSON, "dominant_emotion": "Ennui"}))
        run_emotion_analysis()
        assert "current_mood" not in emotion_agent.load_settings()


class TestItFailsQuietlyAndHonestly:
    def test_no_sessions_is_a_no_op_not_a_crash(self, monkeypatch, tmp_path):
        monkeypatch.setattr(emotion_agent, "SETTINGS_FILE", tmp_path / "settings.json")
        monkeypatch.setattr(emotion_agent, "get_all_sessions", lambda: {"sessions": [], "folders": []})
        monkeypatch.setattr(emotion_agent, "think", lambda *a, **kw: pytest.fail("should not think"))
        run_emotion_analysis()

    def test_a_provider_error_does_not_reach_the_json_parser(self, monkeypatch, wired):
        monkeypatch.setattr(emotion_agent, "think", lambda *a, **kw: {"error": "offline"})
        run_emotion_analysis()  # must not raise
        assert "current_mood" not in emotion_agent.load_settings()

    def test_unparseable_content_is_logged_with_its_type(self, monkeypatch, wired):
        # caplog can't see this — get_logger() attaches its own handlers and
        # doesn't propagate to root — so capture the call itself. The type
        # name is the point: the old message for a KeyError was bare "0".
        logged = []
        monkeypatch.setattr(emotion_agent.log, "error", lambda msg: logged.append(msg))
        _answers(monkeypatch, "I think they seem a bit cross today.")

        run_emotion_analysis()

        assert logged and "JSONDecodeError" in logged[0]

    def test_an_empty_choices_list_does_not_raise(self, monkeypatch, wired):
        monkeypatch.setattr(emotion_agent, "think", lambda *a, **kw: {"choices": []})
        run_emotion_analysis()

    def test_a_message_without_a_speaker_key_does_not_raise(self, monkeypatch, wired):
        monkeypatch.setattr(emotion_agent, "get_session_messages",
                            lambda sid: [{"text": "no speaker field"}])
        _answers(monkeypatch, json.dumps(_GOOD_JSON))
        run_emotion_analysis()


class TestStripCodeFence:
    def test_strips_a_json_tagged_fence(self):
        assert _strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_an_untagged_fence(self):
        assert _strip_code_fence('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_leaves_bare_json_untouched(self):
        assert _strip_code_fence('{"a": 1}') == '{"a": 1}'

    def test_empty_input_stays_empty(self):
        assert _strip_code_fence("") == ""
