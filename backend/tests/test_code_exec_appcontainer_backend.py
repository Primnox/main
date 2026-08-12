"""Tests for code_exec.py's AppContainer backend: _active_backend()
selection, _build_appcontainer_command(), and _run()'s dispatch to it.
Kept separate from test_code_exec.py so that file's existing,
Windows-account-focused orchestration tests stay hermetic (see the autouse
fixture there forcing "windows" by default) while this file exercises the
AppContainer path explicitly.

_create_appcontainer_process() itself — raw ctypes CreateProcessW with the
AppContainer security-capabilities attribute — is NOT unit-tested here,
matching how _create_sandboxed_process() has never been unit-tested either:
Win32 structures and raw DLL calls don't mock cleanly, and it was validated
live instead (see code_exec.py's module docstring and
docs/sandbox-runtime-limitations.md). What's tested: everything ABOVE that
primitive — backend selection, command construction, dispatch, output-file
exclusion — by mocking _create_appcontainer_process as a black box.
"""
import pytest

import appcontainer_sandbox
import code_exec
import permission_manager
import sandbox_account


def _configure_sandbox(monkeypatch, ready: bool = True):
    monkeypatch.setattr(sandbox_account, "sandbox_account_configured", lambda: ready)
    monkeypatch.setattr(code_exec, "sandbox_account_configured", lambda: ready)


def _auto_allow_permission(monkeypatch):
    monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: True)


@pytest.fixture(autouse=True)
def _reset_permission_state():
    with permission_manager._lock:
        permission_manager._pending.clear()


class TestActiveBackend:
    def test_appcontainer_when_configured(self, monkeypatch):
        monkeypatch.setattr(appcontainer_sandbox, "appcontainer_configured", lambda: True)
        assert code_exec._active_backend() == "appcontainer"

    def test_windows_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(appcontainer_sandbox, "appcontainer_configured", lambda: False)
        assert code_exec._active_backend() == "windows"

    def test_falls_back_to_windows_when_check_raises(self, monkeypatch):
        # A broken/partial AppContainer setup must degrade to the
        # Windows-account backend, never take code execution down entirely.
        def boom():
            raise RuntimeError("ctypes call failed")
        monkeypatch.setattr(appcontainer_sandbox, "appcontainer_configured", boom)
        assert code_exec._active_backend() == "windows"


class TestBuildAppcontainerCommand:
    def test_python_writes_script_and_a_wrapper_that_redirects_output(self, tmp_path):
        cmd = code_exec._build_appcontainer_command("python", "print('hi')", tmp_path)

        assert (tmp_path / "script.py").read_text(encoding="utf-8") == "print('hi')"
        wrapper = (tmp_path / "_ac_wrapper.py").read_text(encoding="utf-8")
        assert "sys.stdout" in wrapper and "sys.stderr" in wrapper
        assert str(tmp_path / code_exec._APPCONTAINER_STDOUT_NAME) in wrapper
        assert "_ac_wrapper.py" in cmd

    def test_python_wrapper_execs_rather_than_imports(self, tmp_path):
        # Direct-launch python.exe is confirmed live to work; using import
        # machinery (vs exec/compile on the source text) risks re-opening
        # the same module-resolution questions Node hit.
        wrapper_path = tmp_path / "_ac_wrapper.py"
        code_exec._build_appcontainer_command("python", "print(1)", tmp_path)
        wrapper = wrapper_path.read_text(encoding="utf-8")
        assert "exec(compile(" in wrapper

    def test_node_writes_script_and_a_wrapper_that_redirects_output(self, tmp_path):
        cmd = code_exec._build_appcontainer_command("node", "console.log('hi')", tmp_path)

        assert (tmp_path / "script.js").read_text(encoding="utf-8") == "console.log('hi')"
        wrapper = (tmp_path / "_ac_wrapper.js").read_text(encoding="utf-8")
        assert "process.stdout.write" in wrapper and "process.stderr.write" in wrapper
        assert "_ac_wrapper.js" in cmd

    def test_node_command_includes_preserve_symlinks_flags(self, tmp_path):
        # Confirmed live: without BOTH flags, Node's own realpath resolution
        # (of the entry module AND of the wrapper's require() of the user's
        # script) walks up to the drive root and dies with EPERM under the
        # AppContainer SID, which was never granted anything above the
        # workspace directory.
        cmd = code_exec._build_appcontainer_command("node", "console.log(1)", tmp_path)

        assert "--preserve-symlinks-main" in cmd
        assert "--preserve-symlinks " in cmd or cmd.count("--preserve-symlinks") == 2

    def test_node_writes_a_package_json_next_to_the_wrapper(self, tmp_path):
        # Stops a SEPARATE upward walk (CommonJS-vs-ESM package-scope
        # lookup) that --preserve-symlinks does not cover on its own.
        code_exec._build_appcontainer_command("node", "console.log(1)", tmp_path)
        assert (tmp_path / "package.json").exists()

    def test_shell_is_inlined_not_written_to_a_file(self, tmp_path):
        # A separate attempt to write shell code to a .bat file and invoke
        # `cmd.exe /c "{batfile}"` produced an EARLIER, more opaque failure
        # than inlining (confirmed live) — inlining was kept despite the
        # quoting trade-off, matching the Windows-account backend's own
        # accepted risk for the same language.
        cmd = code_exec._build_appcontainer_command("shell", "echo hi", tmp_path)

        assert "echo hi" in cmd
        assert not (tmp_path / "script.bat").exists()

    def test_shell_redirects_via_cmd_native_syntax(self, tmp_path):
        cmd = code_exec._build_appcontainer_command("shell", "echo hi", tmp_path)

        assert str(tmp_path / code_exec._APPCONTAINER_STDOUT_NAME) in cmd
        assert str(tmp_path / code_exec._APPCONTAINER_STDERR_NAME) in cmd

    def test_unknown_language_raises(self, tmp_path):
        with pytest.raises(ValueError):
            code_exec._build_appcontainer_command("ruby", "puts 1", tmp_path)


