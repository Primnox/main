"""Tests for working/execution state.

State is what replaces the execution transcript, so these tests pin the
properties that make that substitution safe: the record stays small, it
distinguishes four outcome classes rather than two, it refuses to call a
task done while part of it never ran, and it survives an interruption well
enough to resume from.
"""

import pytest

from v2 import store, task_state as ts
from v2.world_model import ValidationError


@pytest.fixture
def db(tmp_path):
    store.reset_for_tests(tmp_path / "v2.db")
    yield ts
    store.reset_for_tests(None)


@pytest.fixture
def task(db):
    return db.start(
        "reduce tool-call cost",
        constraints=["no new dependencies"],
        project="primnox",
        session="s1",
        plan=["benchmark steps", "measure cache behaviour", "design compaction"],
    )


class TestLifecycle:
    def test_a_plan_becomes_pending_actions_in_order(self, db, task):
        assert [a["description"] for a in task["actions"]] == [
            "benchmark steps", "measure cache behaviour", "design compaction"
        ]
        assert {a["status"] for a in task["actions"]} == {"pending"}

    def test_a_task_needs_a_goal(self, db):
        with pytest.raises(ValidationError):
            db.start("   ")

    def test_actions_can_be_appended_later(self, db, task):
        added = db.add_action(task["id"], "write the regression test")
        assert added["sequence"] == 3
        assert len(db.get(task["id"])["actions"]) == 4

    def test_resume_finds_the_unfinished_task(self, db, task):
        assert db.resume(project="primnox")["id"] == task["id"]

    def test_resume_ignores_finished_work(self, db, task):
        for action in task["actions"]:
            db.complete_action(action["id"])
        db.finish(task["id"])
        assert db.resume(project="primnox") is None

    def test_resume_picks_the_most_recently_touched_task(self, db, task):
        second = db.start("fix the calendar sync", project="primnox")
        db.observe(task["id"], "still working on this one")
        assert db.resume(project="primnox")["id"] == task["id"]
        db.observe(second["id"], "switched over")
        assert db.resume(project="primnox")["id"] == second["id"]

    def test_tasks_are_scoped_by_project(self, db, task):
        db.start("unrelated work", project="other")
        assert len(db.open_tasks(project="primnox")) == 1


