"""Tests for sandbox_manager.py — the shared, quota-enforced directory that
pdf_skill.py/ppt_skill.py/screenshot_skill.py write generated output into.
Replaces the previously-unbounded Documents/Primnox/Generated and
Documents/Primnox/Screenshots folders, which had no size-based cleanup."""
import time

import sandbox_manager


class TestSandboxDir:
    def test_creates_and_returns_the_sandbox_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        d = sandbox_manager.sandbox_dir()
        assert d.exists()
        assert d.is_dir()
        assert d == tmp_path / "Documents" / "Primnox" / "Sandbox"


class TestGetUsageBytes:
    def test_empty_sandbox_has_zero_usage(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert sandbox_manager.get_usage_bytes() == 0

    def test_usage_sums_all_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        d = sandbox_manager.sandbox_dir()
        (d / "a.txt").write_bytes(b"x" * 100)
        (d / "b.txt").write_bytes(b"y" * 250)
        assert sandbox_manager.get_usage_bytes() == 350


class TestEnforceQuota:
    def test_no_eviction_when_under_quota(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        d = sandbox_manager.sandbox_dir()
        (d / "a.txt").write_bytes(b"x" * 100)

        evicted = sandbox_manager.enforce_quota(quota_bytes=1000)

        assert evicted == 0
        assert (d / "a.txt").exists()

    def test_evicts_oldest_files_first_until_under_quota(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        d = sandbox_manager.sandbox_dir()

        # Write in order, giving each a distinct mtime so "oldest" is well-defined.
        (d / "oldest.txt").write_bytes(b"a" * 100)
        time.sleep(0.02)
        (d / "middle.txt").write_bytes(b"b" * 100)
        time.sleep(0.02)
        (d / "newest.txt").write_bytes(b"c" * 100)

        # Quota only fits two of the three 100-byte files.
        evicted = sandbox_manager.enforce_quota(quota_bytes=200)

        assert evicted == 1
        assert not (d / "oldest.txt").exists()
        assert (d / "middle.txt").exists()
        assert (d / "newest.txt").exists()

    def test_evicts_multiple_files_if_needed(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        d = sandbox_manager.sandbox_dir()

        for i in range(5):
            (d / f"file{i}.txt").write_bytes(b"x" * 100)
            time.sleep(0.01)

        evicted = sandbox_manager.enforce_quota(quota_bytes=150)

        assert evicted == 4
        assert sandbox_manager.get_usage_bytes() <= 150
        assert (d / "file4.txt").exists()  # the newest one survives

    def test_default_quota_is_one_gigabyte(self):
        assert sandbox_manager.DEFAULT_QUOTA_BYTES == 1 * 1024 * 1024 * 1024

    def test_protected_paths_are_never_evicted(self, tmp_path, monkeypatch):
        # The installed node_modules under runtime_dir() is thousands of files
        # all carrying install-time mtimes — i.e. the oldest thing in the
        # directory and first in line for eviction. Losing it would break the
        # pptx/docx skills with a module-not-found long after install.
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        d = sandbox_manager.sandbox_dir()
        runtime = d / "_runtime"
        runtime.mkdir()
        (runtime / "dep.js").write_bytes(b"x" * 100)
        time.sleep(0.02)
        (d / "recent_output.txt").write_bytes(b"y" * 100)

        evicted = sandbox_manager.enforce_quota(quota_bytes=50, base=d, protect=(runtime,))

        assert (runtime / "dep.js").exists()
        assert not (d / "recent_output.txt").exists()
        assert evicted == 1


class TestPruneStaleWorkspaces:
    def test_recent_workspaces_survive(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        base = sandbox_manager.code_exec_dir()
        ws = base / "ws_session-a"
        ws.mkdir()
        (ws / "deck.pptx").write_bytes(b"in progress")

        assert sandbox_manager.prune_stale_workspaces(max_age_hours=1) == 0
        assert ws.exists()

    def test_stale_workspaces_are_removed(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        base = sandbox_manager.code_exec_dir()
        ws = base / "ws_old-session"
        ws.mkdir()
        f = ws / "leftover.txt"
        f.write_bytes(b"x")
        old = time.time() - (48 * 3600)
        import os
        os.utime(f, (old, old))
        os.utime(ws, (old, old))

        assert sandbox_manager.prune_stale_workspaces(max_age_hours=24) == 1
        assert not ws.exists()

    def test_non_workspace_directories_are_left_alone(self, tmp_path, monkeypatch):
        # Throwaway session dirs and _runtime must not be swept by the
        # age-based pruner — the quota sweeper owns the former, and the
        # latter is infrastructure that is deliberately never reclaimed.
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        base = sandbox_manager.code_exec_dir()
        import os
        old = time.time() - (48 * 3600)
        for name in ("_runtime", "a1b2c3d4"):
            d = base / name
            d.mkdir()
            f = d / "thing.txt"
            f.write_bytes(b"x")
            os.utime(f, (old, old))
            os.utime(d, (old, old))

        assert sandbox_manager.prune_stale_workspaces(max_age_hours=24) == 0
        assert (base / "_runtime").exists()
        assert (base / "a1b2c3d4").exists()
