"""Tests for the once-a-day digest: one LLM call per calendar day (not a
continuous polling loop), gathering calendar + open tasks + recent memory.
"""
from datetime import datetime, timedelta

import pytest

import daily_digest


class _FakeSettingsStore:
    """Stand-in for settings_manager.load_settings/save_settings so tests
    never touch the real settings file."""
    def __init__(self, initial=None):
        self.data = dict(initial or {})

    def load(self):
        return dict(self.data)

    def save(self, settings):
        self.data = dict(settings)


@pytest.fixture
def settings_store(monkeypatch):
    store = _FakeSettingsStore()
    monkeypatch.setattr(daily_digest, "load_settings", store.load)
    monkeypatch.setattr(daily_digest, "save_settings", store.save)
    return store


@pytest.fixture
def no_calendar(monkeypatch):
    """_gather_context does `from skills.calendar_skill import
    CalendarIslandSkill` inline — patch it to fail cleanly like a real
    environment with no calendar configured, rather than needing real
    provider config."""
    import skills.calendar_skill as cal

    class _NoEvents:
        def _fetch_events(self):
            return []

    monkeypatch.setattr(cal, "CalendarIslandSkill", _NoEvents)


class TestGatherContext:
    def test_filters_to_recent_memories_only(self, monkeypatch, no_calendar):
        import memory
        recent = {"text": "recent thing", "timestamp": datetime.now().isoformat()}
        old = {"text": "old thing", "timestamp": (datetime.now() - timedelta(days=5)).isoformat()}
        monkeypatch.setattr(memory, "list_memories", lambda: [recent, old])
        monkeypatch.setattr("notes_manager.get_tasks", lambda: [])

        ctx = daily_digest._gather_context()
        assert ctx["memories"] == [recent]

    def test_filters_out_completed_tasks(self, monkeypatch, no_calendar):
        import memory
        monkeypatch.setattr(memory, "list_memories", lambda: [])
        done = {"text": "done task", "completed": True, "priority": "normal"}
        open_task = {"text": "open task", "completed": False, "priority": "high"}
        monkeypatch.setattr("notes_manager.get_tasks", lambda: [done, open_task])

        ctx = daily_digest._gather_context()
        assert ctx["tasks"] == [open_task]


class TestGenerateDailyDigest:
    def test_returns_none_when_nothing_to_summarize(self, monkeypatch, no_calendar):
        import memory
        monkeypatch.setattr(memory, "list_memories", lambda: [])
        monkeypatch.setattr("notes_manager.get_tasks", lambda: [])

        assert daily_digest.generate_daily_digest() is None

    def test_returns_none_when_llm_call_fails(self, monkeypatch, no_calendar):
        import memory
        monkeypatch.setattr(memory, "list_memories", lambda: [
            {"text": "worked on primnox", "timestamp": datetime.now().isoformat()}
        ])
        monkeypatch.setattr("notes_manager.get_tasks", lambda: [])

        def boom(*a, **kw):
            raise RuntimeError("model unavailable")
        monkeypatch.setattr("brain.think", boom)

        assert daily_digest.generate_daily_digest() is None

    def test_returns_text_and_saves_a_note_on_success(self, monkeypatch, tmp_path, no_calendar):
        import memory
        import notes_manager
        monkeypatch.setattr(notes_manager, "DB_PATH", tmp_path / "notes.db")
        notes_manager.init_db()

        monkeypatch.setattr(memory, "list_memories", lambda: [
            {"text": "worked on primnox", "timestamp": datetime.now().isoformat()}
        ])
        monkeypatch.setattr(notes_manager, "get_tasks", lambda: [])

        fake_resp = {"choices": [{"message": {"content": "Here's your brief for today."}}]}
        monkeypatch.setattr("brain.think", lambda *a, **kw: fake_resp)

        text = daily_digest.generate_daily_digest()
        assert text == "Here's your brief for today."
        titles = [n["title"] for n in notes_manager.get_notes()]
        assert any(t.startswith("Daily Brief:") for t in titles)


class TestMaybeRunDailyDigest:
    def test_runs_when_not_yet_run_today(self, monkeypatch, settings_store):
        monkeypatch.setattr(daily_digest, "generate_daily_digest", lambda: "today's brief")
        ran = daily_digest.maybe_run_daily_digest()
        assert ran is True
        assert settings_store.data["last_daily_digest_date"] == daily_digest._today_str()

    def test_does_not_run_twice_in_the_same_day(self, monkeypatch, settings_store):
        settings_store.data["last_daily_digest_date"] = daily_digest._today_str()
        calls = []
        monkeypatch.setattr(daily_digest, "generate_daily_digest", lambda: calls.append(1) or "brief")

        ran = daily_digest.maybe_run_daily_digest()

        assert ran is False
        assert calls == []

    def test_broadcasts_when_digest_generated(self, monkeypatch, settings_store):
        monkeypatch.setattr(daily_digest, "generate_daily_digest", lambda: "today's brief")
        received = []
        daily_digest.maybe_run_daily_digest(broadcast_callback=lambda t, p: received.append((t, p)))
        assert received[0][0] == "daily_digest"
        assert received[0][1]["text"] == "today's brief"

    def test_no_broadcast_when_nothing_to_report(self, monkeypatch, settings_store):
        monkeypatch.setattr(daily_digest, "generate_daily_digest", lambda: None)
        received = []
        ran = daily_digest.maybe_run_daily_digest(broadcast_callback=lambda t, p: received.append((t, p)))
        assert ran is False
        assert received == []
        # Still marks the day as checked, even with nothing to report, so it
        # doesn't retry generation on every hourly check for a quiet day.
        assert settings_store.data["last_daily_digest_date"] == daily_digest._today_str()
