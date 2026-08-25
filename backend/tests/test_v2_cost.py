"""Tests for adaptive step budgets, cache economics and compaction.

These encode the benchmark's findings as behaviour: steps dominate cost, so
budgets start at one; caching is a net loss on short turns, so it is off
there; and compaction must never rewrite a cached prefix, because a
compaction that does costs more than it saves.
"""

import pytest

from primnox2.context.service import estimate_tokens
from v2 import compaction, router, step_budget as sb, store


@pytest.fixture
def db(tmp_path):
    store.reset_for_tests(tmp_path / "v2.db")
    yield sb
    store.reset_for_tests(None)


class TestPrediction:
    def test_a_trivial_question_gets_one_step(self):
        assert sb.predict("What is this function?") == 1

    def test_a_remembered_fact_gets_one_step(self):
        route = router.route("Remember that this project uses pnpm.")
        assert sb.predict("Remember that this project uses pnpm.", route) == 1

    def test_a_compound_question_gets_more_room(self):
        route = router.route("Why is authentication failing?")
        assert sb.predict("Why is authentication failing?", route) >= 4

    def test_a_refactor_gets_the_full_ladder(self):
        assert sb.predict("Refactor the retrieval router across the codebase") == 8

    def test_an_action_needs_plan_do_verify(self):
        assert sb.predict("Fix the failing test") == 4

    def test_an_empty_request_costs_one_step(self):
        assert sb.predict("") == 1

    def test_predictions_are_on_the_ladder(self):
        questions = [
            "What is this?", "Why is login failing?", "Refactor everything",
            "Where is the vault key loaded?", "Continue what I was doing.",
        ]
        for question in questions:
            assert sb.predict(question, router.route(question)) in sb.LADDER


class TestCacheEconomics:
    def test_caching_is_off_for_a_single_step(self):
        """Measured: 353 billed with a cache write against 350 without."""
        assert sb.cache_pays_off(1) is False
        assert sb.plan("What is this function?").cache is False

    def test_caching_is_on_for_long_turns(self):
        """Measured: 4,376 billed against 7,032 at eight steps."""
        assert sb.cache_pays_off(8) is True
        plan = sb.plan("Refactor the retrieval router across the codebase")
        assert plan.cache is True

    def test_a_short_turn_caches_only_behind_a_large_prefix(self):
        question = "Continue what I was doing."
        route = router.route(question)
        assert sb.plan(question, route, prefix_tokens=100).cache is False
        assert sb.plan(question, route, prefix_tokens=5000).cache is True

    def test_an_unmeasured_step_count_is_judged_by_the_rung_below(self):
        assert sb.cache_pays_off(3) == sb.cache_pays_off(2)

    def test_result_budgets_tighten_as_turns_lengthen(self):
        assert sb.plan("What is this function?").result_budget_tokens > sb.plan(
            "Refactor the router across the codebase"
        ).result_budget_tokens

    def test_compaction_is_planned_for_long_turns_only(self):
        assert sb.plan("What is this function?").compact is False
        assert sb.plan("Refactor the router across the codebase").compact is True

    def test_the_plan_explains_itself(self):
        assert "predicted" in sb.plan("What is this function?").rationale


class TestEscalation:
    def test_a_budget_starts_where_it_was_predicted(self):
        assert sb.StepBudget(1).remaining == 1

    def test_a_budget_is_snapped_onto_the_ladder(self):
        assert sb.StepBudget(3).limit == 4
        assert sb.StepBudget(99).limit == 8

    def test_escalation_doubles(self):
        budget = sb.StepBudget(1)
        budget.escalate()
        assert budget.limit == 2
        budget.escalate()
        assert budget.limit == 4

    def test_escalation_stops_at_the_ceiling(self):
        budget = sb.StepBudget(8)
        assert budget.escalate() is False
        assert budget.limit == 8

    def test_steps_are_counted_down(self):
        budget = sb.StepBudget(2)
        budget.step()
        assert budget.remaining == 1 and not budget.exhausted
        budget.step()
        assert budget.exhausted

    def test_escalating_gives_room_again(self):
        budget = sb.StepBudget(1)
        budget.step()
        assert budget.exhausted
        budget.escalate()
        assert not budget.exhausted

    def test_a_custom_ceiling_is_respected(self):
        budget = sb.StepBudget(1, ceiling=2)
        assert budget.escalate() is True
        assert budget.escalate() is False


class TestTelemetry:
    def test_cost_per_successful_task_is_the_headline(self, db):
        db.record_turn(predicted_steps=1, steps_used=1, billed_tokens=350, success=True, session="s")
        db.record_turn(predicted_steps=1, steps_used=1, billed_tokens=350, success=False, session="s")
        report = db.cost_report(session="s")
        assert report["cost_per_successful_task"] == 700.0
        assert report["cost_per_turn"] == 350.0

    def test_prediction_accuracy_is_tracked(self, db):
        db.record_turn(predicted_steps=1, steps_used=1, billed_tokens=350, session="s")
        db.record_turn(predicted_steps=1, steps_used=4, billed_tokens=2283, session="s")
        report = db.cost_report(session="s")
        assert report["underestimated"] == 1
        assert report["prediction_accuracy"] == 0.5

    def test_an_empty_report_does_not_divide_by_zero(self, db):
        report = db.cost_report(session="nothing")
        assert report["turns"] == 0
        assert report["cost_per_successful_task"] is None


