"""Tests for the V1↔V2 seam.

The property that matters most here is not what these functions do when
everything works — the other suites cover that — but what they do when V2
fails. Adopting the substrate must not add a way for the chat path to break,
so every entry point degrades to V1's existing behaviour.
"""

import pytest

from v2 import episodes, integration, result_store, step_budget, store


@pytest.fixture
def db(tmp_path):
    store.reset_for_tests(tmp_path / "v2.db")
    yield integration
    store.reset_for_tests(None)


class TestPlanTurn:
    def test_a_plan_carries_the_route_and_the_budget(self, db):
        plan = db.plan_turn("What calls authenticate()?", project="primnox")
        assert plan.route.label == "G"
        assert plan.max_steps in step_budget.LADDER

    def test_a_trivial_question_is_planned_cheaply(self, db):
        plan = db.plan_turn("What is this function?")
        assert plan.max_steps == 1
        assert plan.budget.cache is False

    def test_context_is_built_and_measured(self, db):
        from v2 import world_model as wm

        wm.record_fact("the backend serves on port 4009", project="primnox")
        plan = db.plan_turn("What do you remember about this project?", project="primnox")
        assert "4009" in plan.context_block
        assert plan.context_tokens > 0
        assert plan.provenance[0]["source"] == "memory"

    def test_a_broken_context_build_does_not_break_the_turn(self, db, monkeypatch):
        def explode(*args, **kwargs):
            raise RuntimeError("world model unavailable")

        monkeypatch.setattr(integration.context_builder, "build", explode)
        plan = db.plan_turn("What calls authenticate()?")
        assert plan.context_block == ""
        assert plan.max_steps >= 1
        assert any("unavailable" in note for note in plan.notes)

    def test_the_plan_is_serialisable_for_logging(self, db):
        assert db.plan_turn("What is this?").as_dict()["route"] in "MSGRTHC"


class TestObserveToolResult:
    def test_a_large_result_becomes_a_compact_observation(self, db):
        big = "\n".join(f"line {i}" for i in range(5000))
        observation = db.observe_tool_result("grep", big, session="s1")
        assert len(observation) < len(big) / 50
        assert "res_" in observation

    def test_the_full_result_is_still_available(self, db):
        big = "\n".join(f"line {i}" for i in range(5000))
        observation = db.observe_tool_result("grep", big, session="s1")
        result_id = observation.split("res_")[1].split()[0].strip("]·")
        assert result_store.get(f"res_{result_id}") == big

    def test_a_broken_store_passes_the_raw_result_through(self, db, monkeypatch):
        """Degraded and expensive beats failed."""
        def explode(*args, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(integration.result_store, "put", explode)
        assert db.observe_tool_result("grep", "the output", session="s1") == "the output"

    def test_a_secret_result_is_not_summarised_into_the_transcript(self, db):
        observation = db.observe_tool_result(
            "vault_read", "gsk_livekey_abcdefghijk", session="s1", sensitivity="secret"
        )
        assert "gsk_" not in observation


class TestCompactIfNeeded:
    def test_a_short_transcript_is_returned_untouched(self, db):
        messages = [{"role": "user", "content": "hello"}]
        result = db.compact_if_needed(messages, boundary_index=0)
        assert result.compacted is False
        assert result.messages is messages

    def test_a_long_transcript_is_compacted(self, db):
        messages = [{"role": "system", "content": "You are Primnox."}]
        for i in range(10):
            messages.append({"role": "tool", "name": "grep", "content": f"hit {i} " * 400})
        messages.append({"role": "user", "content": "and?"})
        result = db.compact_if_needed(messages, boundary_index=1)
        assert result.compacted is True
        assert result.tokens_saved > 0

    def test_a_compaction_failure_leaves_the_transcript_alone(self, db, monkeypatch):
        def explode(*args, **kwargs):
            raise RuntimeError("summariser exploded")

        monkeypatch.setattr(integration.compaction, "compact", explode)
        messages = [{"role": "user", "content": "hello"}]
        result = db.compact_if_needed(messages)
        assert result.messages is messages
        assert "failed" in result.reason


class TestRecordTurnOutcome:
    def test_cost_and_activity_are_both_recorded(self, db):
        plan = db.plan_turn("What calls authenticate()?", project="primnox")
        outcome = db.record_turn_outcome(
            plan, steps_used=2, billed_tokens=848, session="s1", project="primnox",
            summary="looked up the callers of authenticate",
        )
        assert outcome["telemetry_id"] and outcome["event_id"]
        assert step_budget.cost_report(session="s1")["turns"] == 1
        assert episodes.last_activity(project="primnox")[0]["summary"].startswith("looked up")

    def test_a_failed_turn_is_recorded_as_such(self, db):
        plan = db.plan_turn("Fix the build")
        db.record_turn_outcome(plan, steps_used=8, billed_tokens=7032, success=False, session="s1")
        assert step_budget.cost_report(session="s1")["successes"] == 0

    def test_bookkeeping_failure_never_fails_the_turn(self, db, monkeypatch):
        def explode(*args, **kwargs):
            raise RuntimeError("telemetry table missing")

        monkeypatch.setattr(integration.step_budget, "record_turn", explode)
        plan = db.plan_turn("What is this?")
        outcome = db.record_turn_outcome(plan, steps_used=1, session="s1")
        assert outcome["telemetry_id"] is None


class TestNoteActivity:
    def test_an_ambient_observation_becomes_recallable(self, db):
        event_id = db.note_activity("file_modified", "edited backend/router.py", project="primnox")
        assert event_id
        assert episodes.recall("router.py", project="primnox")

    def test_a_failed_write_returns_none_rather_than_a_false_confirmation(self, db, monkeypatch):
        def explode(*args, **kwargs):
            raise RuntimeError("database is locked")

        monkeypatch.setattr(integration.episodes, "record_event", explode)
        assert db.note_activity("file_modified", "edited something") is None
