"""Tests for the memory write/read path: topic/provenance tagging,
provenance-aware staleness decay, and the zero-token access-count scoring.
"""
from datetime import datetime, timedelta

import pytest

import memory


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Point memory.py at a throwaway DB so tests never touch the real one."""
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test_memory.db")
    memory.init_db()
    return memory


class TestAddMemory:
    def test_defaults_to_explicit_provenance(self, db):
        db.add_memory("user likes dark mode")
        [mem] = db.list_memories()
        assert mem["provenance"] == "explicit"
        assert mem["topic"] is None
        assert mem["access_count"] == 0

    def test_invalid_provenance_falls_back_to_explicit(self, db):
        db.add_memory("some fact", provenance="made_up_value")
        [mem] = db.list_memories()
        assert mem["provenance"] == "explicit"

    def test_stores_topic(self, db):
        db.add_memory("fixed the build", category="session", topic="project:primnox", provenance="inferred_screen")
        [mem] = db.list_memories()
        assert mem["topic"] == "project:primnox"
        assert mem["provenance"] == "inferred_screen"

    def test_dedup_still_scoped_per_category(self, db):
        db.add_memory("prefers dark mode", category="personal")
        added = db.add_memory("prefers dark mode", category="personal")
        assert added is False
        assert len(db.list_memories()) == 1

    def test_dedup_does_not_cross_categories(self, db):
        db.add_memory("prefers dark mode", category="personal")
        added = db.add_memory("prefers dark mode", category="work")
        assert added is True
        assert len(db.list_memories()) == 2

    def test_key_collision_retries_instead_of_crashing(self, db, monkeypatch):
        """Regression test: found via concurrency stress testing that
        add_memory()'s key (sha256 of text+timestamp) could collide when two
        threads wrote near-identical text at the same microsecond — raising
        UNIQUE constraint failed and, worse, leaving the cached connection
        mid-transaction. Fixed by salting the key with random.random() and
        retrying on collision. This forces a first-attempt collision
        deterministically (frozen clock + a fixed random draw matching a
        pre-existing row) and confirms the retry recovers cleanly."""
        import hashlib

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 1, 1, 0, 0, 0)

        fixed_ts = "2026-01-01T00:00:00"
        colliding_random = 0.5
        pre_existing_key = hashlib.sha256(f"new text{fixed_ts}{colliding_random}".encode()).hexdigest()

        conn = db.get_db()
        conn.execute(
            "INSERT INTO memories (key, text, category, timestamp, stale, topic, provenance, access_count) "
            "VALUES (?, ?, ?, ?, 0, NULL, 'explicit', 0)",
            (pre_existing_key, "an unrelated existing row", "work", fixed_ts),
        )
        conn.commit()

        monkeypatch.setattr(db, "datetime", _FrozenDatetime)
        random_draws = iter([colliding_random, 0.999])  # 1st collides, 2nd is fresh
        monkeypatch.setattr(db.random, "random", lambda: next(random_draws))

        added = db.add_memory("new text", category="work")

        assert added is True
        texts = {m["text"] for m in db.list_memories(category="work")}
        assert texts == {"an unrelated existing row", "new text"}


class TestMemoryScore:
    def test_fresher_scores_higher(self, db):
        now = datetime.now().isoformat()
        old = (datetime.now() - timedelta(days=25)).isoformat()
        assert db.memory_score(now, access_count=0) > db.memory_score(old, access_count=0)

    def test_access_count_boosts_score(self, db):
        ts = datetime.now().isoformat()
        assert db.memory_score(ts, access_count=5) > db.memory_score(ts, access_count=0)

    def test_bad_timestamp_does_not_raise(self, db):
        db.memory_score("not-a-date", access_count=0)


class TestMarkStaleMemories:
    def _insert_raw(self, db, text, category, provenance, age_days, access_count=0):
        # get_db() now returns a long-lived, shared per-thread connection —
        # closing it here would break every subsequent call in the test.
        conn = db.get_db()
        c = conn.cursor()
        ts = (datetime.now() - timedelta(days=age_days)).isoformat()
        c.execute(
            "INSERT INTO memories (key, text, category, timestamp, stale, topic, provenance, access_count) "
            "VALUES (?, ?, ?, ?, 0, NULL, ?, ?)",
            (text, text, category, ts, provenance, access_count),
        )
        conn.commit()

    def test_explicit_survives_past_inferred_cutoff(self, db):
        # 15 days old: past the inferred cutoff (10) but well within explicit's (30).
        self._insert_raw(db, "explicit fact", "personal", "explicit", age_days=15)
        self._insert_raw(db, "inferred guess", "session", "inferred_chat", age_days=15)

        flagged = db.mark_stale_memories()

        assert flagged == 1
        remaining = {m["text"] for m in db.list_memories()}
        assert "explicit fact" in remaining
        assert "inferred guess" not in remaining

    def test_frequently_recalled_memory_earns_grace(self, db):
        # 15 days old, inferred (base cutoff 10) — but recalled 10x buys 20 extra days.
        self._insert_raw(db, "popular guess", "session", "inferred_screen", age_days=15, access_count=10)

        flagged = db.mark_stale_memories()

        assert flagged == 0
        assert db.list_memories()[0]["text"] == "popular guess"

    def test_stale_rows_excluded_from_default_list(self, db):
        self._insert_raw(db, "old guess", "session", "inferred_chat", age_days=20)
        db.mark_stale_memories()
        assert db.list_memories() == []
        assert len(db.list_memories(include_stale=True)) == 1


class TestSearchMemories:
    def test_search_increments_access_count(self, db):
        db.add_memory("the sky is blue and vast", category="personal")
        db.search_memories("sky blue")
        [mem] = db.list_memories()
        assert mem["access_count"] == 1


class TestCorrectLastInferredMemory:
    """'No, that's wrong' should undo the single most recent guess Primnox
    made about the user — never something the user stated themselves."""

    def test_nothing_to_correct_initially(self, db):
        assert db.correct_last_inferred_memory() is None

    def test_corrects_an_inferred_memory(self, db):
        db.add_memory("might be a night owl based on activity", provenance="inferred_chat")
        corrected = db.correct_last_inferred_memory()
        assert corrected == "might be a night owl based on activity"
        assert db.list_memories() == []

    def test_does_not_target_explicit_memories(self, db):
        db.add_memory("user's name is Aniketh", provenance="explicit")
        assert db.correct_last_inferred_memory() is None
        assert len(db.list_memories()) == 1

    def test_can_only_correct_once(self, db):
        db.add_memory("guess about a hobby", provenance="inferred_screen")
        assert db.correct_last_inferred_memory() == "guess about a hobby"
        assert db.correct_last_inferred_memory() is None

    def test_targets_the_most_recent_inferred_memory(self, db):
        db.add_memory("older guess", provenance="inferred_chat")
        db.add_memory("newer guess", provenance="inferred_screen")
        corrected = db.correct_last_inferred_memory()
        assert corrected == "newer guess"
        remaining = [m["text"] for m in db.list_memories()]
        assert remaining == ["older guess"]

    def test_an_explicit_memory_after_an_inferred_one_clears_the_target(self, db):
        # If the user states something explicitly after Primnox's guess, "no
        # that's wrong" shouldn't reach past it to correct the older guess —
        # tracking is last-memory-added, not last-inferred-memory-ever.
        db.add_memory("a guess", provenance="inferred_chat")
        db.add_memory("an explicit fact", provenance="explicit")
        assert db.correct_last_inferred_memory() is None


class TestDeleteMemory:
    """delete_memory() backs the "forget X" voice command. It used to only
    match WHERE key = ? OR text = ? — both exact — so a lowercased,
    trigger-stripped phrase like "wifi password" never equaled the original
    mixed-case, full-sentence memory text, and "forget" silently deleted
    nothing."""

    def test_forget_matches_case_insensitively_by_substring(self, db):
        db.add_memory("The WiFi Password Is Hunter2", category="personal")
        db.delete_memory("wifi password")
        assert db.list_memories() == []

    def test_delete_by_exact_key_still_works(self, db):
        db.add_memory("some fact", category="work")
        [mem] = db.list_memories()
        db.delete_memory(mem["key"])
        assert db.list_memories() == []

    def test_no_match_leaves_memories_untouched(self, db):
        db.add_memory("keep me around", category="work")
        db.delete_memory("totally unrelated phrase")
        assert len(db.list_memories()) == 1


class TestConnectionReuse:
    """get_db() used to open+close a brand-new sqlite3 connection (re-running
    PRAGMA journal_mode=WAL) on every single call — real, measured overhead
    at scale. It now caches one connection per thread instead."""

    def test_get_db_returns_the_same_object_across_calls(self, db):
        assert db.get_db() is db.get_db()

    def test_reset_forces_a_new_connection(self, db):
        first = db.get_db()
        db._reset_db_connection()
        second = db.get_db()
        assert first is not second

    def test_reset_is_safe_to_call_with_no_cached_connection(self, db):
        db._reset_db_connection()
        db._reset_db_connection()  # should not raise on a second, no-op call

    def test_init_db_picks_up_a_changed_db_path(self, tmp_path, monkeypatch):
        # This is the scenario connection caching could silently break: if
        # init_db() didn't drop the cached connection, a test (or a real
        # vault unlock) pointing DB_PATH at a new file would keep talking to
        # the old one instead.
        monkeypatch.setattr(memory, "DB_PATH", tmp_path / "first.db")
        memory.init_db()
        memory.add_memory("lives in the first db", category="personal")

        monkeypatch.setattr(memory, "DB_PATH", tmp_path / "second.db")
        memory.init_db()

        assert memory.list_memories() == []
        memory.add_memory("lives in the second db", category="personal")
        assert len(memory.list_memories()) == 1

    def test_connection_survives_a_manual_close_by_reopening(self, db):
        # Simulates local_vault.py's flow: something external rewrites the
        # file on disk, then explicitly resets the cache so the next access
        # reopens fresh instead of operating on stale/closed state.
        db.add_memory("before reset", category="personal")
        db._reset_db_connection()
        # A fresh connection to the same (unchanged) file should see the same data.
        assert len(db.list_memories()) == 1
        db.add_memory("after reset", category="personal")
        assert len(db.list_memories()) == 2
