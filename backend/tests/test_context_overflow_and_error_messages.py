"""When the provider says no, does the user learn anything useful?

Two failures that made Primnox look broken with no way to diagnose it:

  1. A model whose context window can't hold the conversation returned a 400
     and the whole turn was lost. A long chat should shed history, not the
     message.
  2. Every API failure — bad key, dead model, out of quota — surfaced as
     "Sorry, something went wrong. Please try again." For most of those
     causes that's actively wrong advice: it will fail identically on every
     retry, and the fix is in Settings.
"""
import json

import pytest

import brain
import core
import settings_manager
from brain import _context_too_long, _drop_oldest_turn
from core import _GENERIC_FAILURE, _explain_api_error


class TestDetectingContextOverflow:
    @pytest.mark.parametrize("body", [
        '{"error":{"code":"context_length_exceeded"}}',
        '{"error":{"message":"Please reduce the length of the messages or completion."}}',
        "This model's maximum context length is 4096 tokens.",
        '{"error":{"message":"prompt is too long: 250000 tokens > 200000"}}',
    ])
    def test_recognises_real_overflow_bodies(self, body):
        assert _context_too_long(body)

    @pytest.mark.parametrize("body", [
        '{"error":{"message":"invalid api key"}}',
        '{"error":{"message":"`tool calling` is not supported with this model"}}',
        "",
    ])
    def test_ignores_unrelated_errors(self, body):
        assert not _context_too_long(body)


class TestDroppingOldestTurn:
    def test_drops_the_oldest_turn_after_the_system_prompt(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "older reply"},
            {"role": "user", "content": "current"},
        ]
        assert _drop_oldest_turn(messages) is True
        assert [m["content"] for m in messages] == ["sys", "older reply", "current"]

    def test_a_long_history_sheds_a_quarter_at_a_time(self):
        # One-at-a-time would exhaust the retry budget on a long chat while
        # still overflowing.
        messages = ([{"role": "system", "content": "sys"}]
                    + [{"role": "user", "content": str(i)} for i in range(40)]
                    + [{"role": "user", "content": "current"}])
        assert _drop_oldest_turn(messages) is True
        assert len(messages) == 32
        assert messages[0]["content"] == "sys"
        assert messages[-1]["content"] == "current"

    def test_never_drops_the_system_prompt(self):
        messages = [{"role": "system", "content": "sys"},
                    {"role": "user", "content": "a"},
                    {"role": "user", "content": "current"}]
        _drop_oldest_turn(messages)
        assert messages[0]["role"] == "system"

    def test_never_drops_the_current_message(self):
        messages = [{"role": "system", "content": "sys"},
                    {"role": "user", "content": "a"},
                    {"role": "user", "content": "current"}]
        _drop_oldest_turn(messages)
        assert messages[-1]["content"] == "current"

    def test_refuses_when_only_the_prompt_and_the_question_remain(self):
        # The signal that trimming can no longer help — the model itself is
        # too small, which is a different problem with a different answer.
        messages = [{"role": "system", "content": "sys"},
                    {"role": "user", "content": "current"}]
        assert _drop_oldest_turn(messages) is False
        assert len(messages) == 2

    def test_handles_a_history_with_no_system_prompt(self):
        messages = [{"role": "user", "content": "a"},
                    {"role": "assistant", "content": "b"},
                    {"role": "user", "content": "current"}]
        assert _drop_oldest_turn(messages) is True
        assert [m["content"] for m in messages] == ["b", "current"]


