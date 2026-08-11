"""Tests that brain.py's think_stream() keeps run_python/run_shell entirely
out of the tool list offered to the model when code_execution_enabled is
falsy — not just gated behind a permission prompt, genuinely absent from the
request payload. See code_exec.py/tools.py for the runtime permission gate
itself, which applies once the tools *are* offered."""
import brain
import settings_manager


class _FakeResp:
    status_code = 200

    def json(self):
        return {"choices": [{"message": {"content": "ok", "tool_calls": None}}]}


def _settings(**overrides):
    base = {"active_model": "Groq_Llama_3", "groq_api_key": "sk-x"}
    base.update(overrides)
    return base


class TestCodeExecutionToolFiltering:
    def test_tools_excluded_when_disabled(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(code_execution_enabled=False))
        captured = {}
        monkeypatch.setattr(brain.requests, "post", lambda url, headers=None, json=None, timeout=None:
                             captured.setdefault("json", json) or _FakeResp())

        list(brain.think_stream("hello"))

        tool_names = {t["function"]["name"] for t in captured["json"]["tools"]}
        assert "run_python" not in tool_names
        assert "run_shell" not in tool_names

    def test_tools_excluded_when_key_absent(self, monkeypatch):
        # No code_execution_enabled key at all — same as the DEFAULT_SETTINGS
        # value (False), must fail closed rather than defaulting to visible.
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings())
        captured = {}
        monkeypatch.setattr(brain.requests, "post", lambda url, headers=None, json=None, timeout=None:
                             captured.setdefault("json", json) or _FakeResp())

        list(brain.think_stream("hello"))

        tool_names = {t["function"]["name"] for t in captured["json"]["tools"]}
        assert "run_python" not in tool_names
        assert "run_shell" not in tool_names

    def test_tools_included_when_enabled(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(code_execution_enabled=True))
        captured = {}
        monkeypatch.setattr(brain.requests, "post", lambda url, headers=None, json=None, timeout=None:
                             captured.setdefault("json", json) or _FakeResp())

        list(brain.think_stream("hello"))

        tool_names = {t["function"]["name"] for t in captured["json"]["tools"]}
        assert "run_python" in tool_names
        assert "run_shell" in tool_names

    def test_other_tools_unaffected_by_the_filter(self, monkeypatch):
        monkeypatch.setattr(settings_manager, "load_settings", lambda: _settings(code_execution_enabled=False))
        captured = {}
        monkeypatch.setattr(brain.requests, "post", lambda url, headers=None, json=None, timeout=None:
                             captured.setdefault("json", json) or _FakeResp())

        list(brain.think_stream("hello"))

        tool_names = {t["function"]["name"] for t in captured["json"]["tools"]}
        # Disabling code execution shouldn't shrink the tool list to nothing —
        # only the two sandboxed-execution tools should be missing.
        assert len(tool_names) == len(brain.TOOL_DEFINITIONS) - 2
        assert "list_skills" in tool_names
