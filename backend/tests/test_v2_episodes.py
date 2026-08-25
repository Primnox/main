"""Tests for episodic/temporal memory.

The scenario these exist to protect is "what was I doing yesterday?" — the
answer has to be reconstructed from timestamped evidence, grouped into
coherent episodes, and it has to keep working when no model is available to
write a prettier summary.
"""

from datetime import datetime, timedelta, timezone

import pytest

from v2 import episodes, store, world_model as wm


@pytest.fixture
def db(tmp_path):
    store.reset_for_tests(tmp_path / "v2.db")
    yield episodes
    store.reset_for_tests(None)


BASE = datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return BASE + timedelta(minutes=minutes)


def seed_debugging_session(db, project="primnox", session=None):
    """The architecture's own worked example: a run of raw events that
    should consolidate into one recognisable stretch of work."""
    file_entity = wm.upsert_entity("file", "router.py", project=project)
    script = [
        ("file_opened", "opened router.py", 0),
        ("file_read", "read router.py", 1),
        ("file_modified", "modified router.py", 4),
        ("test_failed", "test_retrieval failed", 6),
        ("file_modified", "fixed the off-by-one in router.py", 9),
        ("test_passed", "test_retrieval passed", 11),
    ]
    for kind, summary, offset in script:
        db.record_event(
            kind, summary, project=project, session=session,
            entities=[file_entity["id"]], occurred_at=at(offset),
        )
    return file_entity


class TestRecording:
    def test_an_event_carries_its_provenance_and_time(self, db):
        event = db.record_event("commit", "shipped the router", project="primnox", occurred_at=at(0))
        assert event["occurred_at"] == at(0).isoformat()
        assert event["origin"] == "observed"
        assert event["recorded_at"] >= event["occurred_at"]

    def test_importance_defaults_by_kind(self, db):
        noise = db.record_event("file_opened", "opened a.py")
        signal = db.record_event("error", "crash in router.py")
        assert signal["importance"] > noise["importance"]

    def test_importance_can_be_overridden(self, db):
        event = db.record_event("file_opened", "opened the one file that matters", importance=0.95)
        assert event["importance"] == 0.95

    def test_empty_summary_is_rejected(self, db):
        with pytest.raises(wm.ValidationError):
            db.record_event("message", "   ")

    def test_a_large_result_is_referenced_not_inlined(self, db):
        event = db.record_event("tool_run", "ran the dependency report", result_ref="res_abc123")
        assert event["result_ref"] == "res_abc123"
        assert event["detail"] is None

    def test_naive_timestamps_are_read_as_local_time(self, db):
        event = db.record_event("message", "hi", occurred_at=datetime(2026, 8, 23, 14, 0))
        assert store.parse_time(event["occurred_at"]) is not None


class TestTemporalQueries:
    def test_yesterday_is_a_local_calendar_day(self, db):
        start, end = db.local_day_bounds(1, now=datetime(2026, 8, 24, 3, 0, tzinfo=timezone.utc))
        assert start == "2026-08-23T00:00:00+00:00"
        assert end == "2026-08-24T00:00:00+00:00"

    def test_day_windows_tile_without_overlapping(self, db):
        now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
        _, yesterday_end = db.local_day_bounds(1, now=now)
        today_start, _ = db.local_day_bounds(0, now=now)
        assert yesterday_end == today_start

    def test_events_are_returned_in_the_order_they_happened(self, db):
        db.record_event("message", "second", occurred_at=at(5))
        db.record_event("message", "first", occurred_at=at(0))
        found = db.events_between(at(-1), at(10))
        assert [e["summary"] for e in found] == ["first", "second"]

    def test_the_window_end_is_exclusive(self, db):
        db.record_event("message", "on the boundary", occurred_at=at(10))
        assert db.events_between(at(0), at(10)) == []
        assert len(db.events_between(at(0), at(11))) == 1

    def test_queries_can_be_scoped_to_a_project(self, db):
        db.record_event("message", "alpha work", project="alpha", occurred_at=at(0))
        db.record_event("message", "beta work", project="beta", occurred_at=at(1))
        found = db.events_between(at(-1), at(10), project="alpha")
        assert [e["summary"] for e in found] == ["alpha work"]

    def test_noise_can_be_filtered_out_by_importance(self, db):
        db.record_event("screen_observed", "a window was in focus", occurred_at=at(0))
        db.record_event("error", "the build broke", occurred_at=at(1))
        found = db.events_between(at(-1), at(10), min_importance=0.5)
        assert [e["summary"] for e in found] == ["the build broke"]

    def test_secret_events_are_withheld_unless_requested(self, db):
        db.record_event("message", "pasted a token", sensitivity="secret", occurred_at=at(0))
        assert db.events_between(at(-1), at(10)) == []
        assert len(db.events_between(at(-1), at(10), include_sensitive=True)) == 1