class TestOverflowRecoveryEndToEnd:
    """The whole point: a chat too long for the model still gets answered."""

    @staticmethod
    def _settings(monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Groq_Llama_3", "groq_api_key": "sk-x",
        })

    class _Overflow:
        status_code = 400
        text = ('{"error":{"message":"Please reduce the length of the messages or '
                'completion.","code":"context_length_exceeded"}}')

    class _Ok:
        status_code = 200
        headers = {}

        def json(self):
            return {"choices": [{"message": {"content": "Paris.", "tool_calls": None}}]}

    @staticmethod
    def _long_history(monkeypatch):
        """A real chat's worth of prior turns. Only a session_id produces
        separate message entries — without one, `messages` is just
        [system, user] and there is nothing to trim."""
        import chat_manager
        history = []
        for i in range(12):
            history.append({"speaker": "You", "text": f"question {i}", "timestamp": i})
            history.append({"speaker": "Primnox", "text": f"answer {i}", "timestamp": i})
        monkeypatch.setattr(chat_manager, "get_session_messages", lambda sid: history)

    def test_a_too_long_chat_is_trimmed_and_answered(self, monkeypatch):
        self._settings(monkeypatch)
        self._long_history(monkeypatch)
        sizes = []

        def fake_post(url, headers=None, json=None, timeout=None):
            sizes.append(len(json["messages"]))
            # Accept once the history has been trimmed at least once.
            return self._Ok() if len(sizes) > 1 else self._Overflow()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        tokens = list(brain.think_stream("what is the capital of France", session_id="s1"))

        assert "Paris." in "".join(tokens)
        assert len(sizes) >= 2, "no retry was attempted"
        assert sizes[-1] < sizes[0], "the retry did not send fewer messages"

    def test_it_keeps_trimming_until_the_chat_fits(self, monkeypatch):
        # One dropped turn is rarely enough on a genuinely long conversation.
        self._settings(monkeypatch)
        self._long_history(monkeypatch)
        sizes = []

        def fake_post(url, headers=None, json=None, timeout=None):
            sizes.append(len(json["messages"]))
            return self._Ok() if len(json["messages"]) <= 20 else self._Overflow()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        tokens = list(brain.think_stream("still there?", session_id="s1"))

        assert "Paris." in "".join(tokens)
        assert sizes[0] > 20 and sizes[-1] <= 20

    def test_a_model_that_can_never_fit_says_so_instead_of_looping(self, monkeypatch):
        self._settings(monkeypatch)
        calls = []

        def always_overflow(url, headers=None, json=None, timeout=None):
            calls.append(1)
            return self._Overflow()

        monkeypatch.setattr(brain.requests, "post", always_overflow)
        tokens = list(brain.think_stream("hi"))

        assert "[MODEL TOO SMALL]" in "".join(tokens)
        assert len(calls) < 20, "trimming should terminate, not spin"


class TestExplainingErrorsToTheUser:
    def test_a_model_too_small_names_the_model_and_points_at_settings(self):
        msg = _explain_api_error("[MODEL TOO SMALL] allam-2-7b")
        assert "allam-2-7b" in msg
        assert "Settings" in msg
        assert "try again" not in msg.lower(), "retrying will never help here"

    def test_a_rejected_key_says_so(self):
        msg = _explain_api_error('[API ERROR 401]: {"error":{"code":"invalid_api_key"}}')
        assert "key" in msg.lower() and "Settings" in msg

    def test_out_of_quota_mentions_billing(self):
        msg = _explain_api_error('[API ERROR 429]: {"error":{"code":"insufficient_quota"}}')
        assert "quota" in msg.lower() or "billing" in msg.lower()

    def test_a_missing_model_points_at_the_model_picker(self):
        msg = _explain_api_error('[API ERROR 404]: {"error":{"code":"model_not_found"}}')
        assert "model" in msg.lower() and "Settings" in msg

    def test_rate_limiting_is_the_one_case_where_retrying_is_right(self):
        msg = _explain_api_error('[API ERROR 429]: rate limit reached')
        assert "try again" in msg.lower()

    def test_an_overgrown_chat_suggests_starting_a_new_one(self):
        msg = _explain_api_error('[API ERROR 400]: {"error":{"code":"context_length_exceeded"}}')
        assert "new chat" in msg.lower()

    def test_an_unrecognised_error_keeps_the_generic_message(self):
        assert _explain_api_error("[API ERROR 500]: upstream exploded") == _GENERIC_FAILURE
