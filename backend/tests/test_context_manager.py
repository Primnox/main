"""Tests for context_manager.py's token-budgeted history selection — the
replacement for brain.py's old hardcoded [-20:]/16000-char truncation."""
import pytest

from context_manager import estimate_tokens, build_history, MAX_MESSAGE_COUNT


def _msg(text, speaker="User"):
    return {"text": text, "speaker": speaker}


class TestEstimateTokens:
    def test_empty_string_is_at_least_one_token(self):
        assert estimate_tokens("") == 1

    def test_roughly_four_chars_per_token(self):
        assert estimate_tokens("a" * 400) == 100

    def test_never_zero_for_nonempty_text(self):
        assert estimate_tokens("hi") >= 1


class TestBuildHistory:
    def test_empty_messages_returns_empty(self):
        assert build_history([], "Groq_Llama_3", is_local=False) == []

    def test_keeps_chronological_order(self):
        messages = [_msg(f"message {i}") for i in range(10)]
        result = build_history(messages, "Groq_Llama_3", is_local=False)
        assert [m["text"] for m in result] == [m["text"] for m in messages]

    def test_always_keeps_at_least_the_most_recent_message_even_if_oversized(self):
        # A single message far larger than any budget must not be dropped —
        # the old code never produced an empty history for one huge message.
        huge = _msg("x" * 10_000_000)
        result = build_history([huge], "Groq_Llama_3", is_local=False)
        assert result == [huge]

    def test_drops_oldest_first_when_over_budget(self):
        # Groq's safe_request_ceiling is 24000 tokens; reserve 2000 by default
        # -> ~22000 token budget -> ~88000 chars. Build messages that overflow it.
        messages = [_msg("y" * 20_000) for _ in range(10)]  # 200k chars total
        result = build_history(messages, "Groq_Llama_3", is_local=False)
        assert len(result) < len(messages)
        # The kept messages must be a suffix (the most recent ones) of the input.
        assert result == messages[-len(result):]

    def test_local_model_budget_is_not_extra_clamped_below_its_registry_ceiling(self):
        # Ollama's safe_request_ceiling in model_registry.py equals its full
        # context_window (no external rate ceiling to guard against) — verify
        # build_history actually uses that full figure rather than silently
        # applying some other reduction on top of it.
        from model_registry import get_model_metadata
        meta = get_model_metadata("Ollama_Local", is_local=True)
        budget_chars = (meta["safe_request_ceiling"] - 2000) * 4  # default reserve_tokens=2000
        # One message sized to use almost the whole budget should still be kept
        # alongside a couple of small recent ones, not dropped for headroom
        # the registry ceiling already accounts for.
        messages = [_msg("a" * int(budget_chars * 0.8)), _msg("recent 1"), _msg("recent 2")]
        result = build_history(messages, "Ollama_Local", is_local=True)
        assert result == messages

    def test_hard_message_count_ceiling_applies_even_for_tiny_messages(self):
        # Belt-and-suspenders: many short messages shouldn't exceed
        # max_message_count regardless of how little budget they'd use.
        messages = [_msg("hi") for _ in range(500)]
        result = build_history(messages, "Ollama_Local", is_local=True, max_message_count=MAX_MESSAGE_COUNT)
        assert len(result) <= MAX_MESSAGE_COUNT

    def test_reserve_tokens_shrinks_the_usable_budget(self):
        messages = [_msg("w" * 20_000) for _ in range(10)]
        generous = build_history(messages, "Groq_Llama_3", is_local=False, reserve_tokens=100)
        stingy = build_history(messages, "Groq_Llama_3", is_local=False, reserve_tokens=20_000)
        assert len(stingy) <= len(generous)

    def test_is_a_pure_function_no_mutation(self):
        messages = [_msg(f"message {i}") for i in range(5)]
        original = [dict(m) for m in messages]
        build_history(messages, "Groq_Llama_3", is_local=False)
        assert messages == original
