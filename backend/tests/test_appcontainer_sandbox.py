"""Tests for appcontainer_sandbox.py — provisioning for the AppContainer
sandbox backend (the one that actually runs Node.js and Pillow; see the
module docstring for why the Windows-account backend can't).

The raw ctypes AppContainer/CreateProcess primitives
(appcontainer_sid_string, and code_exec._create_appcontainer_process) are
NOT unit-tested here — they were validated live against a real Windows
AppContainer profile, the same way code_exec.py's _create_sandboxed_process
is validated live rather than mocked at the ctypes level (Win32 structures
and raw DLL calls don't mock cleanly, and creating a real AppContainer
profile is explicitly not something to do inside an automated test). What
IS tested: the orchestration logic above that primitive — configured-check
logic, provisioning step ordering, error propagation, idempotency — by
mocking appcontainer_sid_string() and the icacls-grant functions as black
boxes, mirroring test_sandbox_account.py's approach to
_grant_folder_access/_add_firewall_block_rule.
"""
import types

import pytest

import appcontainer_sandbox as acs


class TestAppcontainerConfigured:
    def test_false_when_sid_unavailable(self, monkeypatch):
        def boom():
            raise acs.AppContainerError("no profile")
        monkeypatch.setattr(acs, "appcontainer_sid_string", boom)
        assert acs.appcontainer_configured() is False

    def test_false_when_marker_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(acs, "appcontainer_sid_string", lambda: "S-1-15-2-FAKE")
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)
        assert acs.appcontainer_configured() is False

    def test_false_when_marker_present_but_sid_mismatched(self, monkeypatch, tmp_path):
        # A stale marker from a DIFFERENT SID (e.g. re-derived after the
        # profile was deleted and recreated) must not be trusted.
        monkeypatch.setattr(acs, "appcontainer_sid_string", lambda: "S-1-15-2-CURRENT")
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)
        (tmp_path / acs._SETUP_MARKER_NAME).write_text("S-1-15-2-OLD", encoding="utf-8")
        assert acs.appcontainer_configured() is False

    def test_true_when_marker_matches_current_sid(self, monkeypatch, tmp_path):
        monkeypatch.setattr(acs, "appcontainer_sid_string", lambda: "S-1-15-2-CURRENT")
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)
        (tmp_path / acs._SETUP_MARKER_NAME).write_text("S-1-15-2-CURRENT", encoding="utf-8")
        assert acs.appcontainer_configured() is True


def _stub_grants(monkeypatch):
    """Black-boxes every grant step so provision tests exercise ORDERING
    and ERROR PROPAGATION without touching real icacls/ctypes calls."""
    calls = []
    monkeypatch.setattr(acs, "appcontainer_sid_string", lambda: "S-1-15-2-FAKE")
    monkeypatch.setattr(acs, "_sid_object", lambda s: f"sidobj({s})")
    monkeypatch.setattr(acs, "_grant_python_interpreter_access", lambda sid: calls.append(("python", sid)))
    monkeypatch.setattr(acs, "_grant_node_access", lambda sid: calls.append(("node", sid)))
    import sandbox_account
    monkeypatch.setattr(
        sandbox_account, "_grant_folder_access",
        lambda path, sid, read_only=False: calls.append(("folder", path, sid, read_only)),
    )
    return calls


