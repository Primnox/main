"""Regression test for a real bug found live: reminder_manager.py and
event_manager.py both import memory.get_db() — the long-lived, per-thread
cached connection — but used to call conn.close() after every use, a
leftover from before that connection became shared. Closing it poisoned
memory._thread_local.conn for the rest of that OS thread's lifetime (the
cache only checks `is None`, not whether the cached connection is closed),
so every later call to memory.get_db() on that thread raised
"Cannot operate on a closed database" — including from completely
unrelated code (list_memories, dashboard) sharing the same thread. This
took the whole backend down in production during live testing.
"""
import pytest

import memory
import event_manager
import reminder_manager


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test_memory.db")
    memory.init_db()
    return memory


def test_event_manager_does_not_close_the_shared_connection(db):
    event_manager.init_events_table()
    conn = memory.get_db()
    # A closed connection raises ProgrammingError on any use.
    conn.execute("SELECT 1")

    event_manager.create_event({
        "title": "test", "start_dt": "2026-01-01T00:00:00", "end_dt": "2026-01-01T01:00:00",
    })
    memory.get_db().execute("SELECT 1")

    events = event_manager.list_events()
    assert len(events) == 1
    memory.get_db().execute("SELECT 1")


def test_reminder_manager_does_not_close_the_shared_connection(db):
    reminder_manager.init_reminders_table()
    memory.get_db().execute("SELECT 1")

    reminder_manager._db_insert("id-1", "test reminder", 9999999999.0)
    memory.get_db().execute("SELECT 1")

    pending = reminder_manager._db_list_pending()
    assert len(pending) == 1
    memory.get_db().execute("SELECT 1")

    reminder_manager._db_prune()
    memory.get_db().execute("SELECT 1")


def test_unrelated_memory_calls_survive_after_event_and_reminder_use(db):
    """The actual failure mode observed live: a totally unrelated caller
    (list_memories, via a FastAPI dashboard endpoint) shared the same OS
    thread as event_manager/reminder_manager and started failing too,
    because the poisoned connection is process-wide per-thread state."""
    event_manager.init_events_table()
    reminder_manager.init_reminders_table()

    memory.add_memory("some fact")
    assert len(memory.list_memories()) == 1
