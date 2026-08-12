"""Tests for the Tasks feature (notes_manager.add_task/get_tasks/complete_task/
delete_task) — the backlog item tracking "Reminders and Tasks don't work"
(Reminders were fixed to persist to SQLite in an earlier pass; this covers
the Tasks half).

Each test gets its own on-disk SQLite file via DB_PATH monkeypatching (same
pattern as test_notes.py) rather than touching the real AppData database, so
these are safe to run against a developer's real Primnox install.
"""
import pytest

import notes_manager as notes


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, "DB_PATH", tmp_path / "test_tasks.db")
    notes.init_db()
    return notes


class TestAddTask:
    def test_returns_an_id(self, db):
        # add_note/add_reminder-style creators all return the new row's id so
        # callers (and the /tasks POST route's JSON response) can reference
        # it immediately. add_task used to omit "id" from its return value —
        # nothing currently reads it, but that's exactly the kind of "wrong
        # return shape" bug that silently breaks a future caller.
        task = db.add_task("Buy milk")
        assert task["id"] is not None
        assert isinstance(task["id"], int)

    def test_default_priority_and_completed_false(self, db):
        task = db.add_task("Buy milk")
        assert task["priority"] == "normal"
        assert task["completed"] is False
        assert task["due_date"] is None

    def test_custom_priority_and_due_date_roundtrip(self, db):
        task = db.add_task("Ship the release", priority="urgent", due_date="2026-08-20")
        assert task["priority"] == "urgent"
        assert task["due_date"] == "2026-08-20"

    def test_returned_id_matches_the_stored_row(self, db):
        task = db.add_task("Buy milk")
        [stored] = db.get_tasks()
        assert stored["id"] == task["id"]


class TestGetTasks:
    def test_empty_by_default(self, db):
        assert db.get_tasks() == []

    def test_returns_added_tasks_in_insertion_order(self, db):
        db.add_task("First")
        db.add_task("Second")
        tasks = db.get_tasks()
        assert [t["text"] for t in tasks] == ["First", "Second"]

    def test_filters_by_priority(self, db):
        db.add_task("Low prio", priority="low")
        db.add_task("Urgent prio", priority="urgent")
        results = db.get_tasks(priority="urgent")
        assert [t["text"] for t in results] == ["Urgent prio"]

    def test_completed_field_is_a_real_bool(self, db):
        db.add_task("Buy milk")
        [task] = db.get_tasks()
        assert task["completed"] is False
        assert isinstance(task["completed"], bool)


class TestCompleteTask:
    def test_marks_the_task_completed(self, db):
        created = db.add_task("Buy milk")
        assert db.complete_task(created["id"]) is True
        [task] = db.get_tasks()
        assert task["completed"] is True

    def test_returns_false_for_unknown_id(self, db):
        assert db.complete_task(999999) is False

    def test_does_not_affect_other_tasks(self, db):
        a = db.add_task("Task A")
        db.add_task("Task B")
        db.complete_task(a["id"])
        statuses = {t["text"]: t["completed"] for t in db.get_tasks()}
        assert statuses == {"Task A": True, "Task B": False}


class TestDeleteTask:
    def test_removes_the_task(self, db):
        created = db.add_task("Buy milk")
        assert db.delete_task(created["id"]) is True
        assert db.get_tasks() == []

    def test_returns_false_for_unknown_id(self, db):
        assert db.delete_task(999999) is False

    def test_only_deletes_the_targeted_task(self, db):
        a = db.add_task("Keep me")
        b = db.add_task("Delete me")
        db.delete_task(b["id"])
        remaining = db.get_tasks()
        assert [t["id"] for t in remaining] == [a["id"]]


class TestTaskPersistence:
    def test_tasks_survive_reopening_the_database(self, db):
        # Mirrors the actual "Reminders don't work" bug this backlog item was
        # modeled on: reminders used to live in an in-process dict and were
        # lost on restart. Every notes_manager call opens (get_db) and closes
        # its own sqlite3 connection per operation, so this proves tasks are
        # genuinely persisted to disk rather than held in memory somewhere.
        created = db.add_task("Survive a restart")

        # Simulate "the app restarted" by dropping any implicit connection
        # state and re-reading straight from disk via a fresh connection.
        conn = db.get_db()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (created["id"],)).fetchone()
        finally:
            conn.close()

        assert row is not None
        assert row["text"] == "Survive a restart"
        assert row["completed"] == 0
