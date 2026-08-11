"""Tests for sandbox_account.py — the one-time provisioning of a dedicated,
low-privileged Windows account used to run sandboxed code. All Win32/keyring
calls are mocked via sys.modules substitution (matching the existing
fake_keyring pattern in test_custom_providers.py) — creating a real Windows
account is explicitly NOT something to do inside an automated test, per the
plan's verification section.
"""
import sys
import types

import pytest

import sandbox_account


@pytest.fixture
def fake_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}

    class FakeKeyring:
        @staticmethod
        def set_password(service, username, password):
            store[(service, username)] = password

        @staticmethod
        def get_password(service, username):
            return store.get((service, username))

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    return store


def _fake_win32net(monkeypatch, existing_users: set[str] = frozenset()):
    def get_info(server, username, level):
        if username not in existing_users:
            raise Exception(f"user {username} not found")
        return {}

    added = []

    def add_user(server, level, user_info):
        added.append(user_info)
        existing_users.add(user_info["name"]) if isinstance(existing_users, set) else None

    fake = types.SimpleNamespace(NetUserGetInfo=get_info, NetUserAdd=add_user, NetUserSetInfo=lambda *a: None)
    monkeypatch.setitem(sys.modules, "win32net", fake)
    return fake, added


class TestAccountExists:
    def test_true_when_lookup_succeeds(self, monkeypatch):
        _fake_win32net(monkeypatch, existing_users={"PrimnoxSandbox"})
        assert sandbox_account.account_exists("PrimnoxSandbox") is True

    def test_false_when_lookup_raises(self, monkeypatch):
        _fake_win32net(monkeypatch, existing_users=set())
        assert sandbox_account.account_exists("PrimnoxSandbox") is False


class TestSandboxAccountConfigured:
    def test_false_when_account_missing(self, monkeypatch, fake_keyring):
        _fake_win32net(monkeypatch, existing_users=set())
        assert sandbox_account.sandbox_account_configured() is False

    def test_false_when_account_exists_but_no_password_stored(self, monkeypatch, fake_keyring):
        _fake_win32net(monkeypatch, existing_users={sandbox_account.SANDBOX_USERNAME})
        assert sandbox_account.sandbox_account_configured() is False

    def test_true_when_both_account_and_password_present(self, monkeypatch, fake_keyring):
        _fake_win32net(monkeypatch, existing_users={sandbox_account.SANDBOX_USERNAME})
        fake_keyring[(sandbox_account.KEYRING_SERVICE, sandbox_account.SANDBOX_USERNAME)] = "some-password"
        assert sandbox_account.sandbox_account_configured() is True

    def test_false_on_keyring_error(self, monkeypatch):
        _fake_win32net(monkeypatch, existing_users={sandbox_account.SANDBOX_USERNAME})

        class BrokenKeyring:
            @staticmethod
            def get_password(*a):
                raise RuntimeError("keyring backend unavailable")

        monkeypatch.setitem(sys.modules, "keyring", BrokenKeyring)
        assert sandbox_account.sandbox_account_configured() is False


