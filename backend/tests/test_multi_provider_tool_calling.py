"""Tests that brain.py's think_stream() tool-calling loop (tools/tool_calls
request-response shape) is reachable from every OpenAI-compatible-shaped
provider, not just Groq/OpenAI. Before this, Ollama/LlamaCpp/Gemini/
Custom-openai all hit a fast path that sent no `tools` param at all —
run_python, web_search, save_note, etc. were unreachable regardless of
settings. Anthropic-shaped providers (native + Custom-anthropic) are
deliberately NOT covered here — they use a different wire format entirely,
see test_brain_anthropic_tool_calling.py."""
import json

import brain
import settings_manager

_PRIVACY = "[[PRIVACY]]"


class _FakeResp:
    status_code = 200

    def __init__(self, content="ok"):
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content, "tool_calls": None}}]}


def _reply_text(tokens) -> str:
    """Joined reply with the ``[[PRIVACY]]{...}`` sentinel removed.

    On a cloud route think_stream() emits that one-shot sentinel carrying the
    scrub mapping (brain.py:1023); core.py intercepts it and never shows it
    to the user. Whether it appears at all depends on the PII model finding
    something in the payload — which includes the system prompt, so an
    unrelated prompt edit can start or stop triggering it. Asserting on the
    raw join made these tests fail for reasons having nothing to do with
    tool calling.
    """
    text = "".join(tokens)
    if text.startswith(_PRIVACY):
        # raw_decode, not a brace scan — the payload nests objects inside
        # "mapping", so the first `}` is not the end of the sentinel.
        rest = text[len(_PRIVACY):]
        try:
            _, end = json.JSONDecoder().raw_decode(rest)
            text = rest[end:]
        except ValueError:
            text = rest
    return text.strip()


class TestGeminiToolCalling:
    def test_gemini_sends_tools_in_request(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Gemini_Flash", "gemini_api_key": "sk-x",
        })
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, json=json)
            return _FakeResp("hi from gemini")

        monkeypatch.setattr(brain.requests, "post", fake_post)
        tokens = list(brain.think_stream("hello"))

        assert _reply_text(tokens) == "hi from gemini"
        assert "tools" in captured["json"]
        assert "generativelanguage.googleapis.com" in captured["url"]


class TestOllamaToolCalling:
    def test_ollama_sends_tools_in_request(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Ollama_Local", "ollama_base_url": "http://localhost:11434",
            "ollama_model": "llama3.2",
        })
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, json=json)
            return _FakeResp("hi from ollama")

        monkeypatch.setattr(brain.requests, "post", fake_post)
        tokens = list(brain.think_stream("hello"))

        assert _reply_text(tokens) == "hi from ollama"
        assert "tools" in captured["json"]
        assert captured["url"] == "http://localhost:11434/v1/chat/completions"


class TestLlamaCppToolCalling:
    def test_llamacpp_sends_tools_in_request(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "LlamaCpp_Local", "llamacpp_base_url": "http://localhost:8080",
        })
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, json=json)
            return _FakeResp("hi from llamacpp")

        monkeypatch.setattr(brain.requests, "post", fake_post)
        tokens = list(brain.think_stream("hello"))

        assert _reply_text(tokens) == "hi from llamacpp"
        assert "tools" in captured["json"]
        assert captured["url"] == "http://localhost:8080/v1/chat/completions"


class TestToolCallExecutesForNewlyEnabledProviders:
    def test_ollama_actually_executes_a_requested_tool(self, monkeypatch):
        # Not just "tools were offered" — confirm a tool_calls response from
        # one of the newly-enabled providers is actually executed, matching
        # what already happens for Groq/OpenAI.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Ollama_Local", "ollama_base_url": "http://localhost:11434",
            "ollama_model": "llama3.2",
        })
        responses = iter([
            {"choices": [{"message": {
                "content": None,
                "tool_calls": [{"id": "call_1", "type": "function",
                                 "function": {"name": "list_skills", "arguments": "{}"}}],
            }}]},
            {"choices": [{"message": {"content": "done", "tool_calls": None}}]},
        ])

        class FakeResp:
            status_code = 200
            def json(self):
                return next(responses)

        monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: FakeResp())

        executed = []
        monkeypatch.setattr(brain, "execute_tool", lambda name, args, session_id=None: executed.append(name) or "ok")

        tokens = list(brain.think_stream("what skills do you have"))

        assert executed == ["list_skills"]
        # think_stream() itself still emits the raw [SYSTEM: Executing ...]
        # control token — core.py is what strips it into a separate
        # "tool_executing" broadcast event for the UI. At this level we just
        # confirm the final answer made it through after the tool call.
        assert "done" in "".join(tokens)


