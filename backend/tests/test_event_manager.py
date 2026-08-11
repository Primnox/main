"""Tests for event_manager.py's calendar-note link (note_id column) added
for the notes-linking feature — plus a smoke test for the CRUD path it
extends, since no test file existed for this module before."""
import pytest

import memory
import event_manager as events


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test_events.db")
    memory.init_db()
    events.init_events_table()
    return events


class TestNoteLink:
    def test_create_event_with_note_id(self, db):
        ev = db.create_event({
            "title": "Standup", "start_dt": "2026-01-01T09:00:00", "end_dt": "2026-01-01T09:30:00",
            "note_id": 42,
        })
        assert ev["note_id"] == 42

    def test_create_event_without_note_id_defaults_none(self, db):
        ev = db.create_event({
            "title": "Standup", "start_dt": "2026-01-01T09:00:00", "end_dt": "2026-01-01T09:30:00",
        })
        assert ev["note_id"] is None

    def test_update_event_sets_note_id(self, db):
        ev = db.create_event({
            "title": "Standup", "start_dt": "2026-01-01T09:00:00", "end_dt": "2026-01-01T09:30:00",
        })
        updated = db.update_event(ev["id"], {"note_id": 7})
        assert updated["note_id"] == 7

    def test_update_event_without_note_id_preserves_existing(self, db):
        ev = db.create_event({
            "title": "Standup", "start_dt": "2026-01-01T09:00:00", "end_dt": "2026-01-01T09:30:00",
            "note_id": 7,
        })
        updated = db.update_event(ev["id"], {"title": "Standup (renamed)"})
        assert updated["note_id"] == 7
        assert updated["title"] == "Standup (renamed)"

    def test_list_events_includes_note_id(self, db):
        db.create_event({
            "title": "Standup", "start_dt": "2026-01-01T09:00:00", "end_dt": "2026-01-01T09:30:00",
            "note_id": 7,
        })
        [ev] = db.list_events()
        assert ev["note_id"] == 7