class TestProvisionSandboxAccountRequiresElevation:
    def test_refuses_when_not_elevated(self, monkeypatch):
        monkeypatch.setattr(sandbox_account, "_is_elevated", lambda: False)
        result = sandbox_account.provision_sandbox_account()
        assert result["success"] is False
        assert "elevated" in result["error"]

    def test_proceeds_when_elevated(self, monkeypatch, fake_keyring, tmp_path):
        monkeypatch.setattr(sandbox_account, "_is_elevated", lambda: True)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)  # _code_exec_dir() must not touch the real home dir
        _fake_win32net(monkeypatch, existing_users=set())

        sid_obj = object()
        rights_calls = []
        fake_win32security = types.SimpleNamespace(
            LookupAccountName=lambda *a: (sid_obj, "DOMAIN", 1),
            LsaOpenPolicy=lambda *a: object(),
            LsaAddAccountRights=lambda policy, sid, rights: rights_calls.append(rights),
            POLICY_CREATE_ACCOUNT=1,
            POLICY_LOOKUP_NAMES=2,
        )
        monkeypatch.setitem(sys.modules, "win32security", fake_win32security)
        monkeypatch.setitem(sys.modules, "win32api", types.SimpleNamespace(GetUserName=lambda: "testuser"))
        monkeypatch.setitem(sys.modules, "win32netcon", types.SimpleNamespace(
            USER_PRIV_USER=1, UF_DONT_EXPIRE_PASSWD=0x10000, UF_NORMAL_ACCOUNT=0x200,
        ))
        monkeypatch.setattr(sandbox_account, "_grant_folder_access", lambda *a: None)
        monkeypatch.setattr(sandbox_account, "_add_firewall_block_rule", lambda *a: None)

        result = sandbox_account.provision_sandbox_account()

        assert result["success"] is True
        assert fake_keyring[(sandbox_account.KEYRING_SERVICE, sandbox_account.SANDBOX_USERNAME)]
        # Regression: LOGON32_LOGON_BATCH (what code_exec.py's LogonUser call
        # uses) fails outright unless SeBatchLogonRight is explicitly granted —
        # ordinary accounts don't have it by default. Confirmed via a live
        # run_python smoke test that failed with "Logon failure: the user has
        # not been granted the requested logon type at this computer." before
        # this was added.
        assert "SeDenyInteractiveLogonRight" in rights_calls[0]
        assert ["SeBatchLogonRight"] in rights_calls
        # Regression: CreateProcessAsUser also needs these on the CALLER's
        # own token (the real user, not the sandbox account) — confirmed
        # live that even a fully elevated admin token lacked
        # SeAssignPrimaryTokenPrivilege before this grant existed.
        assert ["SeAssignPrimaryTokenPrivilege", "SeIncreaseQuotaPrivilege"] in rights_calls

    def test_failure_in_any_step_is_reported_not_raised(self, monkeypatch, fake_keyring):
        monkeypatch.setattr(sandbox_account, "_is_elevated", lambda: True)
        _fake_win32net(monkeypatch, existing_users=set())

        def broken_lookup(*a):
            raise RuntimeError("account lookup failed")

        monkeypatch.setitem(sys.modules, "win32security", types.SimpleNamespace(LookupAccountName=broken_lookup))
        monkeypatch.setitem(sys.modules, "win32netcon", types.SimpleNamespace(
            USER_PRIV_USER=1, UF_DONT_EXPIRE_PASSWD=0x10000, UF_NORMAL_ACCOUNT=0x200,
        ))

        result = sandbox_account.provision_sandbox_account()

        assert result["success"] is False
        assert "account lookup failed" in result["error"]


