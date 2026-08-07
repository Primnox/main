"""Tests for project_context.py — pure local I/O, zero LLM calls.

Covers the two things most likely to silently rot: editor-title parsing (the
gate that replaces the old broken `"electron" in process` check that also
matched Slack/Discord) and the fixed-width `git status --porcelain` parser
that previously truncated the first dirty file by one character.
"""

import subprocess
import time

import pytest

from project_context import parse_editor_title, resolve_project, _find_file_under, _git_info


# ── Editor title parsing ─────────────────────────────────────────────────────


class TestParseEditorTitle:
    def test_vscode_dirty(self):
        result = parse_editor_title("● server.py - Primnox - Visual Studio Code", "Code.exe")
        assert result == {
            "file_name": "server.py",
            "project_name": "Primnox",
            "dirty": True,
            "editor": "vscode",
        }

    def test_vscode_clean(self):
        result = parse_editor_title("server.py - Primnox - Visual Studio Code", "Code.exe")
        assert result["dirty"] is False
        assert result["file_name"] == "server.py"
        assert result["project_name"] == "Primnox"

    def test_vscode_no_file_open(self):
        assert parse_editor_title("Visual Studio Code", "Code.exe") is None

    def test_cursor(self):
        result = parse_editor_title("main.py - myproject - Cursor", "Cursor.exe")
        assert result["editor"] == "cursor"
        assert result["file_name"] == "main.py"

    def test_pycharm_endash(self):
        result = parse_editor_title("server.py – Primnox – PyCharm", "pycharm64.exe")
        assert result["editor"] == "pycharm"
        assert result["file_name"] == "server.py"
        assert result["project_name"] == "Primnox"

    def test_slack_returns_none(self):
        # Slack is Electron-based, same as VS Code — the old
        # `process.lower() in [..., "electron"]` check matched it too.
        assert parse_editor_title("Slack | general | Primnox Team", "slack.exe") is None

    def test_discord_returns_none(self):
        assert parse_editor_title("Discord", "Discord.exe") is None

    def test_empty_title(self):
        assert parse_editor_title("", "Code.exe") is None

    def test_unrecognised_editor(self):
        assert parse_editor_title("notes.txt - Notepad", "notepad.exe") is None


# ── git status --porcelain parsing ──────────────────────────────────────────


class TestGitInfo(object):
    def test_dirty_files_not_truncated(self, tmp_path):
        # Regression test: `.strip()` on the full multi-line porcelain output
        # used to eat the leading space off line 1 only, shifting the fixed
        # `line[3:]` slice and silently dropping the first character of the
        # first filename (e.g. "backend/x.py" -> "ackend/x.py").
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

        (tmp_path / "backend").mkdir()
        target = tmp_path / "backend" / "cleanup_manager.py"
        target.write_text("x = 1")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        # Staged, not committed, so porcelain reports a leading-space status.
        info = _git_info(tmp_path)

        assert info["is_repo"] is True
        assert any(f.endswith("cleanup_manager.py") and f.startswith("backend")
                   for f in info["dirty_files"]), info["dirty_files"]

    def test_not_a_repo(self, tmp_path):
        info = _git_info(tmp_path)
        assert info == {"is_repo": False, "branch": None, "dirty_files": [], "last_commit": None}


# ── Root resolution ───────────────────────────────────────────────────────────


class TestFindFileUnder:
    def test_terminates_quickly_on_a_directory_with_no_matches(self, tmp_path):
        # Regression test: root.rglob(file_name) was capped on MATCHES found,
        # not entries visited, so a large directory containing zero matches
        # (the common case — most candidates tried during resolution are
        # wrong) walked its entire subtree with no bound. Build a directory
        # a bit deeper/wider than any realistic single scan and confirm the
        # walk stays bounded and fast regardless.
        for i in range(50):
            d = tmp_path / f"dir{i}"
            d.mkdir()
            for j in range(20):
                (d / f"file{j}.txt").write_text("x")

        start = time.time()
        found = _find_file_under(tmp_path, "does_not_exist.py", max_visited=200)
        elapsed = time.time() - start

        assert found is False
        assert elapsed < 2.0

    def test_finds_a_real_match(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "target.py").write_text("x")
        assert _find_file_under(tmp_path, "target.py") is True


class TestResolveProject:
    def test_returns_none_rather_than_guess_when_nothing_confirms(self, monkeypatch):
        # Regression test: with no project_name (single file opened, no
        # workspace folder) and no pid, resolve_project used to fall back to
        # "the first plausible candidate anyway" — which for an editor
        # process often resolves to the editor's own install directory, not
        # the user's project. Feeding that to the triage LLM is worse than
        # feeding it nothing.
        assert resolve_project("some_file.py", "", pid=None) is None
