"""Tests that brain.py's think_stream() tool-calling loop (tools/tool_calls
request-response shape) is reachable from every OpenAI-compatible-shaped
provider, not just Groq/OpenAI. Before this, Ollama/LlamaCpp/Gemini/
Custom-openai all hit a fast path that sent no `tools` param at all —
run_python, web_search, save_note, etc. were unreachable regardless of
settings. Anthropic-shaped providers (native + Custom-anthropic) are
deliberately NOT covered here — they use a different wire format entirely,
see test_brain_anthropic_tool_calling.py."""
import brain
import settings_manager


class _FakeResp:
    status_code = 200

    def __init__(self, content="ok"):
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content, "tool_calls": None}}]}


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

        assert "".join(tokens).strip() == "hi from gemini"
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

        assert "".join(tokens).strip() == "hi from ollama"
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

        assert "".join(tokens).strip() == "hi from llamacpp"
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
