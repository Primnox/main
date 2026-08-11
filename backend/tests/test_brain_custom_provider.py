"""Tests for the Custom LLM provider: local/cloud auto-detection from URL,
the /v1/models discovery helper, and both wire formats (OpenAI-compatible and
Anthropic-compatible) in think() and think_stream().

Settings are always monkeypatched via settings_manager.load_settings (brain.py
imports it locally inside each function, so patching the source module is
what actually takes effect — same pattern as the rest of this suite).
"""
import json

import pytest

import brain
import settings_manager


def _settings(**overrides):
    """Builds a settings dict with one named custom-provider profile active.
    Accepts the old flat-field-style kwarg names (custom_api_type,
    custom_base_url, custom_api_key, custom_model) for convenience — they're
    folded into the profile dict — plus any other top-level setting."""
    profile = {
        "id": "p1",
        "name": "Test",
        "api_type": overrides.pop("custom_api_type", "openai"),
        "base_url": overrides.pop("custom_base_url", "http://localhost:9999"),
        "api_key": overrides.pop("custom_api_key", ""),
        "model": overrides.pop("custom_model", "test-model"),
    }
    base = {
        "active_model": "Custom",
        "custom_providers": [profile],
        "active_custom_provider_id": "p1",
        "privacy_mirror_enabled": True,
    }
    base.update(overrides)
    return base


class TestIsLocalUrl:
    @pytest.mark.parametrize("url,expected", [
        ("http://localhost:9999", True),
        ("http://127.0.0.1:8000", True),
        ("https://localhost", True),
        ("http://localhost", True),
        ("https://api.openrouter.ai/v1", False),
        ("http://192.168.1.50:8000", False),
        ("", False),
        (None, False),
        ("not a url at all", False),
    ])
    def test_classification(self, url, expected):
        assert brain._is_local_url(url) is expected


class TestIsLocalProvider:
    def test_ollama_always_local(self):
        assert brain._is_local_provider("Ollama_Local", {}) is True

    def test_llamacpp_always_local(self):
        assert brain._is_local_provider("LlamaCpp_Local", {}) is True

    def test_groq_never_local(self):
        assert brain._is_local_provider("Groq_Llama_3", _settings(custom_base_url="http://localhost:1")) is False

    def test_custom_local_when_url_is_localhost(self):
        assert brain._is_local_provider("Custom", _settings(custom_base_url="http://localhost:8123")) is True

    def test_custom_cloud_when_url_is_remote(self):
        assert brain._is_local_provider("Custom", _settings(custom_base_url="https://api.example.com")) is False

    def test_custom_with_no_url_is_not_local(self):
        assert brain._is_local_provider("Custom", {}) is False

    def test_custom_with_no_active_profile_is_not_local(self):
        assert brain._is_local_provider("Custom", {"custom_providers": [], "active_custom_provider_id": ""}) is False


class TestGetActiveCustomProvider:
    def test_returns_the_active_profile(self):
        settings = _settings(custom_api_key="sk-custom-123")
        profile = brain.get_active_custom_provider(settings)
        assert profile["api_key"] == "sk-custom-123"

    def test_returns_none_when_no_active_id(self):
        assert brain.get_active_custom_provider({}) is None

    def test_returns_none_when_id_not_found(self):
        settings = {"custom_providers": [{"id": "other"}], "active_custom_provider_id": "missing"}
        assert brain.get_active_custom_provider(settings) is None


