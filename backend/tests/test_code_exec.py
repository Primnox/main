"""Tests for code_exec.py. The real Win32 process-creation primitive
(_create_sandboxed_process — LogonUser + CreateProcessAsUser under the
sandbox account) is isolated into its own function specifically so the
surrounding orchestration logic here — permission gating, session
directories, quota enforcement, result formatting — is testable by mocking
that one call, without needing a real second Windows account in every test
run. See test_sandbox_account.py for the account-provisioning side, and the
plan's verification section for how the actual OS-level boundary gets
checked (with the user's explicit go-ahead, against a real account).
"""
import sys
import time
import types

import pytest

import code_exec
import permission_manager
import sandbox_account


@pytest.fixture(autouse=True)
def _reset_permission_state():
    with permission_manager._lock:
        permission_manager._pending.clear()
    yield


class TestMinimalEnv:
    def test_only_allowlisted_vars_present(self, monkeypatch):
        monkeypatch.setenv("SystemRoot", r"C:\Windows")
        monkeypatch.setenv("PATH", r"C:\Windows\System32")
        monkeypatch.setenv("GROQ_API_KEY", "sk-should-not-leak")
        monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")

        env = code_exec._minimal_env()

        assert "GROQ_API_KEY" not in env
        assert "APPDATA" not in env
        assert env["SystemRoot"] == r"C:\Windows"

    def test_comspec_defaults_when_unset(self, monkeypatch):
        monkeypatch.delenv("COMSPEC", raising=False)
        env = code_exec._minimal_env()
        assert env["COMSPEC"] == r"C:\Windows\System32\cmd.exe"

    def test_comspec_preserved_when_set(self, monkeypatch):
        monkeypatch.setenv("COMSPEC", r"D:\custom\cmd.exe")
        env = code_exec._minimal_env()
        assert env["COMSPEC"] == r"D:\custom\cmd.exe"


class TestFilesCreated:
    def test_empty_dir_returns_empty_list(self, tmp_path):
        assert code_exec._files_created(tmp_path) == []

    def test_lists_files_relative_to_session_dir(self, tmp_path):
        (tmp_path / "result.csv").write_text("a,b\n1,2")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.txt").write_text("x")

        files = code_exec._files_created(tmp_path)

        assert "result.csv" in files
        assert str(__import__("pathlib").Path("sub") / "nested.txt") in files

    def test_directories_are_not_listed_as_files(self, tmp_path):
        (tmp_path / "empty_subdir").mkdir()
        assert code_exec._files_created(tmp_path) == []

    def test_excluded_names_are_omitted(self, tmp_path):
        (tmp_path / "script.py").write_text("print(1)")
        (tmp_path / "output.txt").write_text("done")

        files = code_exec._files_created(tmp_path, exclude=frozenset({"script.py"}))

        assert files == ["output.txt"]

    def test_staged_skill_files_are_never_reported(self, tmp_path):
        # The docx/pptx/xlsx skills stage ~1.1 MB of bundled scripts and OOXML
        # schemas into the workspace. Reporting those as output would bury the
        # one artifact the user asked for under 50+ irrelevant filenames.
        (tmp_path / "skill" / "scripts").mkdir(parents=True)
        (tmp_path / "skill" / "scripts" / "thumbnail.py").write_text("x")
        (tmp_path / "deck.pptx").write_text("real output")

        assert code_exec._files_created(tmp_path) == ["deck.pptx"]

    def test_reused_workspace_reports_only_files_this_run_touched(self, tmp_path):
        # A workspace persists across steps, so without diffing against a
        # pre-run snapshot every step would re-report every earlier step's
        # output as newly created.
        (tmp_path / "from_step_one.txt").write_text("old")
        before = code_exec._snapshot(tmp_path)

        (tmp_path / "from_step_two.txt").write_text("new")

        assert code_exec._files_created(tmp_path, before=before) == ["from_step_two.txt"]

    def test_a_modified_existing_file_counts_as_created(self, tmp_path):
        target = tmp_path / "deck.pptx"
        target.write_text("v1")
        before = code_exec._snapshot(tmp_path)

        time.sleep(0.01)  # mtime_ns must actually differ
        target.write_text("v2 — rewritten by this step")

        assert code_exec._files_created(tmp_path, before=before) == ["deck.pptx"]


