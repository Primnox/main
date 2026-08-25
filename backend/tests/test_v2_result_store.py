"""Tests for the tool result store.

This is the module that attacks the measured cost problem: results
accumulating in the transcript so that later steps re-pay for earlier ones.
The properties that matter are that the observation is small, that it is
honest about what was left out, that the full result stays recoverable, and
that a repeat costs a reference rather than a second summary.
"""

import json

import pytest

from primnox2.context.service import estimate_tokens
from v2 import result_store as rs, store
from v2.world_model import ValidationError


@pytest.fixture
def db(tmp_path):
    store.reset_for_tests(tmp_path / "v2.db")
    yield rs
    store.reset_for_tests(None)


def big_log(lines: int = 500) -> str:
    return "\n".join(f"line {i}: routing decision for module_{i}" for i in range(lines))


class TestSummarisation:
    def test_a_short_result_is_passed_through_verbatim(self, db):
        assert db.summarize("ok") == "ok"

    def test_a_long_result_is_trimmed_and_says_so(self, db):
        summary = db.summarize("x" * 10000, budget_tokens=50)
        assert "[truncated]" in summary
        assert estimate_tokens(summary) <= 60

    def test_a_multi_line_result_reports_its_size(self, db):
        summary = db.summarize(big_log())
        assert "500 lines" in summary
        assert "more line" in summary

    def test_a_failure_is_summarised_from_the_end(self, db):
        """A traceback's useful line is the last one; a head-only excerpt of
        a stack trace is the least informative possible summary."""
        trace = "Traceback (most recent call last):\n" + "\n".join(
            f'  File "f{i}.py", line {i}' for i in range(50)
        ) + "\nValueError: vault is locked"
        summary = db.summarize(trace)
        assert "ValueError: vault is locked" in summary

    def test_a_json_list_is_described_structurally(self, db):
        summary = db.summarize([{"path": f"m{i}.py", "imports": ["b"]} for i in range(47)])
        assert "47 items" in summary
        assert "path" in summary and "imports" in summary

    def test_a_json_object_is_described_by_its_keys(self, db):
        summary = db.summarize({"status": "ok", "count": 3, "items": list(range(100))})
        assert "3 keys" in summary
        assert "status" in summary

    def test_an_empty_result_says_so(self, db):
        assert db.summarize("") == "(empty result)"
        assert db.summarize("   ") == "(empty result)"

    def test_json_text_is_recognised_as_json(self, db):
        summary = db.summarize(json.dumps([{"a": 1}, {"a": 2}]))
        assert "2 items" in summary


class TestPut:
    def test_the_observation_is_far_smaller_than_the_result(self, db):
        stored = db.put("grep", big_log())
        assert stored["observation_tokens"] < stored["full_tokens"] / 10
        assert stored["truncated"] is True

    def test_the_full_result_is_recoverable_by_id(self, db):
        text = big_log()
        stored = db.put("grep", text)
        assert db.get(stored["result_id"]) == text

    def test_an_identical_repeat_costs_a_reference(self, db):
        text = big_log()
        first = db.put("grep", text)
        second = db.put("grep", text)
        assert second["duplicate"] is True
        assert second["result_id"] == first["result_id"]
        assert first["result_id"] in second["observation"]
        assert estimate_tokens(second["observation"]) < 40

    def test_the_same_bytes_from_different_tools_stay_distinct(self, db):
        """A file read and a grep that happen to return the same text are
        different observations about different questions."""
        assert db.put("read_file", "same")["result_id"] != db.put("grep", "same")["result_id"]

    def test_a_small_result_is_not_marked_truncated(self, db):
        stored = db.put("status", "ok")
        assert stored["truncated"] is False
        assert stored["observation"] == "ok"

    def test_metadata_is_kept_without_loading_content(self, db):
        stored = db.put("grep", big_log(), args={"pattern": "router"}, session="s1", project="primnox")
        meta = db.info(stored["result_id"])
        assert meta["tool"] == "grep"
        assert json.loads(meta["args"]) == {"pattern": "router"}
        assert meta["session_id"] == "s1"
        assert "content" not in meta

    def test_an_unnamed_tool_is_rejected(self, db):
        with pytest.raises(ValidationError):
            db.put("", "result")

    def test_non_string_results_are_accepted(self, db):
        stored = db.put("count", 42)
        assert db.get(stored["result_id"]) == "42"

    def test_reference_rendering_carries_the_handle(self, db):
        stored = db.put("grep", big_log())
        rendered = db.reference(stored)
        assert stored["result_id"] in rendered
        assert "full result" in rendered