def transcript(tool_calls: int = 10, chunk: int = 400) -> list[dict]:
    """A system+user prefix followed by a long tool loop."""
    messages = [
        {"role": "system", "content": "You are Primnox."},
        {"role": "user", "content": "reduce the cost of the tool loop"},
    ]
    for i in range(tool_calls):
        messages.append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "grep"}}]})
        messages.append(
            {"role": "tool", "name": "grep", "content": f"match {i} " * chunk + f" [result: res_{i:016x}]"}
        )
    messages.append({"role": "user", "content": "what did you find?"})
    return messages


class TestCompaction:
    def test_a_long_loop_compacts_dramatically(self):
        messages = transcript()
        result = compaction.compact(messages, boundary_index=2)
        assert result.compacted is True
        assert result.tokens_after < result.tokens_before / 10

    def test_the_cached_prefix_is_returned_untouched(self):
        """The whole point: rewriting a cached message re-bills the prefix."""
        messages = transcript()
        before = [dict(m) for m in messages]
        result = compaction.compact(messages, boundary_index=2)
        assert compaction.prefix_unchanged(before, result.messages, 2)
        assert result.messages[0] is messages[0]

    def test_the_frozen_block_joins_the_prefix(self):
        messages = transcript()
        result = compaction.compact(messages, boundary_index=2)
        assert result.boundary_index == 3
        assert result.messages[2]["compacted"] is True

    def test_compacting_twice_does_not_rewrite_the_first_summary(self):
        """Immutability is what lets compaction and caching compound."""
        first = compaction.compact(transcript(), boundary_index=2)
        grown = first.messages + transcript(6)[2:]
        second = compaction.compact(grown, boundary_index=first.boundary_index)
        assert second.compacted is True
        assert compaction.prefix_unchanged(grown, second.messages, first.boundary_index)
        assert second.messages[2]["content"] == first.summary

    def test_the_recent_tail_survives_verbatim(self):
        messages = transcript()
        result = compaction.compact(messages, boundary_index=2)
        assert result.messages[-1]["content"] == "what did you find?"

    def test_a_tail_never_starts_with_an_orphaned_tool_message(self):
        """A `tool` message is only valid straight after the assistant turn
        that requested it; cutting between them produces an invalid request."""
        messages = transcript()
        result = compaction.compact(messages, boundary_index=2, keep_recent=2)
        tail = result.messages[result.boundary_index:]
        assert tail and tail[0].get("role") != "tool"

    def test_evidence_references_survive_compaction(self):
        result = compaction.compact(transcript(), boundary_index=2)
        assert len(result.result_refs) == 10
        assert "res_" in result.summary

    def test_errors_are_preserved_in_the_summary(self):
        messages = transcript(2)
        messages.insert(-1, {"role": "tool", "name": "run_tests", "content": "ERROR: vault is locked"})
        result = compaction.compact(messages, boundary_index=2, min_tokens=0)
        assert "vault is locked" in result.summary

    def test_a_short_transcript_is_left_alone(self):
        messages = transcript(1, chunk=2)
        result = compaction.compact(messages, boundary_index=2)
        assert result.compacted is False
        assert result.messages is messages
        assert "threshold" in result.reason

    def test_nothing_outside_the_prefix_is_a_no_op(self):
        messages = transcript(1, chunk=2)
        result = compaction.compact(messages, boundary_index=len(messages))
        assert result.compacted is False

    def test_should_compact_agrees_with_compact(self):
        long_messages = transcript()
        short_messages = transcript(1, chunk=2)
        assert compaction.should_compact(long_messages, boundary_index=2) is True
        assert compaction.should_compact(short_messages, boundary_index=2) is False

    def test_a_model_summary_is_used_when_it_works(self):
        result = compaction.compact(
            transcript(), boundary_index=2, summarizer=lambda region: "Searched for the hot path."
        )
        assert "Searched for the hot path." in result.summary
        assert result.messages[2]["origin"] == "model"

    def test_a_failing_summarizer_falls_back_rather_than_losing_context(self):
        def broken(region):
            raise RuntimeError("provider down")

        result = compaction.compact(transcript(), boundary_index=2, summarizer=broken)
        assert result.compacted is True
        assert result.messages[2]["origin"] == "deterministic"

    def test_the_summary_stays_within_its_budget(self):
        result = compaction.compact(transcript(40), boundary_index=2, budget_tokens=120)
        assert estimate_tokens(result.summary) <= 140

    def test_vision_style_content_blocks_are_counted(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "hello"}, {"type": "image_url"}]},
        ]
        assert compaction.count_tokens(messages) == estimate_tokens("hello")

    def test_prefix_verification_catches_a_rewrite(self):
        before = transcript(1, chunk=2)
        after = [dict(m) for m in before]
        after[0]["content"] = "rewritten system prompt"
        assert compaction.prefix_unchanged(before, after, 2) is False
