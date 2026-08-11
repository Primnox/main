"""Tests for native Anthropic_Claude_3 tool-calling in brain.py's
think_stream(). Anthropic previously had zero tool-calling support in this
codepath — the streaming branch sent no `tools` field at all, for either
native Anthropic_Claude_3 or Custom-anthropic. See
test_brain_custom_provider.py's TestThinkStreamCustomProvider for the
Custom-anthropic equivalent of the basic cases; this file covers native
Anthropic_Claude_3 plus the max-steps and code_execution_enabled-filtering
behavior shared by both."""
import brain
import settings_manager


def _settings(**overrides):
    base = {"active_model": "Anthropic_Claude_3", "anthropic_api_key": "sk-ant-x"}
    base.update(overrides)
    return base


class _FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class TestNativeAnthropicToolCalling:
    def test_sends_tools_shaped_as_input_schema_not_parameters(self, monkeypatch):
        # Anthropic's tool schema is {"name","description","input_schema"} —
        # flat, not OpenAI's nested {"type":"function","function":{...}}.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(code_execution_enabled=True))
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, json=json)
            return _FakeResp({"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]})

        monkeypatch.setattr(brain.requests, "post", fake_post)
        list(brain.think_stream("hello"))

        assert captured["url"] == "https://api.anthropic.com/v1/messages"
        tool_names = {t["name"] for t in captured["json"]["tools"]}
        assert "run_python" in tool_names
        sample = next(t for t in captured["json"]["tools"] if t["name"] == "list_skills")
        assert "input_schema" in sample
        assert "parameters" not in sample

    def test_code_execution_disabled_excludes_run_python_from_anthropic_tools(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(code_execution_enabled=False))
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(json=json)
            return _FakeResp({"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]})

        monkeypatch.setattr(brain.requests, "post", fake_post)
        list(brain.think_stream("hello"))

        tool_names = {t["name"] for t in captured["json"]["tools"]}
        assert "run_python" not in tool_names
        assert "run_shell" not in tool_names
        assert "list_skills" in tool_names  # unrelated tools stay available

    def test_multi_step_tool_use_then_final_answer(self, monkeypatch):
        responses = iter([
            {
                "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "id": "toolu_1", "name": "list_skills", "input": {}}],
            },
            {"stop_reason": "end_turn", "content": [{"type": "text", "text": "here you go"}]},
        ])
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings())
        monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: _FakeResp(next(responses)))
        monkeypatch.setattr(brain, "execute_tool", lambda *a, **kw: "some tool output")

        tokens = list(brain.think_stream("hi"))

        assert "here you go" in "".join(tokens)

    def test_max_steps_exhausted_forces_a_final_streaming_pass(self, monkeypatch):
        # A model that never stops calling tools must not loop forever —
        # after max_steps, one last tool-less streaming request gets the
        # user an actual answer instead of nothing.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings())

        call_count = {"non_streaming": 0}

        def fake_post(url, headers=None, json=None, stream=None, timeout=None):
            if json.get("stream"):
                class FakeStreamResp:
                    status_code = 200
                    def iter_lines(self):
                        yield b'data: {"type":"content_block_delta","delta":{"text":"final answer"}}'
                return FakeStreamResp()
            call_count["non_streaming"] += 1
            return _FakeResp({
                "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "id": f"toolu_{call_count['non_streaming']}", "name": "list_skills", "input": {}}],
            })

        monkeypatch.setattr(brain.requests, "post", fake_post)
        monkeypatch.setattr(brain, "execute_tool", lambda *a, **kw: "output")

        tokens = list(brain.think_stream("hi"))

        assert call_count["non_streaming"] == 5  # max_steps
        assert "final answer" in "".join(tokens)

    def test_non_200_response_yields_error_and_stops(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings())

        class FakeErrorResp:
            status_code = 401
            text = "invalid api key"

        monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: FakeErrorResp())
        tokens = list(brain.think_stream("hi"))

        assert any("401" in t for t in tokens)
