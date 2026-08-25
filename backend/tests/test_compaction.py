"""The properties that make compaction a deferral rather than a deletion.

`bench_compaction.py` measures what compaction SAVES. These assert what it
must never cost, which is the half a benchmark cannot see: a mechanism that
replaced every result with the word "done" would score 99% and be useless.

Four things have to hold, and each of them has been wrong at some point:

* every result gets a handle, whatever its size and whoever produced it;
* the handle survives into the transcript, including when the observation is
  truncated;
* the handle redeems, in full and in part;
* a decision, once appended, is never revised — which is what lets the prefix
  cache and the compactor compound instead of cancelling.
"""
from __future__ import annotations

import re

import pytest

from primnox2.chat import turns
from primnox2.models import gateway
from primnox2.tools import observations, runtime
from primnox2.tools.registry import ToolContext

RESULT_ID = re.compile(r"res_[0-9a-f]{16}")


def _result(tool: str, output: str, *, status: str = "success",
            summary: str = "did the thing") -> dict:
    return {"type": "tool_result", "tool": tool, "status": status,
            "summary": summary, "output": output}


def _lines(count: int, prefix: str = "line") -> str:
    return "\n".join(f"{prefix} {i}: " + "content " * 8 for i in range(count))


@pytest.fixture
def session():
    conversation = turns.create_conversation("compaction test")
    turn = turns.create_turn(conversation["id"], "do a long thing")
    return conversation["id"], turn["turn_id"]


class TestHandles:
    """Everything the model is shown must lead back to what it was shown of."""

    def test_every_result_gets_a_handle_whatever_its_size(self, session):
        """The bug `bf95b46` fixed, pushed one level further down.

        That commit gave every tool an asset ref so the ledger would stop
        refusing to compact it. But `_store_output` only promotes output ABOVE
        the inline cap, so a result that fits inline still had nowhere to
        point. The store is asked at every size instead.
        """
        conversation, _ = session
        ledger = observations.Ledger(threshold=0, session=conversation)
        for size in (1, 40, 4000):
            result = _result("grep", _lines(size))
            ledger.record(runtime.format_result(result), result)
            assert RESULT_ID.fullmatch(result["result_id"] or ""), (
                f"a {size}-line result got no handle")

    def test_the_pointer_survives_truncation(self, session):
        """The failure that made an observation look fine and be unredeemable.

        `observe` caps the text it returns. An earlier ordering put the
        excerpt before the pointer, so on any result large enough to be worth
        compacting the cap ate the `res_…` id and the instruction to fetch it.
        """
        conversation, _ = session
        ledger = observations.Ledger(threshold=0, session=conversation)
        result = _result("read_skill", _lines(2000))
        observation = ledger.record(runtime.format_result(result), result)

        assert result["result_id"] in observation
        assert "read_result" in observation

    def test_nothing_is_compacted_without_somewhere_to_point(self, session):
        """Compaction that loses information is not compaction.

        With the store unreachable there is no handle, so the result has to be
        sent whole. Expensive is the correct failure mode; unrecoverable is
        not.
        """
        conversation, _ = session
        ledger = observations.Ledger(threshold=0, session=conversation)
        result = _result("grep", _lines(400))
        formatted = runtime.format_result(result)

        def explode(*args, **kwargs):
            raise RuntimeError("store is down")

        from v2 import result_store
        original = result_store.put
        result_store.put = explode
        try:
            appended = ledger.record(formatted, result)
        finally:
            result_store.put = original

        assert appended == formatted
        assert ledger.compacted == []