class TestFetchCustomProviderModels:
    def test_no_base_url(self):
        result = brain.fetch_custom_provider_models("", "openai", "")
        assert result == {"models": [], "error": "No base URL provided."}

    def test_openai_style_parses_model_ids(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": "llama3"}, {"id": "mistral"}]}

        captured = {}

        def fake_get(url, headers=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResp()

        monkeypatch.setattr(brain.requests, "get", fake_get)
        result = brain.fetch_custom_provider_models("http://localhost:9999", "openai", "sk-abc")

        assert result == {"models": ["llama3", "mistral"]}
        assert captured["url"] == "http://localhost:9999/v1/models"
        assert captured["headers"]["Authorization"] == "Bearer sk-abc"

    def test_anthropic_style_uses_x_api_key_header(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": "claude-custom"}]}

        captured = {}

        def fake_get(url, headers=None, timeout=None):
            captured["headers"] = headers
            return FakeResp()

        monkeypatch.setattr(brain.requests, "get", fake_get)
        result = brain.fetch_custom_provider_models("http://localhost:9999", "anthropic", "sk-abc")

        assert result == {"models": ["claude-custom"]}
        assert captured["headers"]["x-api-key"] == "sk-abc"
        assert captured["headers"]["anthropic-version"] == "2023-06-01"

    def test_connection_failure_reports_error_not_exception(self, monkeypatch):
        def fake_get(*a, **kw):
            raise ConnectionError("boom")

        monkeypatch.setattr(brain.requests, "get", fake_get)
        result = brain.fetch_custom_provider_models("http://localhost:9999", "openai", "")

        assert result["models"] == []
        assert "error" in result

    def test_strips_trailing_slash_from_base_url(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"data": []}

        captured = {}
        monkeypatch.setattr(brain.requests, "get", lambda url, **kw: captured.setdefault("url", url) or FakeResp())

        brain.fetch_custom_provider_models("http://localhost:9999/", "openai", "")
        assert captured["url"] == "http://localhost:9999/v1/models"


class TestThinkCustomProvider:
    def test_openai_style_hits_chat_completions(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings())
        captured = {}

        class FakeResp:
            def json(self): return {"choices": [{"message": {"content": "hi there"}}]}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, headers=headers, json=json)
            return FakeResp()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        result = brain.think("hello")

        assert captured["url"] == "http://localhost:9999/v1/chat/completions"
        assert captured["json"]["model"] == "test-model"
        assert result["choices"][0]["message"]["content"] == "hi there"

    def test_anthropic_style_hits_messages_endpoint(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(custom_api_type="anthropic", custom_api_key="sk-abc"))
        captured = {}

        class FakeResp:
            def json(self): return {"content": [{"text": "hi from anthropic-compatible"}]}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, headers=headers, json=json)
            return FakeResp()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        result = brain.think("hello")

        assert captured["url"] == "http://localhost:9999/v1/messages"
        assert captured["headers"]["x-api-key"] == "sk-abc"
        assert "system" in captured["json"]
        assert result["choices"][0]["message"]["content"] == "hi from anthropic-compatible"

    def test_no_base_url_configured_does_not_crash(self, monkeypatch):
        # privacy_mirror_enabled=False here: the point of this test is the
        # missing-URL guard, not exercising a real PII-model load for an
        # empty (therefore non-local) base URL.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(custom_base_url="", privacy_mirror_enabled=False))
        result = brain.think("hello")
        assert "no custom endpoint selected" in result["choices"][0]["message"]["content"].lower()

    def test_remote_custom_url_engages_privacy_mirror(self, monkeypatch):
        # A non-localhost custom URL must be treated as cloud — privacy_mirror's
        # ensure_model_ready gets called, confirming the scrub path actually engages.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(custom_base_url="https://api.example.com"))
        calls = []
        monkeypatch.setattr("privacy_mirror.ensure_model_ready", lambda timeout=45: calls.append(1))
        monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: type("R", (), {"json": lambda self: {"choices": [{"message": {"content": "ok"}}]}})())

        brain.think("hello")

        assert calls == [1]

    def test_local_custom_url_skips_privacy_mirror(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(custom_base_url="http://localhost:9999"))
        calls = []
        monkeypatch.setattr("privacy_mirror.ensure_model_ready", lambda timeout=45: calls.append(1))
        monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: type("R", (), {"json": lambda self: {"choices": [{"message": {"content": "ok"}}]}})())

        brain.think("hello")

        assert calls == []


class TestThinkStreamCustomProvider:
    def test_openai_style_goes_through_the_tool_calling_loop(self, monkeypatch):
        # Custom-openai used to hit a no-tools streaming fast path — every
        # provider except Groq/OpenAI did. It now shares the same
        # tools/tool_calls loop those two use, so run_python/web_search/etc.
        # are actually reachable regardless of which provider is active.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings())
        captured = {}

        class FakeResp:
            status_code = 200
            def json(self):
                return {"choices": [{"message": {"content": "hello there", "tool_calls": None}}]}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, json=json)
            return FakeResp()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        tokens = list(brain.think_stream("hello"))

        assert "".join(tokens).strip() == "hello there"
        assert captured["url"] == "http://localhost:9999/v1/chat/completions"
        assert "tools" in captured["json"]

    def test_anthropic_style_no_tool_use_returns_final_answer_directly(self, monkeypatch):
        # Anthropic tool-calling steps use a non-streaming request (mirrors
        # the Groq/OpenAI loop's own shape) — when the first response has no
        # tool_use blocks, it IS the final answer, no second request needed.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(custom_api_type="anthropic", custom_api_key="sk-abc"))
        captured = {}

        class FakeResp:
            status_code = 200
            def json(self):
                return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "hi there"}]}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, json=json, headers=headers)
            return FakeResp()

        monkeypatch.setattr(brain.requests, "post", fake_post)
        tokens = list(brain.think_stream("hello"))

        assert "".join(tokens).strip() == "hi there"
        assert captured["url"] == "http://localhost:9999/v1/messages"
        assert captured["headers"]["x-api-key"] == "sk-abc"
        assert "system" in captured["json"]
        assert "tools" in captured["json"]

    def test_anthropic_style_tool_use_executes_and_sends_tool_result(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(custom_api_type="anthropic", custom_api_key="sk-abc"))
        responses = iter([
            {
                "stop_reason": "tool_use",
                "content": [
                    {"type": "text", "text": "let me check"},
                    {"type": "tool_use", "id": "toolu_1", "name": "list_skills", "input": {}},
                ],
            },
            {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]},
        ])
        captured_requests = []

        class FakeResp:
            status_code = 200
            def __init__(self, payload):
                self._payload = payload
            def json(self):
                return self._payload

        def fake_post(url, headers=None, json=None, timeout=None):
            captured_requests.append(json)
            return FakeResp(next(responses))

        monkeypatch.setattr(brain.requests, "post", fake_post)
        executed = []
        monkeypatch.setattr(brain, "execute_tool", lambda name, args, session_id=None: executed.append((name, args)) or "ok")

        tokens = list(brain.think_stream("what skills do you have"))

        assert executed == [("list_skills", {})]
        assert "done" in "".join(tokens)
        # Second request must carry the tool_result tied to the first tool_use id.
        second_req = captured_requests[1]
        tool_result_msg = second_req["messages"][-1]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["tool_use_id"] == "toolu_1"