class TestSecrets:
    def test_a_secret_result_never_appears_in_its_observation(self, db):
        stored = db.put("vault_read", "sk-live-abcdef123456", sensitivity="secret")
        assert "sk-live" not in stored["observation"]
        assert "withheld" in stored["observation"]

    def test_a_secret_result_is_still_retrievable_through_an_authorised_path(self, db):
        stored = db.put("vault_read", "sk-live-abcdef123456", sensitivity="secret")
        assert db.get(stored["result_id"]) == "sk-live-abcdef123456"


class TestSelectiveRetrieval:
    def test_only_the_relevant_lines_come_back(self, db):
        stored = db.put("deps", big_log())
        found = db.section(stored["result_id"], r"module_42\b")
        assert found["matches"] == 1
        assert "module_42" in found["text"]
        assert estimate_tokens(found["text"]) < 100

    def test_context_lines_surround_each_match(self, db):
        stored = db.put("deps", big_log())
        found = db.section(stored["result_id"], r"module_42\b", context_lines=2)
        assert "module_40" in found["text"] and "module_44" in found["text"]

    def test_gaps_between_matches_are_marked(self, db):
        stored = db.put("deps", big_log())
        found = db.section(stored["result_id"], r"module_(1|400)\b")
        assert "…" in found["text"]

    def test_no_match_is_reported_rather_than_guessed_at(self, db):
        stored = db.put("deps", big_log())
        found = db.section(stored["result_id"], "nothing here")
        assert found["matches"] == 0 and found["text"] == ""

    def test_an_invalid_regex_is_treated_as_literal_text(self, db):
        """A query typed by a model is as likely to be prose as a pattern —
        an unbalanced bracket should search for those characters, not raise."""
        stored = db.put("deps", "the failing case is items[0] in the report")
        assert db.section(stored["result_id"], "items[0]")["matches"] == 1

    def test_head_returns_the_first_lines(self, db):
        stored = db.put("deps", big_log())
        assert db.head(stored["result_id"], 3).count("\n") == 2

    def test_retrieving_an_unknown_id_returns_none(self, db):
        assert db.get("res_0000000000000000") is None
        assert db.section("res_0000000000000000", "x") is None
        assert db.info("res_0000000000000000") is None


class TestRetention:
    def test_session_results_can_be_erased(self, db):
        db.put("grep", "a", session="private")
        db.put("grep", "b", session="other")
        assert db.forget_session("private") == 1
        assert db.stats()["results"] == 1

    def test_project_results_can_be_purged(self, db):
        db.put("grep", "a", project="alpha")
        db.put("grep", "b", project="beta")
        assert db.purge_project("alpha")["results_deleted"] == 1

    def test_pruning_drops_stale_working_data(self, db):
        stored = db.put("grep", big_log())
        with store.transaction() as conn:
            conn.execute(
                "UPDATE results SET last_used_at = '2020-01-01T00:00:00+00:00' WHERE id = ?",
                (stored["result_id"],),
            )
        assert db.prune(keep_days=14) == 1
        assert db.get(stored["result_id"]) is None

    def test_durable_results_survive_pruning(self, db):
        stored = db.put("report", big_log(), retention="durable")
        with store.transaction() as conn:
            conn.execute(
                "UPDATE results SET last_used_at = '2020-01-01T00:00:00+00:00' WHERE id = ?",
                (stored["result_id"],),
            )
        assert db.prune(keep_days=14) == 0
        assert db.get(stored["result_id"]) is not None


class TestAccounting:
    def test_savings_are_measured_not_assumed(self, db):
        stored = db.put("grep", big_log(), session="s1")
        totals = db.stats(session="s1")
        assert totals["results"] == 1
        assert totals["full_tokens"] == stored["full_tokens"]
        assert totals["tokens_saved"] == stored["full_tokens"] - totals["observation_tokens"]

    def test_a_repeat_counts_as_a_further_saving(self, db):
        text = big_log()
        db.put("grep", text, session="s1")
        before = db.stats(session="s1")["tokens_saved"]
        db.put("grep", text, session="s1")
        assert db.stats(session="s1")["tokens_saved"] > before

    def test_stats_on_an_empty_store_are_zeroes_not_an_error(self, db):
        assert db.stats()["results"] == 0
        assert db.stats()["tokens_saved"] == 0