class TestConsolidation:
    def test_a_run_of_related_events_becomes_one_episode(self, db):
        seed_debugging_session(db)
        [episode] = db.consolidate(project="primnox")
        assert episode["event_count"] == 6
        assert episode["started_at"] == at(0).isoformat()
        assert episode["ended_at"] == at(11).isoformat()

    def test_the_default_summary_names_the_work_without_a_model(self, db):
        seed_debugging_session(db)
        [episode] = db.consolidate(project="primnox")
        assert "router.py" in episode["summary"]
        assert "file modified" in episode["summary"]

    def test_a_long_gap_splits_the_work_into_separate_episodes(self, db):
        db.record_event("file_modified", "morning work", occurred_at=at(0))
        db.record_event("file_modified", "afternoon work", occurred_at=at(300))
        assert len(db.consolidate(gap_minutes=30)) == 2

    def test_two_projects_at_once_are_two_threads_of_work(self, db):
        db.record_event("file_modified", "alpha", project="alpha", occurred_at=at(0))
        db.record_event("file_modified", "beta", project="beta", occurred_at=at(1))
        assert len(db.consolidate()) == 2

    def test_consolidated_events_are_not_consolidated_again(self, db):
        seed_debugging_session(db)
        assert len(db.consolidate(project="primnox")) == 1
        assert db.consolidate(project="primnox") == []

    def test_work_still_in_progress_can_be_left_alone(self, db):
        db.record_event("file_modified", "older work", occurred_at=at(0))
        db.record_event("file_modified", "still going", occurred_at=at(120))
        assert len(db.consolidate(before=at(60))) == 1
        assert db.get_event(db.last_activity()[0]["id"])["episode_id"] is None

    def test_raw_events_stay_addressable_as_evidence(self, db):
        seed_debugging_session(db)
        [episode] = db.consolidate(project="primnox")
        evidence = db.events_in_episode(episode["id"])
        assert len(evidence) == 6
        assert evidence[0]["summary"] == "opened router.py"

    def test_a_model_summary_is_labelled_as_an_inference(self, db):
        seed_debugging_session(db)
        [episode] = db.consolidate(
            project="primnox", summarizer=lambda events: "Debugged the retrieval router"
        )
        assert episode["summary"] == "Debugged the retrieval router"
        assert episode["origin"] == "inferred"

    def test_a_failing_summarizer_falls_back_instead_of_losing_the_episode(self, db):
        """Memory must not stop working because a provider is unreachable."""
        def broken(events):
            raise RuntimeError("provider down")

        seed_debugging_session(db)
        [episode] = db.consolidate(project="primnox", summarizer=broken)
        assert "router.py" in episode["summary"]
        assert episode["origin"] == "observed"

    def test_noise_does_not_outvote_what_mattered(self, db):
        for i in range(20):
            db.record_event("screen_observed", f"window {i}", occurred_at=at(i))
        db.record_event("error", "the build broke", occurred_at=at(21))
        [episode] = db.consolidate()
        assert "error" in episode["summary"]

    def test_min_events_can_suppress_trivial_episodes(self, db):
        db.record_event("file_opened", "opened a.py", occurred_at=at(0))
        assert db.consolidate(min_events=2) == []


class TestTimeline:
    def test_the_timeline_reads_chronologically(self, db):
        seed_debugging_session(db)
        db.consolidate(project="primnox")
        db.record_event("commit", "committed the fix", project="primnox", occurred_at=at(20))
        result = db.timeline(at(-10), at(60), project="primnox")
        assert [e["type"] for e in result["entries"]] == ["episode", "event"]

    def test_episodes_overlapping_the_window_are_included(self, db):
        """Work that ran from 23:40 to 00:20 belongs to both days."""
        db.record_event("file_modified", "late night", occurred_at=at(0))
        db.record_event("file_modified", "just after", occurred_at=at(20))
        db.consolidate()
        assert db.episodes_between(at(10), at(15))

    def test_the_timeline_is_trimmed_and_says_so(self, db):
        for i in range(30):
            db.record_event("message", f"note {i}", occurred_at=at(i * 120))
        result = db.timeline(at(-10), at(5000), max_entries=5)
        assert len(result["entries"]) == 5
        assert result["truncated"] is True
        assert result["total_entries"] == 30

    def test_an_empty_period_is_an_empty_timeline_not_an_error(self, db):
        result = db.timeline(at(0), at(10))
        assert result["entries"] == []
        assert result["truncated"] is False

    def test_important_entries_survive_trimming(self, db):
        for i in range(20):
            db.record_event("screen_observed", f"window {i}", occurred_at=at(i))
        db.record_event("error", "the build broke", occurred_at=at(25))
        result = db.timeline(at(-1), at(60), max_entries=3)
        assert any("build broke" in e["summary"] for e in result["entries"])


class TestRecallAndCleanup:
    def test_recall_finds_events_by_word(self, db):
        seed_debugging_session(db)
        found = db.recall("off-by-one", project="primnox")
        assert found and "off-by-one" in found[0]["summary"]

    def test_recall_handles_punctuated_terms(self, db):
        seed_debugging_session(db)
        assert db.recall("router.py", project="primnox")

    def test_last_activity_answers_where_did_i_leave_off(self, db):
        seed_debugging_session(db)
        [latest] = db.last_activity(project="primnox", limit=1)
        assert latest["summary"] == "test_retrieval passed"

    def test_a_non_persistent_session_can_be_erased(self, db):
        seed_debugging_session(db, session="private-session")
        db.record_event("message", "kept", project="primnox", session="other")
        assert db.forget_session("private-session") == 6
        assert len(db.last_activity(project="primnox")) == 1

    def test_purging_a_project_removes_its_events_and_episodes(self, db):
        seed_debugging_session(db, project="alpha")
        db.consolidate(project="alpha")
        db.record_event("message", "beta stays", project="beta", occurred_at=at(0))

        report = db.purge_project("alpha")

        assert report["events_deleted"] == 6
        assert report["episodes_deleted"] == 1
        assert db.events_between(at(-1), at(100), project="alpha") == []
        assert len(db.events_between(at(-1), at(100), project="beta")) == 1