class TestWorkspaceDir:
    def test_same_id_returns_the_same_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)

        _, first = code_exec._workspace_dir("session-abc")
        (first / "artifact.txt").write_text("step one output")
        _, second = code_exec._workspace_dir("session-abc")

        assert first == second
        assert (second / "artifact.txt").read_text() == "step one output"

    def test_different_ids_get_different_directories(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)

        _, a = code_exec._workspace_dir("session-a")
        _, b = code_exec._workspace_dir("session-b")

        assert a != b

    def test_path_traversal_in_the_id_cannot_escape_the_base(self, tmp_path, monkeypatch):
        # workspace_id originates from a chat session id. A caller passing
        # traversal must not be able to steer execution — or the quota
        # sweeper's rmtree — outside CodeExecution.
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)

        _, d = code_exec._workspace_dir("../../Windows/System32")

        assert d.resolve().parent == tmp_path.resolve()
        assert ".." not in d.name

    def test_id_with_no_usable_characters_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)
        with pytest.raises(ValueError):
            code_exec._workspace_dir("../..")


class TestTruncate:
    def test_short_text_unchanged(self):
        assert code_exec._truncate("hello") == "hello"

    def test_long_text_is_truncated_with_marker(self):
        text = "x" * (code_exec.MAX_OUTPUT_CHARS + 500)
        result = code_exec._truncate(text)
        assert len(result) < len(text)
        assert "truncated" in result


class TestBuildCommand:
    def test_python_writes_script_and_returns_command(self, tmp_path):
        cmd = code_exec._build_command("python", "print('hi')", tmp_path)
        assert (tmp_path / "script.py").read_text(encoding="utf-8") == "print('hi')"
        assert "script.py" in cmd

    def test_shell_is_wrapped_in_cmd_exe(self, tmp_path):
        # CreateProcessAsUser runs a command line directly with no shell, so
        # a bare command gets no redirects, pipes, chaining or builtins —
        # `echo hi > out.txt && dir` resolved `echo` to an unrelated echo.exe
        # on PATH and passed the rest through as literal argv (confirmed
        # live). Wrapping in cmd.exe /c is what makes shell syntax work.
        cmd = code_exec._build_command("shell", "dir /b", tmp_path)
        assert "cmd.exe" in cmd.lower()
        assert "/c" in cmd
        assert "dir /b" in cmd

    def test_node_writes_script_js_and_invokes_node(self, tmp_path, monkeypatch):
        # pptxgenjs and docx-js have no Python equivalent, so a Python-only
        # sandbox can only describe the official pptx/docx skills, not run them.
        monkeypatch.setattr(code_exec.shutil, "which", lambda name: r"C:\node\node.exe")

        cmd = code_exec._build_command("node", "require('pptxgenjs')", tmp_path)

        assert (tmp_path / "script.js").read_text(encoding="utf-8") == "require('pptxgenjs')"
        assert "node.exe" in cmd
        assert "script.js" in cmd

    def test_node_without_node_installed_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(code_exec.shutil, "which", lambda name: None)
        with pytest.raises(ValueError, match="node"):
            code_exec._build_command("node", "console.log(1)", tmp_path)

    def test_unknown_language_raises(self, tmp_path):
        with pytest.raises(ValueError):
            code_exec._build_command("ruby", "puts 1", tmp_path)


class TestNodePath:
    def test_node_path_points_at_the_shared_runtime(self, monkeypatch, tmp_path):
        # The sandbox account cannot read this user's global npm root (it's
        # under AppData by design), so require('pptxgenjs') fails without an
        # explicit NODE_PATH no matter what's installed.
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)

        env = code_exec._minimal_env()

        assert env["NODE_PATH"] == str(tmp_path / "_runtime" / "node_modules")