class TestGrantFolderAccess:
    """Regression coverage for the subtlest live failure in this module: a
    single `icacls (OI)(CI)... /T` call appears to succeed (exit 0) but
    silently skips every FILE, because inheritance flags are only valid on
    directories and /C suppresses the per-file errors. Observed result: the
    Lib\\ directory carried the ACE while python311.dll beside it did not,
    and the sandboxed interpreter kept dying with STATUS_ACCESS_DENIED. Two
    passes are required — one inheritable (for future children), one
    flagless with /T (for children that already exist)."""

    def _run_grant(self, monkeypatch, tmp_path, read_only=False):
        monkeypatch.setattr(sandbox_account, "_sid_to_string", lambda sid: "S-1-5-21-TEST-1002")
        calls = []

        class Ok:
            returncode = 0
            stdout = ""
            stderr = ""

        import subprocess as real_subprocess
        monkeypatch.setattr(real_subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Ok())
        sandbox_account._grant_folder_access(tmp_path, object(), read_only=read_only)
        return calls

    def test_runs_two_passes(self, monkeypatch, tmp_path):
        calls = self._run_grant(monkeypatch, tmp_path)
        assert len(calls) == 2

    def test_first_pass_is_inheritable_without_recursion(self, monkeypatch, tmp_path):
        first = self._run_grant(monkeypatch, tmp_path)[0]
        grant = next(a for a in first if a.startswith("*S-1-5-21-TEST-1002:"))
        assert "(OI)(CI)" in grant
        assert "/T" not in first  # inheritance only — recursion is pass 2's job

    def test_second_pass_recurses_without_inheritance_flags(self, monkeypatch, tmp_path):
        second = self._run_grant(monkeypatch, tmp_path)[1]
        grant = next(a for a in second if a.startswith("*S-1-5-21-TEST-1002:"))
        # Flagless is the whole point — with (OI)(CI) present icacls skips files.
        assert "(OI)" not in grant and "(CI)" not in grant
        assert "/T" in second
        assert "/C" in second  # don't abort on the first locked file

    def test_read_only_grants_rx_not_modify(self, monkeypatch, tmp_path):
        calls = self._run_grant(monkeypatch, tmp_path, read_only=True)
        grants = [a for c in calls for a in c if a.startswith("*S-1-5-21-TEST-1002:")]
        assert all("(RX)" in g for g in grants)
        assert not any("(M)" in g for g in grants)

    def test_writable_grants_modify(self, monkeypatch, tmp_path):
        calls = self._run_grant(monkeypatch, tmp_path, read_only=False)
        grants = [a for c in calls for a in c if a.startswith("*S-1-5-21-TEST-1002:")]
        assert all("(M)" in g for g in grants)

    def test_failure_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sandbox_account, "_sid_to_string", lambda sid: "S-1-5-21-TEST-1002")

        class Fail:
            returncode = 1
            stdout = ""
            stderr = "access denied"

        import subprocess as real_subprocess
        monkeypatch.setattr(real_subprocess, "run", lambda cmd, **kw: Fail())
        with pytest.raises(RuntimeError, match="icacls"):
            sandbox_account._grant_folder_access(tmp_path, object())


class TestGrantCallerProcessCreationRights:
    """code_exec.py's CreateProcessAsUser call needs SeAssignPrimaryToken-
    Privilege and SeIncreaseQuotaPrivilege on the CALLER's own token (the
    real logged-in user, not the sandbox account) — confirmed live that even
    a fully UAC-elevated admin token lacks SeAssignPrimaryTokenPrivilege by
    default (Windows reserves it for LOCAL SERVICE/NETWORK SERVICE)."""

    def test_grants_both_privileges_to_the_current_user(self, monkeypatch):
        sid_obj = object()
        calls = []
        fake_win32security = types.SimpleNamespace(
            LookupAccountName=lambda *a: (sid_obj, "DOMAIN", 1),
            LsaOpenPolicy=lambda *a: object(),
            LsaAddAccountRights=lambda policy, sid, rights: calls.append((sid, rights)),
            POLICY_CREATE_ACCOUNT=1,
            POLICY_LOOKUP_NAMES=2,
        )
        monkeypatch.setitem(sys.modules, "win32security", fake_win32security)
        monkeypatch.setitem(sys.modules, "win32api", types.SimpleNamespace(GetUserName=lambda: "testuser"))

        sandbox_account._grant_caller_process_creation_rights()

        assert calls == [(sid_obj, ["SeAssignPrimaryTokenPrivilege", "SeIncreaseQuotaPrivilege"])]

    def test_looks_up_the_actual_current_username(self, monkeypatch):
        captured = {}

        def fake_lookup(system, name):
            captured["name"] = name
            return (object(), "DOMAIN", 1)

        fake_win32security = types.SimpleNamespace(
            LookupAccountName=fake_lookup,
            LsaOpenPolicy=lambda *a: object(),
            LsaAddAccountRights=lambda *a: None,
            POLICY_CREATE_ACCOUNT=1,
            POLICY_LOOKUP_NAMES=2,
        )
        monkeypatch.setitem(sys.modules, "win32security", fake_win32security)
        monkeypatch.setitem(sys.modules, "win32api", types.SimpleNamespace(GetUserName=lambda: "aniketh"))

        sandbox_account._grant_caller_process_creation_rights()

        assert captured["name"] == "aniketh"