class TestAppcontainerCaptureNamesAreExcluded:
    def test_all_plumbing_files_are_excluded_from_files_created(self):
        for name in ("_ac_stdout.txt", "_ac_stderr.txt", "_ac_wrapper.py", "_ac_wrapper.js", "package.json"):
            assert name in code_exec._APPCONTAINER_CAPTURE_NAMES


class TestRunDispatchesToAppcontainerBackend:
    def test_appcontainer_backend_calls_build_and_create_appcontainer(self, monkeypatch, tmp_path):
        _configure_sandbox(monkeypatch, ready=True)
        _auto_allow_permission(monkeypatch)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        monkeypatch.setattr(code_exec, "_active_backend", lambda: "appcontainer")

        build_calls, run_calls = [], []
        monkeypatch.setattr(code_exec, "_build_appcontainer_command",
                            lambda *a: build_calls.append(a) or "python x")
        monkeypatch.setattr(code_exec, "_create_appcontainer_process", lambda *a, **kw: run_calls.append(a) or {
            "success": True, "stdout": "", "stderr": "", "return_code": 0,
            "timed_out": False, "duration_ms": 1.0,
        })
        # If dispatch is wrong, the Windows-only primitives would run
        # instead — fail loudly rather than silently succeeding via the
        # wrong path.
        monkeypatch.setattr(code_exec, "_build_command", lambda *a: (_ for _ in ()).throw(
            AssertionError("Windows _build_command should not run on the AppContainer path")))
        monkeypatch.setattr(code_exec, "_create_sandboxed_process", lambda *a: (_ for _ in ()).throw(
            AssertionError("Windows _create_sandboxed_process should not run on the AppContainer path")))

        result = code_exec.run_python("print(1)")

        assert result["success"] is True
        assert len(build_calls) == 1
        assert len(run_calls) == 1

    def test_windows_backend_does_not_require_appcontainer_configured(self, monkeypatch, tmp_path):
        # _run()'s gate must only demand sandbox_account_configured() when
        # the WINDOWS backend was actually selected — appcontainer_configured
        # being false must not block execution when it wasn't chosen.
        _configure_sandbox(monkeypatch, ready=True)
        _auto_allow_permission(monkeypatch)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        monkeypatch.setattr(code_exec, "_active_backend", lambda: "windows")
        monkeypatch.setattr(code_exec, "_create_sandboxed_process", lambda *a: {
            "success": True, "stdout": "", "stderr": "", "return_code": 0,
            "timed_out": False, "duration_ms": 1.0,
        })

        result = code_exec.run_python("print(1)")

        assert result["success"] is True

    def test_windows_backend_still_gated_on_sandbox_account_configured(self, monkeypatch):
        _configure_sandbox(monkeypatch, ready=False)
        monkeypatch.setattr(code_exec, "_active_backend", lambda: "windows")

        result = code_exec.run_python("print(1)")

        assert result["success"] is False
        assert "not set up" in result["error"] or "Settings" in result["error"]

    def test_files_created_and_quota_pipeline_are_backend_agnostic(self, monkeypatch, tmp_path):
        _configure_sandbox(monkeypatch, ready=True)
        _auto_allow_permission(monkeypatch)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        monkeypatch.setattr(code_exec, "_active_backend", lambda: "appcontainer")
        monkeypatch.setattr(code_exec, "_build_appcontainer_command", lambda *a: "python x")

        def fake_create(command, cwd, timeout):
            (cwd / "output.pptx").write_text("fake artifact")
            (cwd / code_exec._APPCONTAINER_STDOUT_NAME).write_text("")
            return {"success": True, "stdout": "", "stderr": "", "return_code": 0,
                    "timed_out": False, "duration_ms": 5.0}

        monkeypatch.setattr(code_exec, "_create_appcontainer_process", fake_create)

        result = code_exec.run_python("print(1)")

        assert result["files_created"] == ["output.pptx"]
        assert "sandbox_id" in result and len(result["sandbox_id"]) == 8