class TestEnableOwnPrivileges:
    """SeAssignPrimaryTokenPrivilege/SeIncreaseQuotaPrivilege come from local
    Administrators-group membership, but UAC strips them entirely from a
    normal, non-elevated process token — confirmed live: CreateProcessAsUser
    failed with 'A required privilege is not held by the client.' when
    Primnox's backend ran unelevated. AdjustTokenPrivileges itself never
    raises for a missing privilege, so the only signal is GetLastError()."""

    def _fake_modules(self, monkeypatch, last_errors):
        calls = []
        errors = iter(last_errors)

        class FakeToken:
            def __init__(self):
                self.closed = False

            def Close(self):
                self.closed = True

        fake_token = FakeToken()
        fake_win32security = types.SimpleNamespace(
            OpenProcessToken=lambda proc, access: fake_token,
            LookupPrivilegeValue=lambda system, name: name,
            AdjustTokenPrivileges=lambda token, disable_all, privs: calls.append(privs),
            SE_PRIVILEGE_ENABLED=2,
        )
        fake_win32api = types.SimpleNamespace(
            GetCurrentProcess=lambda: object(),
            GetLastError=lambda: next(errors),
        )
        fake_win32con = types.SimpleNamespace(TOKEN_ADJUST_PRIVILEGES=0x20, TOKEN_QUERY=0x8)
        fake_winerror = types.SimpleNamespace(ERROR_NOT_ALL_ASSIGNED=1300)

        monkeypatch.setitem(sys.modules, "win32security", fake_win32security)
        monkeypatch.setitem(sys.modules, "win32api", fake_win32api)
        monkeypatch.setitem(sys.modules, "win32con", fake_win32con)
        monkeypatch.setitem(sys.modules, "winerror", fake_winerror)
        return calls, fake_token

    def test_enables_all_requested_privileges(self, monkeypatch):
        calls, fake_token = self._fake_modules(monkeypatch, last_errors=[0, 0])
        code_exec._enable_own_privileges(("SeAssignPrimaryTokenPrivilege", "SeIncreaseQuotaPrivilege"))
        assert len(calls) == 2
        assert fake_token.closed is True

    def test_raises_sandbox_privilege_error_when_privilege_missing(self, monkeypatch):
        self._fake_modules(monkeypatch, last_errors=[1300])  # ERROR_NOT_ALL_ASSIGNED
        with pytest.raises(code_exec.SandboxPrivilegeError, match="SeAssignPrimaryTokenPrivilege"):
            code_exec._enable_own_privileges(("SeAssignPrimaryTokenPrivilege",))

    def test_error_message_mentions_administrator(self, monkeypatch):
        self._fake_modules(monkeypatch, last_errors=[1300])
        with pytest.raises(code_exec.SandboxPrivilegeError, match="administrator"):
            code_exec._enable_own_privileges(("SeIncreaseQuotaPrivilege",))

    def test_token_closed_even_when_privilege_missing(self, monkeypatch):
        _calls, fake_token = self._fake_modules(monkeypatch, last_errors=[1300])
        with pytest.raises(code_exec.SandboxPrivilegeError):
            code_exec._enable_own_privileges(("SeAssignPrimaryTokenPrivilege",))
        assert fake_token.closed is True


def _configure_sandbox(monkeypatch, ready: bool = True):
    monkeypatch.setattr(sandbox_account, "sandbox_account_configured", lambda: ready)
    monkeypatch.setattr(code_exec, "sandbox_account_configured", lambda: ready)


def _auto_allow_permission(monkeypatch):
    monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: True)


def _auto_deny_permission(monkeypatch):
    monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: False)