class TestAddFirewallBlockRule:
    """Regression coverage for a real bug found during live provisioning:
    netsh advfirewall's CLI doesn't actually support localuser= on this
    Windows build (absent from `netsh advfirewall firewall add rule ?`'s own
    parameter list; passing it fails with "'localuser' is not a valid
    argument for this command." regardless of whether the value is a bare
    SID or an SDDL string — confirmed live). Switched to PowerShell's
    New-NetFirewallRule -LocalUser, which does support SDDL-scoped rules.
    The orchestration test above mocks this function out entirely, so it
    never caught either issue."""

    def test_powershell_invoked_with_sddl_wrapped_sid_not_bare_sid(self, monkeypatch):
        fake_win32security = types.SimpleNamespace(ConvertSidToStringSid=lambda sid: "S-1-5-21-111-222-333-1004")
        monkeypatch.setitem(sys.modules, "win32security", fake_win32security)

        calls = []

        class FakeCompletedProcess:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return FakeCompletedProcess()

        import subprocess as real_subprocess
        monkeypatch.setattr(real_subprocess, "run", fake_run)

        sandbox_account._add_firewall_block_rule(object())

        assert calls[0][0] == "powershell"
        add_call = next(c for c in calls if "New-NetFirewallRule" in c[-1])
        script = add_call[-1]

        assert "-LocalUser 'D:(A;;" in script
        assert "S-1-5-21-111-222-333-1004" in script
        assert "-Direction Outbound" in script
        assert "-Action Block" in script

    def test_raises_when_powershell_fails(self, monkeypatch):
        fake_win32security = types.SimpleNamespace(ConvertSidToStringSid=lambda sid: "S-1-5-21-1")
        monkeypatch.setitem(sys.modules, "win32security", fake_win32security)

        import subprocess as real_subprocess

        class FailingResult:
            returncode = 1
            stdout = ""
            stderr = "some PowerShell-side failure"

        def fake_run(cmd, **kw):
            if "Remove-NetFirewallRule" in cmd[-1]:
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")
            return FailingResult()

        monkeypatch.setattr(real_subprocess, "run", fake_run)

        with pytest.raises(RuntimeError, match="firewall rule creation failed"):
            sandbox_account._add_firewall_block_rule(object())


class TestRequestElevatedProvisioning:
    def test_reports_failure_when_elevation_declined(self, monkeypatch):
        def raise_shell_execute(**kwargs):
            raise Exception("pywintypes.error: (1223, 'ShellExecuteEx', 'The operation was canceled by the user.')")

        fake_shell = types.SimpleNamespace(ShellExecuteEx=raise_shell_execute)
        monkeypatch.setitem(sys.modules, "win32comext.shell.shell", fake_shell)
        monkeypatch.setitem(sys.modules, "win32comext.shell", types.SimpleNamespace(shellcon=types.SimpleNamespace(SEE_MASK_NOCLOSEPROCESS=0x40)))
        monkeypatch.setitem(sys.modules, "win32comext.shell.shellcon", types.SimpleNamespace(SEE_MASK_NOCLOSEPROCESS=0x40))
        monkeypatch.setitem(sys.modules, "win32event", types.SimpleNamespace())
        monkeypatch.setitem(sys.modules, "win32process", types.SimpleNamespace())

        result = sandbox_account.request_elevated_provisioning()

        assert result["success"] is False
        assert "declined" in result["error"] or "failed" in result["error"]