class TestOutcomes:
    def test_a_task_cannot_be_declared_complete_while_work_remains(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        with pytest.raises(ValidationError):
            db.finish(task["id"], "completed")

    def test_a_derived_status_is_partial_when_something_never_ran(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        db.complete_action(task["actions"][1]["id"])
        assert db.finish(task["id"])["status"] == "partial"

    def test_a_derived_status_is_completed_only_when_everything_is(self, db, task):
        for action in task["actions"]:
            db.complete_action(action["id"])
        assert db.finish(task["id"])["status"] == "completed"

    def test_a_failure_among_successes_is_partial_not_failed(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        db.fail_action(task["actions"][1]["id"], "provider timeout")
        db.complete_action(task["actions"][2]["id"])
        assert db.finish(task["id"])["status"] == "partial"

    def test_a_task_where_nothing_worked_is_failed(self, db, task):
        for action in task["actions"]:
            db.fail_action(action["id"], "provider unreachable")
        assert db.finish(task["id"])["status"] == "failed"

    def test_a_partial_action_is_neither_success_nor_failure(self, db, task):
        db.partial_action(task["actions"][0]["id"], "wrote 3 of 5 files")
        attempted = db.tried(task["id"])
        assert attempted["succeeded"] == []
        assert attempted["failed"] == []
        assert attempted["unresolved"][0]["status"] == "partial"

    def test_a_crashed_tool_leaves_an_unknown_outcome(self, db, task):
        """The state a tool that died mid-write should leave behind — not
        "failed", because a blind retry of a half-finished write is how
        recovery turns into data loss."""
        db.unknown_action(task["actions"][0]["id"], "process died after the file was opened")
        [unresolved] = [u for u in db.tried(task["id"])["unresolved"] if u["status"] == "unknown"]
        assert "process died" in unresolved["detail"]

    def test_an_unknown_status_value_is_rejected(self, db, task):
        with pytest.raises(ValidationError):
            db.set_action(task["actions"][0]["id"], "vibes")


class TestResumption:
    def test_the_next_step_is_the_first_unresolved_action(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        assert db.next_step(task["id"])["description"] == "measure cache behaviour"

    def test_doubtful_outcomes_are_settled_before_new_work(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        db.unknown_action(task["actions"][2]["id"], "tool crashed")
        assert db.next_step(task["id"])["description"] == "design compaction"

    def test_a_finished_task_has_no_next_step(self, db, task):
        for action in task["actions"]:
            db.complete_action(action["id"])
        assert db.next_step(task["id"]) is None

    def test_verification_confirms_work_that_really_happened(self, db, task):
        db.unknown_action(task["actions"][0]["id"], "tool crashed")
        changed = db.verify(task["id"], lambda action: True)
        assert changed[0]["status"] == "completed"

    def test_verification_reopens_work_that_did_not_happen(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        db.verify(task["id"], lambda action: False)
        assert db.get_action(task["actions"][0]["id"])["status"] == "pending"

    def test_unverifiable_work_becomes_unknown_rather_than_assumed_done(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        db.verify(task["id"], lambda action: None)
        assert db.get_action(task["actions"][0]["id"])["status"] == "unknown"

    def test_a_raising_verifier_does_not_lose_the_task(self, db, task):
        def broken(action):
            raise OSError("filesystem unavailable")

        db.complete_action(task["actions"][0]["id"])
        db.verify(task["id"], broken)
        assert db.get_action(task["actions"][0]["id"])["status"] == "unknown"


class TestChangingIntent:
    def test_a_new_goal_drops_the_stale_plan(self, db, task):
        db.retarget(task["id"], goal="find the bug, don't refactor")
        updated = db.get(task["id"])
        assert updated["goal"] == "find the bug, don't refactor"
        assert {a["status"] for a in updated["actions"]} == {"skipped"}

    def test_findings_survive_a_change_of_goal(self, db, task):
        db.complete_action(task["actions"][0]["id"], result_ref="res_abc")
        db.learn(task["id"], "transcripts accumulate superlinearly")
        db.observe(task["id"], "8 steps billed 7032 tokens")
        db.retarget(task["id"], goal="find the bug")
        state = db.snapshot(task["id"])
        assert state["completed"] == ["benchmark steps"]
        assert state["known"] == ["transcripts accumulate superlinearly"]
        assert state["latest_observation"] == "8 steps billed 7032 tokens"

    def test_new_constraints_are_added_not_replaced(self, db, task):
        db.retarget(task["id"], constraints=["do not touch the vault"])
        assert db.get(task["id"])["constraints"] == ["no new dependencies", "do not touch the vault"]

    def test_the_skipped_plan_stays_visible_as_history(self, db, task):
        db.retarget(task["id"], goal="find the bug")
        [skipped] = [a for a in db.get(task["id"])["actions"] if a["sequence"] == 0]
        assert skipped["detail"] == "superseded by a change of goal"


class TestKnowledgeAndObservations:
    def test_observations_record_where_they_came_from(self, db, task):
        db.observe(task["id"], "the report lists 47 dependents", result_ref="res_abc123")
        state = db.snapshot(task["id"])
        assert state["latest_observation"] == "the report lists 47 dependents"
        assert state["result_refs"] == ["res_abc123"]

    def test_repeated_result_references_are_not_duplicated(self, db, task):
        db.observe(task["id"], "first look", result_ref="res_abc")
        db.observe(task["id"], "second look", result_ref="res_abc")
        assert db.snapshot(task["id"])["result_refs"] == ["res_abc"]

    def test_task_local_knowledge_does_not_repeat_itself(self, db, task):
        db.learn(task["id"], "the failure needs a warm cache")
        db.learn(task["id"], "the failure needs a warm cache")
        assert db.get(task["id"])["known"] == ["the failure needs a warm cache"]

    def test_tried_reports_successes_and_failures_separately(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        db.fail_action(task["actions"][1]["id"], "429 from the provider")
        attempted = db.tried(task["id"])
        assert attempted["succeeded"] == ["benchmark steps"]
        assert attempted["failed"] == [{"action": "measure cache behaviour", "error": "429 from the provider"}]


class TestRendering:
    def test_the_state_block_stays_small(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        db.learn(task["id"], "transcripts accumulate superlinearly")
        db.observe(task["id"], "8 steps billed 7032 tokens", result_ref="res_abc")
        assert db.render_tokens(task["id"]) < 150

    def test_the_state_block_says_what_matters(self, db, task):
        db.complete_action(task["actions"][0]["id"])
        db.fail_action(task["actions"][1]["id"], "429 from the provider")
        rendered = db.render(task["id"])
        assert "reduce tool-call cost" in rendered
        assert "✓ benchmark steps" in rendered
        assert "429 from the provider" in rendered
        assert "Next: → design compaction" in rendered

    def test_long_lists_are_capped_and_counted(self, db, task):
        for i in range(20):
            action = db.add_action(task["id"], f"step {i}")
            db.complete_action(action["id"])
        rendered = db.render(task["id"], max_items=3)
        assert "… 17 more" in rendered

    def test_rendering_an_unknown_task_is_empty_not_an_error(self, db):
        assert db.render("task_0000000000000000") == ""
        assert db.snapshot("task_0000000000000000") is None


class TestDeletion:
    def test_a_session_can_be_erased_with_its_actions(self, db, task):
        db.start("other session work", session="s2")
        assert db.forget_session("s1") == 1
        assert db.get(task["id"]) is None
        assert len(db.open_tasks()) == 1

    def test_purging_a_project_removes_tasks_and_actions(self, db, task):
        db.start("elsewhere", project="other")
        report = db.purge_project("primnox")
        assert report["tasks_deleted"] == 1
        assert report["actions_deleted"] == 3
        assert db.open_tasks(project="primnox") == []
        assert len(db.open_tasks(project="other")) == 1
