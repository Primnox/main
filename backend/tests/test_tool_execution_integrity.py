"""Heavy tests for TOOL EXECUTION integrity.

Three properties, each of which has a plausible silent-failure mode:

  27. SELECTION   — a request to produce a real artifact must reach a real
                    file/exec tool, not be answered with prose that merely
                    *looks* like a file.
  28. FAILURE     — when a tool fails, the REAL error text has to reach the
                    model so it can recover or explain. A failure that is
                    swallowed produces the worst outcome: a cheerful "Done!"
                    over a no-op.
  29. VERIFICATION— a tool (or skill) claiming it wrote a file must be checked
                    against the filesystem. reportlab and python-pptx both
                    return normally for a document that was never written, so
                    "no exception" is not evidence of success.

Deterministic throughout — requests.post is stubbed, code_exec is stubbed, and
all paths point at tmp_path. The live counterpart (does a real model actually
pick the right tool?) lives in test_e2e_pdf_to_pptx_pipeline.py.
"""
import json
from pathlib import Path

import pytest

import brain
import code_exec
import settings_manager
import tools


# ── harness ──────────────────────────────────────────────────────────────────

def _settings(monkeypatch, **overrides):
    base = {
        "active_model": "Groq_Llama_3",
        "groq_api_key": "sk-fake",
        "privacy_mirror_enabled": False,
        "code_execution_enabled": True,
    }
    base.update(overrides)
    monkeypatch.setattr(settings_manager, "load_settings", lambda: base)
    monkeypatch.setattr(brain, "get_api_key", lambda provider: "sk-fake")
    monkeypatch.setattr(brain, "get_groq_api_key", lambda: "sk-fake")
    return base


class _ScriptedProvider:
    """Replays a scripted list of assistant messages, recording every payload
    it was sent — so a test can assert what the model SAW on the turn after a
    tool ran."""

    status_code = 200
    headers: dict = {}
    text = ""

    def __init__(self, replies):
        self._replies = list(replies)
        self.payloads = []

    def __call__(self, url, headers=None, json=None, timeout=None, stream=None):
        self.payloads.append(json)
        return self

    def json(self):
        msg = self._replies.pop(0) if self._replies else {"content": "", "tool_calls": None}
        return {"choices": [{"message": msg}]}

    def iter_lines(self):
        return iter(())

    def tool_messages(self):
        """Every role=tool message across every request — i.e. exactly what
        tool output the model was fed."""
        out = []
        for p in self.payloads:
            for m in p.get("messages", []):
                if m.get("role") == "tool":
                    out.append(m)
        return out


