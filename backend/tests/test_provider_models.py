"""Tests for the per-provider model picker backend: brain.py's unified
fetch_provider_models() dispatcher (live detection with a curated fallback),
the Gemini-specific List Models fetcher (different response shape than the
OpenAI-style /v1/models used everywhere else), the non-chat-model filter, and
the optional groq_model "pin one, fall back to the chain" behavior.
"""
import pytest

import brain
import settings_manager


class TestIsChatModel:
    @pytest.mark.parametrize("model_id,expected", [
        ("gpt-4o", True),
        ("llama-3.3-70b-versatile", True),
        ("claude-3-5-sonnet-20241022", True),
        ("whisper-large-v3", False),
        ("tts-1-hd", False),
        ("dall-e-3", False),
        ("text-embedding-3-small", False),
        ("llama-guard-3-8b", False),
        ("text-moderation-latest", False),
        ("davinci-002", False),
        ("babbage-002", False),
        ("ada", False),
    ])
    def test_classification(self, model_id, expected):
        assert brain._is_chat_model(model_id) is expected


class TestIsTtsModel:
    @pytest.mark.parametrize("model_id,expected", [
        ("tts-1", True),
        ("tts-1-hd", True),
        ("playai-tts", True),
        ("canopylabs/orpheus-v1-english", True),
        ("whisper-large-v3", False),  # transcription, not synthesis
        ("gpt-4o", False),
        ("llama-3.3-70b-versatile", False),
        ("claude-3-5-sonnet-20241022", False),
    ])
    def test_classification(self, model_id, expected):
        assert brain._is_tts_model(model_id) is expected


class TestFetchGeminiModels:
    def test_no_api_key(self):
        result = brain.fetch_gemini_models("")
        assert result == {"models": [], "error": "No API key provided."}

    def test_filters_to_generate_content_models(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self):
                return {"models": [
                    {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
                    {"name": "models/gemini-1.5-flash", "supportedGenerationMethods": ["generateContent", "countTokens"]},
                ]}

        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured["url"] = url
            captured["params"] = params
            return FakeResp()

        monkeypatch.setattr(brain.requests, "get", fake_get)
        result = brain.fetch_gemini_models("test-key")

        assert result == {"models": ["gemini-1.5-flash", "gemini-2.0-flash"]}
        assert captured["params"] == {"key": "test-key"}

    def test_connection_failure_reports_error_not_exception(self, monkeypatch):
        def fake_get(*a, **kw):
            raise ConnectionError("boom")
        monkeypatch.setattr(brain.requests, "get", fake_get)
        result = brain.fetch_gemini_models("test-key")
        assert result["models"] == []
        assert "error" in result


class TestFetchProviderModels:
    def test_unknown_provider(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {})
        result = brain.fetch_provider_models("not-a-real-provider", "key")
        assert result["models"] == []
        assert "error" in result

    def test_live_success_filters_non_chat_and_tags_source(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": "gpt-4o"}, {"id": "whisper-1"}, {"id": "gpt-4o-mini"}]}

        monkeypatch.setattr(brain.requests, "get", lambda *a, **kw: FakeResp())
        result = brain.fetch_provider_models("openai", "sk-real")

        assert result["source"] == "live"
        assert result["models"] == ["gpt-4o", "gpt-4o-mini"]

    def test_falls_back_when_live_detection_fails(self, monkeypatch):
        def fake_get(*a, **kw):
            raise ConnectionError("boom")
        monkeypatch.setattr(brain.requests, "get", fake_get)
        result = brain.fetch_provider_models("anthropic", "sk-real")

        assert result["source"] == "fallback"
        assert result["models"] == brain.ANTHROPIC_FALLBACK_MODELS

    def test_falls_back_to_groq_chain(self, monkeypatch):
        monkeypatch.setattr(brain.requests, "get", lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("boom")))
        result = brain.fetch_provider_models("groq", "sk-real")
        assert result["models"] == brain.GROQ_FALLBACK_CHAIN

    def test_gemini_dispatches_to_gemini_fetcher(self, monkeypatch):
        monkeypatch.setattr(brain, "fetch_gemini_models", lambda key: {"models": ["gemini-2.0-flash"]})
        result = brain.fetch_provider_models("gemini", "test-key")
        assert result == {"models": ["gemini-2.0-flash"], "source": "live"}

    def test_sentinel_key_falls_back_to_real_stored_key(self, monkeypatch):
        # Settings UI echoes back "sk-****" for an already-saved key instead of
        # retyping it — the endpoint must resolve the real key itself rather
        # than sending the literal placeholder to the provider.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {"openai_api_key": "sk-real-stored"})
        captured = {}

        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"data": []}

        def fake_get(url, headers=None, timeout=None):
            captured["headers"] = headers
            return FakeResp()

        monkeypatch.setattr(brain.requests, "get", fake_get)
        brain.fetch_provider_models("openai", "sk-****")

        assert captured["headers"]["Authorization"] == "Bearer sk-real-stored"