class TestRedemption:
    """A handle nobody can redeem is a deletion with better manners."""

    def test_read_result_returns_the_whole_body(self, session):
        conversation, turn_id = session
        ledger = observations.Ledger(threshold=0, session=conversation)
        body = _lines(300)
        result = _result("run_shell", body)
        ledger.record(runtime.format_result(result), result)

        ctx = ToolContext(job_id="j", turn_id=turn_id, conversation_id=conversation)
        got = runtime.execute("read_result", {"result_id": result["result_id"]}, ctx)

        assert got["status"] == "success"
        assert "line 0:" in got["output"]

    def test_find_pulls_back_only_the_matching_lines(self, session):
        """The mode that makes retrieval cheaper than never compacting.

        Reading every result back in full would pay for each one twice and
        land above where the turn started. `find` is what makes a read-back
        cost the lines that mattered instead of the whole body.
        """
        conversation, turn_id = session
        ledger = observations.Ledger(threshold=0, session=conversation)
        body = _lines(300) + "\nNEEDLE: the one line that mattered"
        result = _result("run_shell", body)
        ledger.record(runtime.format_result(result), result)

        ctx = ToolContext(job_id="j", turn_id=turn_id, conversation_id=conversation)
        got = runtime.execute(
            "read_result", {"result_id": result["result_id"], "find": "NEEDLE"}, ctx)

        assert got["status"] == "success"
        assert "the one line that mattered" in got["output"]
        assert len(got["output"]) < len(body) / 2

    def test_an_unknown_handle_says_so_rather_than_returning_nothing(self, session):
        conversation, turn_id = session
        ctx = ToolContext(job_id="j", turn_id=turn_id, conversation_id=conversation)
        got = runtime.execute(
            "read_result", {"result_id": "res_0000000000000000"}, ctx)

        assert got["status"] == "error"
        assert "not in the result store" in got["output"]

    def test_a_read_back_is_counted_against_the_observation(self, session):
        """The feedback signal compaction is aimed with.

        A result read back in full was paid for twice and the saving on it was
        negative. `sufficiency()` is what makes that visible, and it is only
        true if the retrieval path actually reports itself.
        """
        conversation, turn_id = session
        ledger = observations.Ledger(threshold=0, session=conversation)
        result = _result("run_python", _lines(300))
        ledger.record(runtime.format_result(result), result)

        from v2 import result_store
        before = result_store.sufficiency(session=conversation)["read_back"]
        ctx = ToolContext(job_id="j", turn_id=turn_id, conversation_id=conversation)
        runtime.execute("read_result", {"result_id": result["result_id"]}, ctx)
        after = result_store.sufficiency(session=conversation)["read_back"]

        assert after == before + 1


class TestImmutability:
    """The invariant the prefix cache is bought with."""

    def test_a_decision_once_made_is_never_revised(self, session):
        """Both mechanisms depend on this and neither can enforce it alone.

        A prefix cache keys on exact bytes, so revising an earlier message
        invalidates every cached token after it — a compactor that went back
        to shrink result one would pay a cache write every step and collect no
        reads. `Ledger` returns a string and holds no message list, which is
        what makes "never rewrite" structural instead of a convention.
        """
        conversation, _ = session
        ledger = observations.Ledger(threshold=0, session=conversation)

        appended = []
        for i in range(6):
            result = _result("grep", _lines(200, prefix=f"run{i}"))
            appended.append(ledger.record(runtime.format_result(result), result))

        first = appended[0]
        for i in range(6, 10):
            result = _result("grep", _lines(200, prefix=f"run{i}"))
            ledger.record(runtime.format_result(result), result)

        assert appended[0] == first
        assert not hasattr(ledger, "messages")


class TestConversationCache:
    """The half of the saving that compaction cannot reach."""

    def test_the_marker_goes_on_the_last_message(self):
        convo = [{"role": "user", "content": "x" * 6000},
                 {"role": "assistant", "content": "y" * 6000},
                 {"role": "user", "content": "z" * 6000}]
        marked = gateway._cacheable_conversation(convo)

        assert marked[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
        assert marked[0]["content"] == convo[0]["content"], (
            "only the last message may carry the marker — an earlier one would "
            "cap the cacheable prefix short of what was sent")

    def test_a_single_message_is_not_marked(self):
        """The first call of a turn has no earlier prefix to read.

        Measured at one step, a cache write costs more than it saves. Marking
        here would bill every one-step turn for a cache nothing collects.
        """
        convo = [{"role": "user", "content": "x" * 8000}]
        assert gateway._cacheable_conversation(convo) == convo

    def test_a_short_conversation_is_not_marked(self):
        convo = [{"role": "user", "content": "hello"},
                 {"role": "assistant", "content": "hi"}]
        assert gateway._cacheable_conversation(convo) == convo

    def test_the_original_messages_are_not_mutated(self):
        """The caller's list is reused across steps of the tool loop.

        Marking in place would leave a stale `cache_control` on a message that
        is no longer last, which caps the cacheable prefix at wherever the
        marker was stranded.
        """
        convo = [{"role": "user", "content": "x" * 6000},
                 {"role": "assistant", "content": "y" * 6000}]
        gateway._cacheable_conversation(convo)

        assert convo[-1]["content"] == "y" * 6000