def _tool_call(name, args):
    return {
        "content": None,
        "tool_calls": [{"id": f"call_{name}", "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)}}],
    }


def _sentinels(tokens, prefix):
    return [json.loads(t[len(prefix):]) for t in tokens if t.startswith(prefix)]


# ── 27. Tool selection ───────────────────────────────────────────────────────

class TestRealFileCreatingToolIsOffered:
    """"Create a file containing this data" can only be honoured by a tool that
    actually touches the filesystem. These assert such a tool exists, is
    offered, and genuinely executes — the prerequisites for a model to pick it
    instead of typing out a fake file."""

    def test_a_real_execution_tool_exists_in_the_tool_list(self):
        names = {t["function"]["name"] for t in tools.TOOL_DEFINITIONS}
        assert {"run_python", "run_shell"} <= names, (
            "no tool can create a real file — the model's only option is to "
            "fabricate file contents in prose"
        )

    def test_the_execution_tools_are_offered_for_a_file_creation_request(
            self, monkeypatch):
        _settings(monkeypatch, code_execution_enabled=True)
        provider = _ScriptedProvider([{"content": "sure", "tool_calls": None}])
        monkeypatch.setattr(brain.requests, "post", provider)

        list(brain.think_stream("Create a file containing this data: a,b,c\n1,2,3"))

        offered = {t["function"]["name"] for t in provider.payloads[0]["tools"]}
        assert "run_python" in offered
        assert provider.payloads[0]["tool_choice"] == "auto"

    def test_tool_descriptions_tell_the_model_they_produce_real_output(self):
        by_name = {t["function"]["name"]: t["function"] for t in tools.TOOL_DEFINITIONS}
        for name in ("run_python", "run_shell"):
            desc = by_name[name]["description"].lower()
            assert "sandbox" in desc
            assert "output" in desc or "run" in desc

    def test_a_selected_execution_tool_actually_reaches_code_exec(self, monkeypatch):
        """Selection is worthless if dispatch is broken: prove the call lands
        in code_exec rather than being answered by a stub."""
        _settings(monkeypatch, code_execution_enabled=True)
        seen = {}

        def fake_run_python(code, session_id="", **kw):
            seen["code"] = code
            return {"success": True, "return_code": 0, "stdout": "wrote data.csv",
                    "stderr": "", "files_created": ["data.csv"]}

        monkeypatch.setattr(code_exec, "run_python", fake_run_python)

        result = tools.execute_tool(
            "run_python",
            {"code": "open('data.csv','w').write('a,b,c\\n1,2,3')"},
            session_id="s1",
        )

        assert "data.csv" in seen["code"]
        assert "files created: data.csv" in result

    def test_a_fabricated_tool_name_is_refused_not_silently_accepted(
            self, monkeypatch):
        """A model that invents `write_file` must not have it quietly treated
        as a success — the loop skips unknown names, and execute_tool itself
        reports the miss."""
        _settings(monkeypatch, code_execution_enabled=True)
        provider = _ScriptedProvider([
            _tool_call("write_file", {"path": "data.csv", "content": "a,b,c"}),
            {"content": "I could not do that", "tool_calls": None},
        ])
        monkeypatch.setattr(brain.requests, "post", provider)

        tokens = list(brain.think_stream("Create a file containing this data"))

        assert not _sentinels(tokens, "[[TOOL_RESULT]]"), (
            "an unregistered tool name produced a tool result — the model's "
            "hallucinated tool appeared to succeed"
        )
        assert tools.execute_tool("write_file", {}) == "Error: Tool 'write_file' not found."

    def test_execution_tools_are_withheld_when_disabled(self, monkeypatch):
        """The counterpart: with execution off, the model must not be offered a
        file-creating tool it would then be blocked from using."""
        _settings(monkeypatch, code_execution_enabled=False)
        provider = _ScriptedProvider([{"content": "ok", "tool_calls": None}])
        monkeypatch.setattr(brain.requests, "post", provider)

        list(brain.think_stream("Create a file containing this data"))

        offered = {t["function"]["name"] for t in provider.payloads[0]["tools"]}
        assert "run_python" not in offered and "run_shell" not in offered


# ── 28. Tool failure surfaces the REAL error ────────────────────────────────

FAILURE_TEXT = "Error executing tool: PermissionError: [Errno 13] Permission denied: 'C:/data.csv'"


class TestToolFailureReachesTheModel:
    def test_the_real_error_text_is_fed_back_to_the_model(self, monkeypatch):
        _settings(monkeypatch, code_execution_enabled=True)
        provider = _ScriptedProvider([
            _tool_call("run_python", {"code": "open('C:/data.csv','w')"}),
            {"content": "I couldn't write that file — permission denied.", "tool_calls": None},
        ])
        monkeypatch.setattr(brain.requests, "post", provider)
        monkeypatch.setattr(brain, "execute_tool",
                            lambda name, args, session_id=None: FAILURE_TEXT)

        list(brain.think_stream("Create a file containing this data"))

        fed = [m["content"] for m in provider.tool_messages()]
        assert fed, "the model was never told the tool ran at all"
        assert any("Permission denied" in c for c in fed), (
            f"the real error never reached the model; it saw: {fed}"
        )
        assert any("PermissionError" in c for c in fed), (
            "the exception type was stripped — the model cannot diagnose it"
        )

    def test_the_error_is_not_replaced_by_a_generic_placeholder(self, monkeypatch):
        _settings(monkeypatch, code_execution_enabled=True)
        provider = _ScriptedProvider([
            _tool_call("run_python", {"code": "boom"}),
            {"content": "that failed", "tool_calls": None},
        ])
        monkeypatch.setattr(brain.requests, "post", provider)
        monkeypatch.setattr(brain, "execute_tool",
                            lambda name, args, session_id=None: FAILURE_TEXT)

        list(brain.think_stream("run it"))

        fed = " ".join(m["content"] for m in provider.tool_messages())
        for placeholder in ("tool failed", "an error occurred", "success", "done"):
            assert placeholder not in fed.lower() or "denied" in fed.lower(), (
                f"tool output was flattened to a placeholder: {fed!r}"
            )

    def test_a_failing_tool_still_lets_the_conversation_continue(self, monkeypatch):
        """Recovery path: after seeing the error the model gets another turn,
        and its explanation is what the user receives."""
        _settings(monkeypatch, code_execution_enabled=True)
        provider = _ScriptedProvider([
            _tool_call("run_python", {"code": "boom"}),
            {"content": "I hit a permission error and could not create the file.",
             "tool_calls": None},
        ])
        monkeypatch.setattr(brain.requests, "post", provider)
        monkeypatch.setattr(brain, "execute_tool",
                            lambda name, args, session_id=None: FAILURE_TEXT)

        out = "".join(t for t in brain.think_stream("make it") if not t.startswith("[["))

        assert "permission error" in out.lower()
        assert "done!" not in out.lower()

    def test_the_failure_is_surfaced_to_the_ui_not_only_to_the_model(
            self, monkeypatch):
        _settings(monkeypatch, code_execution_enabled=True)
        provider = _ScriptedProvider([
            _tool_call("run_python", {"code": "boom"}),
            {"content": "failed", "tool_calls": None},
        ])
        monkeypatch.setattr(brain.requests, "post", provider)
        monkeypatch.setattr(brain, "execute_tool",
                            lambda name, args, session_id=None: FAILURE_TEXT)

        tokens = list(brain.think_stream("make it"))

        results = _sentinels(tokens, "[[TOOL_RESULT]]")
        assert results, "no tool result was emitted for the UI"
        assert "Permission denied" in results[0]["output"]

    def test_execute_tool_converts_an_exception_into_a_readable_error(
            self, monkeypatch):
        """The boundary that guarantees the above: no tool may raise out of
        execute_tool, and the message must survive."""
        def exploding(*a, **kw):
            raise RuntimeError("disk is on fire")

        monkeypatch.setattr(tools, "web_search", exploding)
        result = tools.execute_tool("web_search", {"query": "x"})

        assert "disk is on fire" in result
        assert result.startswith("Error executing tool")

    def test_code_exec_error_is_passed_through_verbatim(self, monkeypatch):
        monkeypatch.setattr(code_exec, "run_python",
                            lambda code, session_id="", **kw: {"error": "sandbox account not provisioned"})
        result = tools.execute_tool("run_python", {"code": "print(1)"}, session_id="s")
        assert result == "sandbox account not provisioned"

    def test_a_nonzero_exit_is_reported_with_its_stderr(self, monkeypatch):
        monkeypatch.setattr(code_exec, "run_python", lambda code, session_id="", **kw: {
            "success": False, "return_code": 1, "stdout": "",
            "stderr": "Traceback...\nZeroDivisionError: division by zero",
            "files_created": [],
        })
        result = tools.execute_tool("run_python", {"code": "1/0"}, session_id="s")

        assert "exit code: 1" in result
        assert "ZeroDivisionError" in result
        assert "files created" not in result

    def test_a_timeout_is_reported_rather_than_looking_like_a_clean_run(
            self, monkeypatch):
        monkeypatch.setattr(code_exec, "run_python", lambda code, session_id="", **kw: {
            "success": False, "return_code": -1, "stdout": "partial", "stderr": "",
            "timed_out": True, "files_created": [],
        })
        result = tools.execute_tool("run_python", {"code": "while True: pass"}, session_id="s")
        assert "timed out" in result

    def test_a_very_large_error_is_truncated_but_still_marked_as_truncated(self):
        huge = "E" * (brain._TOOL_ECHO_MAX_CHARS + 5000)
        sentinel = json.loads(brain._tool_result_sentinel("run_python", huge)[len("[[TOOL_RESULT]]"):])
        assert sentinel["truncated"] is True
        assert "more chars" in sentinel["output"]


# ── 29. Tool result verification ────────────────────────────────────────────

class TestClaimedFileIsVerifiedAgainstDisk:
    """A claim of "file created" must be checked. python-pptx and reportlab
    both return normally without writing anything under the right conditions,
    so the check has to be an explicit filesystem probe."""



    def test_sandboxed_render_rejects_a_run_that_produced_no_artifact(
            self, tmp_path, monkeypatch):
        """The sandbox reports exit code 0, but the promised file is not there.
        render_in_sandbox must not move on as if it were."""
        from skills import sandboxed_render
        import sandbox_manager

        monkeypatch.setattr(sandbox_manager, "code_exec_dir", lambda: tmp_path)
        monkeypatch.setattr(code_exec, "run_python", lambda script, session_id="", **kw: {
            "success": True, "return_code": 0, "stdout": "wrote out.pdf",
            "stderr": "", "sandbox_id": "run1", "files_created": ["out.pdf"],
        })
        (tmp_path / "run1").mkdir()   # session dir exists, artifact does not

        ok, err = sandboxed_render.render_in_sandbox(
            script="...", produced_filename="out.pdf",
            final_path=tmp_path / "final.pdf",
        )

        assert ok is False
        assert "no output file" in err
        assert not (tmp_path / "final.pdf").exists(), (
            "a destination file was created despite the render producing nothing"
        )

    def test_sandboxed_render_rejects_a_zero_byte_artifact(
            self, tmp_path, monkeypatch):
        from skills import sandboxed_render
        import sandbox_manager

        monkeypatch.setattr(sandbox_manager, "code_exec_dir", lambda: tmp_path)
        monkeypatch.setattr(code_exec, "run_python", lambda script, session_id="", **kw: {
            "success": True, "return_code": 0, "stdout": "", "stderr": "",
            "sandbox_id": "run1", "files_created": ["out.pdf"],
        })
        (tmp_path / "run1").mkdir()
        (tmp_path / "run1" / "out.pdf").write_bytes(b"")

        ok, err = sandboxed_render.render_in_sandbox(
            script="...", produced_filename="out.pdf",
            final_path=tmp_path / "final.pdf",
        )

        assert ok is False
        assert "no output file" in err

    def test_a_genuine_artifact_is_accepted_and_moved(self, tmp_path, monkeypatch):
        """Negative control — verification must not reject real output."""
        from skills import sandboxed_render
        import sandbox_manager

        monkeypatch.setattr(sandbox_manager, "code_exec_dir", lambda: tmp_path)
        monkeypatch.setattr(code_exec, "run_python", lambda script, session_id="", **kw: {
            "success": True, "return_code": 0, "stdout": "", "stderr": "",
            "sandbox_id": "run1", "files_created": ["out.pdf"],
        })
        (tmp_path / "run1").mkdir()
        (tmp_path / "run1" / "out.pdf").write_bytes(b"%PDF-1.4 real content")

        final = tmp_path / "final.pdf"
        ok, err = sandboxed_render.render_in_sandbox(
            script="...", produced_filename="out.pdf", final_path=final)

        assert ok is True and err is None
        assert final.exists() and final.stat().st_size > 0

    def test_files_created_lists_only_files_that_exist_on_disk(self, tmp_path):
        """code_exec derives files_created by walking the directory, so it
        cannot report a file the script only claimed to write."""
        (tmp_path / "real.csv").write_text("a,b\n1,2", encoding="utf-8")

        listed = code_exec._files_created(tmp_path)

        assert listed == ["real.csv"]
        for name in listed:
            assert (tmp_path / name).exists()




class TestPermissionGateOnExecutionTools:
    """run_python/run_shell must not become a bypass for the confirm gate."""

    def test_denied_permission_yields_an_error_not_a_fabricated_success(
            self, monkeypatch):
        monkeypatch.setattr(code_exec, "run_python", lambda code, session_id="", **kw: {
            "error": "Execution cancelled — the user did not approve it."})

        result = tools.execute_tool("run_python", {"code": "print(1)"}, session_id="s")

        assert "cancelled" in result.lower()
        assert "exit code" not in result