class TestFetchProviderModelsTtsCapability:
    def test_openai_tts_returns_only_tts_models(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self):
                return {"data": [{"id": "gpt-4o"}, {"id": "tts-1"}, {"id": "tts-1-hd"}, {"id": "whisper-1"}]}

        monkeypatch.setattr(brain.requests, "get", lambda *a, **kw: FakeResp())
        result = brain.fetch_provider_models("openai", "sk-real", capability="tts")

        assert result["source"] == "live"
        assert sorted(result["models"]) == ["tts-1", "tts-1-hd"]

    def test_groq_tts_returns_only_tts_models(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self):
                return {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "playai-tts"},
                                  {"id": "canopylabs/orpheus-v1-english"}]}

        monkeypatch.setattr(brain.requests, "get", lambda *a, **kw: FakeResp())
        result = brain.fetch_provider_models("groq", "sk-real", capability="tts")

        assert result["source"] == "live"
        assert sorted(result["models"]) == ["canopylabs/orpheus-v1-english", "playai-tts"]

    def test_anthropic_tts_is_empty_not_an_error(self, monkeypatch):
        # Anthropic offers no TTS models at all — a successful check that
        # finds none is "live" with an empty list, not a failure state.
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": "claude-3-5-sonnet-20241022"}]}

        monkeypatch.setattr(brain.requests, "get", lambda *a, **kw: FakeResp())
        result = brain.fetch_provider_models("anthropic", "sk-real", capability="tts")

        assert result == {"models": [], "source": "live"}

    def test_tts_has_no_curated_fallback(self, monkeypatch):
        # Unlike chat, there's no "safe default" TTS model to guess at — a
        # failed detection returns an empty fallback, not a guessed model id.
        def fake_get(*a, **kw):
            raise ConnectionError("boom")
        monkeypatch.setattr(brain.requests, "get", fake_get)
        result = brain.fetch_provider_models("openai", "sk-real", capability="tts")

        assert result["source"] == "fallback"
        assert result["models"] == []

    def test_chat_capability_is_unaffected_default(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": "gpt-4o"}, {"id": "tts-1"}]}

        monkeypatch.setattr(brain.requests, "get", lambda *a, **kw: FakeResp())
        result = brain.fetch_provider_models("openai", "sk-real")  # capability defaults to "chat"

        assert result["models"] == ["gpt-4o"]


class TestFetchProviderModelsKeyResolution:
    def test_missing_key_falls_back_to_real_stored_key(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {"groq_api_key": "sk-from-settings"})
        captured = {}

        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": "llama-3.3-70b-versatile"}]}

        def fake_get(url, headers=None, timeout=None):
            captured["headers"] = headers
            return FakeResp()

        monkeypatch.setattr(brain.requests, "get", fake_get)
        brain.fetch_provider_models("groq", "")

        assert captured["headers"]["Authorization"] == "Bearer sk-from-settings"


class TestGroqPinningNonStreaming:
    def test_pinned_model_tried_first(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Groq_Llama_3", "groq_api_key": "sk-x", "groq_model": "my-favorite-model",
        })
        attempted = []

        def fake_post(url, headers=None, json=None, timeout=None):
            attempted.append(json["model"])
            class R:
                status_code = 200
                headers = {}
                def json(self): return {"choices": [{"message": {"content": "ok"}}]}
            return R()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        brain.think("hello")

        assert attempted[0] == "my-favorite-model"

    def test_falls_back_to_chain_when_pinned_model_fails(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Groq_Llama_3", "groq_api_key": "sk-x", "groq_model": "broken-pinned-model",
        })
        attempted = []

        def fake_post(url, headers=None, json=None, timeout=None):
            attempted.append(json["model"])
            class R:
                status_code = 400
                headers = {}
                def json(self): return {"error": "model not found"}
            return R()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Groq_Llama_3", "groq_api_key": "sk-x", "groq_model": "broken-pinned-model",
            "gemini_api_key": "",
        })
        brain.think("hello")

        assert attempted[0] == "broken-pinned-model"
        assert attempted[1] in brain.GROQ_FALLBACK_CHAIN

    def test_no_pin_uses_normal_chain(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Groq_Llama_3", "groq_api_key": "sk-x", "groq_model": "",
        })
        attempted = []

        def fake_post(url, headers=None, json=None, timeout=None):
            attempted.append(json["model"])
            class R:
                status_code = 200
                headers = {}
                def json(self): return {"choices": [{"message": {"content": "ok"}}]}
            return R()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        brain.think("hello")

        assert attempted[0] in brain.GROQ_FALLBACK_CHAIN


class TestGroqPinningStreaming:
    def test_pinned_model_used_for_initial_request(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Groq_Llama_3", "groq_api_key": "sk-x", "groq_model": "my-favorite-model",
        })
        captured = {}

        class FakeResp:
            status_code = 200
            def json(self): return {"choices": [{"message": {"content": "no tools needed", "tool_calls": None}}]}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.setdefault("models", []).append(json["model"])
            return FakeResp()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        list(brain.think_stream("hello"))

        assert captured["models"][0] == "my-favorite-model"

    def test_pinned_model_survives_429_rotation_without_crashing(self, monkeypatch):
        # Before the fix, a pinned model outside GROQ_FALLBACK_CHAIN reaching
        # the manual-tool-parse retry path would raise ValueError from
        # GROQ_FALLBACK_CHAIN.index(model_name) — this is the regression test
        # for that specific crash.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Groq_Llama_3", "groq_api_key": "sk-x", "groq_model": "totally-custom-model",
        })
        call_count = {"n": 0}

        def fake_post(url, headers=None, json=None, timeout=None):
            call_count["n"] += 1
            class R:
                status_code = 429
                text = "rate limited"
            return R()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        # The point of this test is that it doesn't raise ValueError from
        # GROQ_FALLBACK_CHAIN.index(model_name) — just consuming the generator
        # to completion without an exception is the assertion.
        list(brain.think_stream("hello"))
        assert call_count["n"] > 0
