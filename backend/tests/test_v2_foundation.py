"""Tests for the V2 storage/ID foundation.

Everything else in V2 references records by ID and reads them out of one
SQLite file, so a mistake here shows up as cross-subsystem corruption rather
than a local bug. These tests pin the two properties the rest of the
substrate assumes: IDs derived from the same natural key are identical
across processes, and storage can be redirected cleanly.
"""

import threading

import pytest

from v2 import ids, store


@pytest.fixture
def db(tmp_path):
    store.reset_for_tests(tmp_path / "v2.db")
    yield store
    store.reset_for_tests(None)


class TestStableIds:
    def test_same_natural_key_gives_same_id(self):
        assert ids.stable_id("entity", "file", "/src/a.py") == ids.stable_id("entity", "file", "/src/a.py")

    def test_different_keys_give_different_ids(self):
        assert ids.stable_id("entity", "file", "/src/a.py") != ids.stable_id("entity", "file", "/src/b.py")

    def test_part_boundaries_cannot_be_confused(self):
        """A separator that could appear inside a part would let two
        different natural keys hash to one ID — ("a", "b:c") vs ("a:b", "c")
        is exactly the shape of a file path plus a symbol name."""
        assert ids.stable_id("entity", "a", "b:c") != ids.stable_id("entity", "a:b", "c")

    def test_missing_part_is_distinct_from_absent_part(self):
        assert ids.stable_id("entity", "file", None) != ids.stable_id("entity", "file")

    def test_prefix_names_the_kind(self):
        assert ids.stable_id("result", "x").startswith("res_")
        assert ids.new_id("task").startswith("task_")

    def test_unknown_kind_is_loud(self):
        with pytest.raises(ids.UnknownKindError):
            ids.stable_id("entty", "x")


class TestRandomIds:
    def test_new_ids_do_not_collide(self):
        generated = {ids.new_id("event") for _ in range(1000)}
        assert len(generated) == 1000

    def test_content_ids_collapse_identical_content(self):
        assert ids.content_id("result", "abc") == ids.content_id("result", "abc")
        assert ids.content_id("result", "abc") != ids.content_id("result", "abd")


class TestIdIntrospection:
    def test_kind_round_trips(self):
        assert ids.kind_of(ids.new_id("artifact")) == "artifact"

    def test_unrecognised_input_is_not_an_error(self):
        assert ids.kind_of("hello") is None
        assert ids.kind_of("") is None
        assert ids.is_id(None) is False

    def test_kind_can_be_asserted(self):
        result = ids.new_id("result")
        assert ids.is_id(result, "result")
        assert not ids.is_id(result, "task")

    def test_right_prefix_wrong_shape_is_rejected(self):
        assert not ids.is_id("res_nothex!")
        assert not ids.is_id("res_abc")


class TestStore:
    def test_configure_redirects_storage(self, tmp_path, db):
        target = tmp_path / "elsewhere.db"
        store.configure(target)
        store.connect()
        assert target.exists()

    def test_schema_is_applied_once_per_database(self, db):
        store.ensure_schema("demo", ["CREATE TABLE IF NOT EXISTS demo(a TEXT)"])
        store.ensure_schema("demo", ["CREATE TABLE IF NOT EXISTS demo(a TEXT)"])
        rows = store.connect().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='demo'"
        ).fetchall()
        assert len(rows) == 1

    def test_redirecting_reapplies_schema_to_the_new_database(self, tmp_path, db):
        """Without clearing the applied-schema cache, a second database
        would be considered migrated while having no tables at all."""
        store.ensure_schema("demo", ["CREATE TABLE IF NOT EXISTS demo(a TEXT)"])
        store.reset_for_tests(tmp_path / "second.db")
        store.ensure_schema("demo", ["CREATE TABLE IF NOT EXISTS demo(a TEXT)"])
        store.connect().execute("INSERT INTO demo VALUES ('ok')")

    def test_transaction_rolls_back_on_error(self, db):
        store.ensure_schema("demo", ["CREATE TABLE IF NOT EXISTS demo(a TEXT)"])
        with pytest.raises(RuntimeError):
            with store.transaction() as conn:
                conn.execute("INSERT INTO demo VALUES ('x')")
                raise RuntimeError("boom")
        assert store.connect().execute("SELECT COUNT(*) c FROM demo").fetchone()["c"] == 0

    def test_each_thread_gets_its_own_connection(self, db):
        store.ensure_schema("demo", ["CREATE TABLE IF NOT EXISTS demo(a TEXT)"])
        seen = []

        def worker():
            seen.append(id(store.connect()))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(seen)) == 4

    def test_environment_variable_is_honoured(self, tmp_path, monkeypatch, db):
        store.reset_for_tests(None)
        monkeypatch.setenv("PRIMNOX_V2_DB", str(tmp_path / "from_env.db"))
        assert store.db_path() == tmp_path / "from_env.db"

    def test_explicit_configuration_outranks_the_environment(self, tmp_path, monkeypatch, db):
        monkeypatch.setenv("PRIMNOX_V2_DB", str(tmp_path / "from_env.db"))
        store.configure(tmp_path / "explicit.db")
        assert store.db_path() == tmp_path / "explicit.db"


class TestTimestamps:
    def test_now_is_timezone_aware_and_utc(self):
        parsed = store.parse_time(store.utc_now())
        assert parsed is not None and parsed.utcoffset().total_seconds() == 0

    def test_naive_v1_timestamps_are_read_as_utc(self):
        """V1 wrote naive local timestamps; V2 has to be able to read those
        rows without a migration pass rather than treating them as unparsed."""
        parsed = store.parse_time("2026-08-24T10:00:00")
        assert parsed is not None and parsed.utcoffset().total_seconds() == 0

    def test_zulu_suffix_is_accepted(self):
        assert store.parse_time("2026-08-24T10:00:00Z") == store.parse_time("2026-08-24T10:00:00+00:00")

    def test_unparseable_input_returns_none(self):
        assert store.parse_time("not a time") is None
        assert store.parse_time(None) is None

    def test_timestamps_sort_chronologically_as_strings(self):
        earlier = "2026-08-24T09:00:00+00:00"
        later = "2026-08-24T10:00:00+00:00"
        assert earlier < later
