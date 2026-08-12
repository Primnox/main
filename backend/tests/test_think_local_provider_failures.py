"""Regression tests: brain.think()'s Ollama_Local and LlamaCpp_Local failure
paths must set an "error" key, same as the Groq/OpenAI/Anthropic/Custom
branches.

Root cause (Smart Paste bug, backend/server.py's /api/smart_paste): these two
branches used to return `{"choices": [{"message": {"content": "<human-
readable failure text>"}}]}` on a timeout or connection error, with no
"error" key. brain.resolve_think_text() — the guard every clipboard-writing
caller must go through (see test_smart_paste_resolve.py) — only recognises a
failure when an "error" key is present, so it treated these responses as a
real completion and callers like Smart Paste wrote the failure text straight
into the user's OS clipboard. Fixed by adding "error" alongside "choices" in
brain.py, matching the pattern already used for the Groq/OpenAI/Anthropic/
Custom-provider failure returns.
"""
import settings_manager
import brain


def _settings(active_model, **overrides):
    base = {
        "active_model": active_model,
        "privacy_mirror_enabled": False,  # these providers are local; irrelevant here
    }
    base.update(overrides)
    return base


class TestThinkOllamaLocalFailures:
    def test_connection_error_sets_error_key(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings("Ollama_Local"))

        def fake_post(*a, **kw):
            raise brain.requests.exceptions.ConnectionError("refused")

        monkeypatch.setattr(brain.requests, "post", fake_post)
        result = brain.think("hello")

        assert result.get("error")
        assert "ollama" in result["choices"][0]["message"]["content"].lower()
        # The actual clipboard-safety contract Smart Paste depends on.
        assert brain.resolve_think_text(result, "original clipboard text") == "original clipboard text"

    def test_timeout_sets_error_key(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings("Ollama_Local"))

        def fake_post(*a, **kw):
            raise brain.requests.exceptions.Timeout("slow")

        monkeypatch.setattr(brain.requests, "post", fake_post)
        result = brain.think("hello")

        assert result.get("error")
        assert brain.resolve_think_text(result, "original clipboard text") == "original clipboard text"


class TestThinkLlamaCppLocalFailures:
    def test_connection_error_sets_error_key(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings("LlamaCpp_Local"))

        def fake_post(*a, **kw):
            raise brain.requests.exceptions.ConnectionError("refused")

        monkeypatch.setattr(brain.requests, "post", fake_post)
        result = brain.think("hello")

        assert result.get("error")
        assert "llama.cpp" in result["choices"][0]["message"]["content"].lower()
        assert brain.resolve_think_text(result, "original clipboard text") == "original clipboard text"

    def test_timeout_sets_error_key(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings("LlamaCpp_Local"))

        def fake_post(*a, **kw):
            raise brain.requests.exceptions.Timeout("slow")

        monkeypatch.setattr(brain.requests, "post", fake_post)
        result = brain.think("hello")

        assert result.get("error")
        assert brain.resolve_think_text(result, "original clipboard text") == "original clipboard text"