class TestProviderThatRejectsToolCalling:
    """Plenty of models behind an OpenAI-compatible proxy reject a request
    carrying `tools` with a 400. Primnox attaches tools to every agentic turn,
    so on such a provider every single message died with a raw API error
    pasted into the chat. It now drops the tools and answers instead."""

    def setup_method(self):
        brain._no_tool_support.clear()

    def teardown_method(self):
        brain._no_tool_support.clear()

    @staticmethod
    def _custom_settings(monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: {
            "active_model": "Custom",
            "active_custom_provider_id": "p1",
            "custom_providers": [{
                "id": "p1", "name": "proxy", "api_type": "openai",
                "base_url": "https://proxy.example", "api_key": "sk-x",
                "model": "some-model",
            }],
        })

    class _Rejects:
        """400s on any request carrying tools, 200s otherwise — the exact
        behaviour of the endpoint that made the app unusable."""
        status_code = 400
        text = ('{"error":{"message":"`tool calling` is not supported with this '
                'model","type":"invalid_request_error","param":"tool calling"}}')

    def _post(self, seen):
        def fake_post(url, headers=None, json=None, timeout=None):
            seen.append(json)
            if "tools" in json:
                return self._Rejects()
            return _FakeResp("here is your answer")
        return fake_post

    def test_the_user_gets_an_answer_instead_of_a_raw_400(self, monkeypatch):
        self._custom_settings(monkeypatch)
        seen = []
        monkeypatch.setattr(brain.requests, "post", self._post(seen))

        tokens = list(brain.think_stream("say something"))

        assert "here is your answer" in _reply_text(tokens)
        assert "API ERROR" not in "".join(tokens)
        assert "tools" in seen[0], "the first attempt should still offer tools"
        assert "tools" not in seen[1], "the retry should drop them"

    def test_later_turns_skip_the_doomed_request_entirely(self, monkeypatch):
        self._custom_settings(monkeypatch)
        seen = []
        monkeypatch.setattr(brain.requests, "post", self._post(seen))

        list(brain.think_stream("first"))
        seen.clear()
        list(brain.think_stream("second"))

        assert seen and all("tools" not in payload for payload in seen), (
            "a provider known to reject tools should not be asked again")

    def test_a_capable_provider_is_never_downgraded(self, monkeypatch):
        self._custom_settings(monkeypatch)
        seen = []
        monkeypatch.setattr(brain.requests, "post",
                            lambda url, headers=None, json=None, timeout=None:
                            seen.append(json) or _FakeResp("fine"))

        list(brain.think_stream("hello"))

        assert len(seen) == 1
        assert "tools" in seen[0]
        assert brain._no_tool_support == set()


class TestRejectsToolsDetection:
    """The marker match is deliberately narrow — a 400 normally means our
    payload was wrong, and dropping tools on every 400 would hide real bugs
    and quietly downgrade a capable model."""

    def test_recognises_the_real_error_body(self):
        assert brain._rejects_tools(
            '{"error":{"message":"`tool calling` is not supported with this model"}}')

    def test_recognises_openai_style_unsupported_parameter(self):
        assert brain._rejects_tools(
            "Unsupported parameter: 'tools' is not supported with this model.")

    def test_ignores_an_unrelated_bad_request(self):
        assert not brain._rejects_tools('{"error":{"message":"invalid JSON in request body"}}')

    def test_ignores_a_context_length_error(self):
        assert not brain._rejects_tools(
            "This model's maximum context length is 8192 tokens.")

    def test_empty_body_is_not_a_tools_rejection(self):
        assert not brain._rejects_tools("")
