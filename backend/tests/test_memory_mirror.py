"""Tests for the Markdown memory mirror: topic grouping/slugging, the
scrub-at-write privacy boundary, and orphaned-file cleanup.

Git commits run for real against a tmp_path repo (git init accepts inline
-c user.name/email, so it needs no global git config) rather than being
mocked — the audit trail is the point of this feature, worth checking it
actually commits.
"""
import pytest

import memory
import memory_mirror


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test_memory.db")
    memory.init_db()
    return memory


@pytest.fixture
def mirror_dir(tmp_path, monkeypatch):
    d = tmp_path / "Memory"
    monkeypatch.setattr(memory_mirror, "MEMORY_DIR", d)
    return d


@pytest.fixture
def force_cloud_mode(monkeypatch):
    """render_memory_mirror() checks load_settings() to decide whether to
    scrub; default to a cloud model so scrubbing is exercised unless a test
    overrides it."""
    monkeypatch.setattr(memory_mirror, "load_settings", lambda: {"active_model": "Groq_Llama_3"})


class TestSlugAndTitle:
    def test_slug_sanitizes_special_chars(self):
        assert memory_mirror._slug("Project: Primnox!!") == "project-primnox"

    def test_slug_empty_falls_back_to_misc(self):
        assert memory_mirror._slug("###") == "misc"

    def test_topic_key_prefers_topic_over_category(self):
        mem = {"topic": "project:primnox", "category": "session"}
        assert memory_mirror._topic_key(mem) == "project:primnox"

    def test_topic_key_falls_back_to_category(self):
        mem = {"topic": None, "category": "personal"}
        assert memory_mirror._topic_key(mem) == "personal"

    def test_topic_title_formats_namespaced_topic(self):
        assert memory_mirror._topic_title("project:primnox") == "Project: Primnox"


class TestRenderMemoryMirror:
    def test_writes_one_file_per_topic(self, db, mirror_dir, force_cloud_mode):
        db.add_memory("fixed the theme bug", category="session", topic="project:primnox")
        db.add_memory("prefers dark mode", category="personal")

        count = memory_mirror.render_memory_mirror()

        assert count == 2
        assert (mirror_dir / "project-primnox.md").exists()
        assert (mirror_dir / "personal.md").exists()

    def test_orders_by_score_within_topic(self, db, mirror_dir, force_cloud_mode):
        db.add_memory("older fact", category="work")
        db.search_memories("nonexistent")  # no-op, just exercising the path
        db.add_memory("recalled fact", category="work")
        # Bump access_count on "recalled fact" so it should sort first despite being newer-only-by-a-hair.
        db.search_memories("recalled")

        memory_mirror.render_memory_mirror()

        text = (mirror_dir / "work.md").read_text(encoding="utf-8")
        assert text.index("recalled fact") < text.index("older fact")

    def test_removes_orphaned_topic_file(self, db, mirror_dir, force_cloud_mode):
        mirror_dir.mkdir(parents=True)
        (mirror_dir / "ghost-topic.md").write_text("# stale\n", encoding="utf-8")
        db.add_memory("still here", category="personal")

        memory_mirror.render_memory_mirror()

        assert not (mirror_dir / "ghost-topic.md").exists()
        assert (mirror_dir / "personal.md").exists()

    def test_inferred_memory_tagged_as_guess(self, db, mirror_dir, force_cloud_mode):
        db.add_memory("might be using VS Code a lot", category="session", provenance="inferred_screen")

        memory_mirror.render_memory_mirror()

        text = (mirror_dir / "session.md").read_text(encoding="utf-8")
        assert "correct me if wrong" in text

    def test_explicit_memory_not_tagged_as_guess(self, db, mirror_dir, force_cloud_mode):
        db.add_memory("I use VS Code", category="session", provenance="explicit")

        memory_mirror.render_memory_mirror()

        text = (mirror_dir / "session.md").read_text(encoding="utf-8")
        assert "correct me if wrong" not in text

    def test_commits_to_git(self, db, mirror_dir, force_cloud_mode):
        db.add_memory("a fact worth remembering", category="personal")

        memory_mirror.render_memory_mirror()

        assert (mirror_dir / ".git").exists()
        log = memory_mirror._run_git(["log", "--oneline"], mirror_dir)
        assert log.returncode == 0
        assert "sync 1 memories" in log.stdout

    def test_full_local_skips_scrubbing(self, db, mirror_dir, monkeypatch):
        monkeypatch.setattr(memory_mirror, "load_settings", lambda: {"active_model": "Ollama_Local"})
        calls = []
        monkeypatch.setattr("privacy_mirror.redact_text", lambda t: calls.append(t) or t)

        db.add_memory("contact jane@example.com", category="personal")
        memory_mirror.render_memory_mirror()

        assert calls == []

    def test_cloud_mode_invokes_scrub(self, db, mirror_dir, force_cloud_mode, monkeypatch):
        calls = []

        def fake_redact(t):
            calls.append(t)
            return "[SCRUBBED]"

        monkeypatch.setattr("privacy_mirror.redact_text", fake_redact)
        db.add_memory("contact jane@example.com", category="personal")

        memory_mirror.render_memory_mirror()

        assert calls == ["contact jane@example.com"]
        text = (mirror_dir / "personal.md").read_text(encoding="utf-8")
        assert "[SCRUBBED]" in text