class TestProvisionAppcontainerSandbox:
    def test_happy_path_grants_everything_and_writes_marker(self, monkeypatch, tmp_path):
        calls = _stub_grants(monkeypatch)
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)

        result = acs.provision_appcontainer_sandbox()

        assert result == {"success": True, "error": None}
        assert ("python", "sidobj(S-1-15-2-FAKE)") in calls
        assert ("node", "sidobj(S-1-15-2-FAKE)") in calls
        assert any(c[0] == "folder" and c[1] == tmp_path and c[3] is False for c in calls)
        marker = tmp_path / acs._SETUP_MARKER_NAME
        assert marker.read_text(encoding="utf-8") == "S-1-15-2-FAKE"

    def test_folder_grant_is_read_write_not_read_only(self, monkeypatch, tmp_path):
        # The workspace root needs write access (sandboxed code produces
        # files there) — unlike the Python/Node interpreter grants, which
        # are read-only.
        calls = _stub_grants(monkeypatch)
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)

        acs.provision_appcontainer_sandbox()

        folder_call = next(c for c in calls if c[0] == "folder")
        assert folder_call[3] is False  # read_only=False

    def test_failure_in_sid_resolution_is_reported_not_raised(self, monkeypatch):
        def boom():
            raise acs.AppContainerError("HRESULT failure")
        monkeypatch.setattr(acs, "appcontainer_sid_string", boom)

        result = acs.provision_appcontainer_sandbox()

        assert result["success"] is False
        assert "HRESULT failure" in result["error"]

    def test_failure_in_folder_grant_is_reported_not_raised(self, monkeypatch, tmp_path):
        _stub_grants(monkeypatch)
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)
        import sandbox_account

        def raise_grant(*a, **kw):
            raise RuntimeError("icacls failed")

        monkeypatch.setattr(sandbox_account, "_grant_folder_access", raise_grant)

        result = acs.provision_appcontainer_sandbox()

        assert result["success"] is False
        assert "icacls failed" in result["error"]

    def test_marker_not_written_on_partial_failure(self, monkeypatch, tmp_path):
        # The marker is the ONE signal appcontainer_configured() trusts —
        # it must not exist if an earlier step never completed.
        _stub_grants(monkeypatch)
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)
        import sandbox_account

        def raise_grant(*a, **kw):
            raise RuntimeError("icacls failed")

        monkeypatch.setattr(sandbox_account, "_grant_folder_access", raise_grant)

        acs.provision_appcontainer_sandbox()

        assert not (tmp_path / acs._SETUP_MARKER_NAME).exists()

    def test_grants_happen_before_marker_is_written(self, monkeypatch, tmp_path):
        calls = _stub_grants(monkeypatch)
        monkeypatch.setattr("sandbox_manager.code_exec_dir", lambda: tmp_path)

        acs.provision_appcontainer_sandbox()

        # All three grant calls recorded before the marker check below runs —
        # if the marker existed without them having fired, order was wrong.
        assert len(calls) == 3
        assert (tmp_path / acs._SETUP_MARKER_NAME).exists()


class TestGrantPythonInterpreterAccess:
    def test_grants_read_only_access_to_the_python_install_dir(self, monkeypatch):
        import sandbox_account
        calls = []
        monkeypatch.setattr(sandbox_account, "_grant_folder_access",
                            lambda path, sid, read_only=False: calls.append((path, read_only)))

        acs._grant_python_interpreter_access(object())

        assert len(calls) == 1
        assert calls[0][1] is True  # read_only

    def test_failure_is_caught_and_logged_not_raised(self, monkeypatch):
        import sandbox_account

        def raise_grant(*a, **kw):
            raise RuntimeError("access denied")

        monkeypatch.setattr(sandbox_account, "_grant_folder_access", raise_grant)

        acs._grant_python_interpreter_access(object())  # must not raise


class TestGrantNodeAccess:
    def test_noop_when_node_not_installed(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        import sandbox_account
        calls = []
        monkeypatch.setattr(sandbox_account, "_grant_folder_access", lambda *a, **kw: calls.append(1))

        acs._grant_node_access(object())

        assert calls == []

    def test_grants_read_only_access_when_node_is_installed(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: r"C:\Program Files\nodejs\node.exe")
        import sandbox_account
        calls = []
        monkeypatch.setattr(sandbox_account, "_grant_folder_access",
                            lambda path, sid, read_only=False: calls.append((path, read_only)))

        acs._grant_node_access(object())

        assert len(calls) == 1
        assert calls[0][1] is True  # read_only

    def test_failure_is_caught_and_logged_not_raised(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: r"C:\nodejs\node.exe")
        import sandbox_account

        def raise_grant(*a, **kw):
            raise RuntimeError("access denied")

        monkeypatch.setattr(sandbox_account, "_grant_folder_access", raise_grant)

        acs._grant_node_access(object())  # must not raise