class TestRunOrchestration:
    def test_not_configured_short_circuits_before_permission_check(self, monkeypatch):
        _configure_sandbox(monkeypatch, ready=False)
        prompted = []
        monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: prompted.append(kw) or True)

        result = code_exec._run("python", "print(1)")

        assert result["success"] is False
        assert "not set up" in result["error"] or "Settings" in result["error"]
        assert prompted == []

    def test_denied_permission_stops_before_process_creation(self, monkeypatch, tmp_path):
        _configure_sandbox(monkeypatch, ready=True)
        _auto_deny_permission(monkeypatch)
        called = []
        monkeypatch.setattr(code_exec, "_create_sandboxed_process", lambda *a, **kw: called.append(1))

        result = code_exec._run("python", "print(1)")

        assert result["success"] is False
        assert "cancelled" in result["error"]
        assert called == []

    def test_permission_description_shows_the_actual_code(self, monkeypatch):
        _configure_sandbox(monkeypatch, ready=True)
        captured = {}

        def fake_request(**kw):
            captured.update(kw)
            return False

        monkeypatch.setattr(permission_manager, "request_permission", fake_request)

        code_exec._run("python", "import os; os.system('evil')")

        assert "os.system('evil')" in captured["description"]
        assert "python" in captured["description"]

    def test_successful_run_returns_structured_result(self, monkeypatch, tmp_path):
        _configure_sandbox(monkeypatch, ready=True)
        _auto_allow_permission(monkeypatch)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        def fake_create(command_line, cwd, env, timeout):
            (cwd / "output.txt").write_text("done")
            return {
                "success": True, "stdout": "hello\n", "stderr": "", "return_code": 0,
                "timed_out": False, "duration_ms": 42.0,
            }

        monkeypatch.setattr(code_exec, "_create_sandboxed_process", fake_create)

        result = code_exec.run_python("print('hello')")

        assert result["success"] is True
        assert result["stdout"] == "hello\n"
        assert result["return_code"] == 0
        # script.py (the code we wrote in) must not appear as a "created" file.
        assert result["files_created"] == ["output.txt"]
        assert "sandbox_id" in result and len(result["sandbox_id"]) == 8

    def test_script_py_never_reported_as_a_created_file(self, monkeypatch, tmp_path):
        _configure_sandbox(monkeypatch, ready=True)
        _auto_allow_permission(monkeypatch)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        monkeypatch.setattr(code_exec, "_create_sandboxed_process", lambda *a, **kw: {
            "success": True, "stdout": "", "stderr": "", "return_code": 0, "timed_out": False, "duration_ms": 1.0,
        })

        result = code_exec.run_python("print('nothing written')")

        assert result["files_created"] == []

    def test_each_call_gets_a_fresh_session_directory(self, monkeypatch, tmp_path):
        _configure_sandbox(monkeypatch, ready=True)
        _auto_allow_permission(monkeypatch)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        seen_dirs = []

        def fake_create(command_line, cwd, env, timeout):
            seen_dirs.append(cwd)
            assert list(cwd.iterdir()) == [] or all(p.name == "script.py" for p in cwd.iterdir())
            return {"success": True, "stdout": "", "stderr": "", "return_code": 0, "timed_out": False, "duration_ms": 1.0}

        monkeypatch.setattr(code_exec, "_create_sandboxed_process", fake_create)

        code_exec.run_python("print(1)")
        code_exec.run_python("print(2)")

        assert seen_dirs[0] != seen_dirs[1]

    def test_quota_enforced_after_execution(self, monkeypatch, tmp_path):
        _configure_sandbox(monkeypatch, ready=True)
        _auto_allow_permission(monkeypatch)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        monkeypatch.setattr(code_exec, "_create_sandboxed_process", lambda *a, **kw: {
            "success": True, "stdout": "", "stderr": "", "return_code": 0, "timed_out": False, "duration_ms": 1.0,
        })

        calls = []
        import sandbox_manager
        real_enforce = sandbox_manager.enforce_quota
        def spy_enforce(*a, **kw):
            calls.append(kw)
            return real_enforce(*a, **kw)
        monkeypatch.setattr(sandbox_manager, "enforce_quota", spy_enforce)

        code_exec.run_python("print(1)")

        assert len(calls) == 1
        assert calls[0]["quota_bytes"] == code_exec.CODE_EXEC_QUOTA_BYTES

    def test_run_shell_uses_shell_language(self, monkeypatch, tmp_path):
        _configure_sandbox(monkeypatch, ready=True)
        _auto_allow_permission(monkeypatch)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        captured = {}

        def fake_create(command_line, cwd, env, timeout):
            captured["command_line"] = command_line
            return {"success": True, "stdout": "", "stderr": "", "return_code": 0, "timed_out": False, "duration_ms": 1.0}

        monkeypatch.setattr(code_exec, "_create_sandboxed_process", fake_create)

        code_exec.run_shell("dir /b")

        assert "cmd.exe" in captured["command_line"].lower()
        assert "dir /b" in captured["command_line"]

    def test_privilege_error_returns_clean_dict_not_a_raise(self, monkeypatch, tmp_path):
        # If Primnox isn't running elevated, _create_sandboxed_process raises
        # SandboxPrivilegeError — this must surface as a normal {"success":
        # False, "error": ...} result (what tools.py/brain.py expect from
        # every tool call), not an unhandled exception mid tool-call loop.
        _configure_sandbox(monkeypatch, ready=True)
        _auto_allow_permission(monkeypatch)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        def raise_privilege_error(*a, **kw):
            raise code_exec.SandboxPrivilegeError(
                "SeAssignPrimaryTokenPrivilege is not available on Primnox's process "
                "token — Primnox must be running with administrator privileges for "
                "sandboxed code execution to work."
            )

        monkeypatch.setattr(code_exec, "_create_sandboxed_process", raise_privilege_error)

        result = code_exec.run_python("print(1)")

        assert result["success"] is False
        assert "administrator" in result["error"]
