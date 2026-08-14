"""Replay Recorder — "my response duplicated" becomes reproducible.

The point of these tests is that a recorded turn can answer the question that
prompted the report, without guessing: what states did it move through, what
did it emit, what did it run.
"""
from __future__ import annotations

import pytest
from conftest import run_turn, wait_for_turn

from primnox2.kernel.trace import recorder
from primnox2.chat import turns


@pytest.fixture(autouse=True)
def _recording():
    recorder.start()
    yield
    recorder.stop()


def test_records_a_watched_turn(conversation, scripted):
    scripted("A traced reply.")
    turn = turns.create_turn(conversation, "trace me")
    tid = turn["turn_id"]
    recorder.watch(tid)

    from primnox2.kernel import scheduler
    scheduler.enqueue(tid, "chat.reply", {"conversation_id": conversation, "text": "trace me"})
    assert wait_for_turn(tid) == "completed"

    trace = recorder.dump(tid)
    assert trace is not None, "a watched turn produced no trace"
    kinds = [e.get("kind") for e in trace["entries"] if e["category"] == "event"]
    assert "turn.status" in kinds and "turn.completed" in kinds


def test_untraced_turns_are_not_recorded(conversation, scripted):
    """Off by default — recording every turn forever is its own problem."""
    scripted("Not traced.")
    tid = run_turn(conversation, "ignore me")
    wait_for_turn(tid)
    assert recorder.dump(tid) is None


def test_timeline_is_human_readable(conversation, scripted):
    scripted("Readable.")
    turn = turns.create_turn(conversation, "timeline me")
    tid = turn["turn_id"]
    recorder.watch(tid)

    from primnox2.kernel import scheduler
    scheduler.enqueue(tid, "chat.reply", {"conversation_id": conversation, "text": "timeline me"})
    wait_for_turn(tid)

    lines = recorder.timeline(tid)
    assert lines, "no timeline was produced"
    assert any("turn.status" in line and "streaming" in line for line in lines), \
        "the timeline does not show the turn reaching streaming"


def test_notes_capture_what_events_do_not(conversation):
    """Provider calls and transactions are not events, and are exactly what
    you need when reconstructing a turn."""
    turn = turns.create_turn(conversation, "note me")
    tid = turn["turn_id"]
    recorder.watch(tid)
    recorder.note(tid, "provider", action="stream_completion", messages=4, tokens=180)
    recorder.note(tid, "sandbox", action="execute", runtime="python", exit_code=0)

    trace = recorder.dump(tid)
    categories = {e["category"] for e in trace["entries"]}
    assert {"provider", "sandbox"} <= categories


def test_large_payloads_are_trimmed(conversation, scripted):
    """A trace is a diagnostic, not a second copy of the conversation."""
    scripted("x" * 5000, chunk=500)
    turn = turns.create_turn(conversation, "big reply")
    tid = turn["turn_id"]
    recorder.watch(tid)

    from primnox2.kernel import scheduler
    scheduler.enqueue(tid, "chat.reply", {"conversation_id": conversation, "text": "big reply"})
    wait_for_turn(tid)

    trace = recorder.dump(tid)
    for entry in trace["entries"]:
        for value in entry.get("payload", {}).values():
            if isinstance(value, str):
                assert len(value) < 1000, "a trace entry stored an untrimmed payload"


def test_trace_persists_to_disk(conversation, scripted):
    scripted("Persisted.")
    turn = turns.create_turn(conversation, "persist me")
    tid = turn["turn_id"]
    recorder.watch(tid)

    from primnox2.kernel import scheduler
    scheduler.enqueue(tid, "chat.reply", {"conversation_id": conversation, "text": "persist me"})
    wait_for_turn(tid)

    # Flushed on terminal status, so a trace on disk always describes a
    # finished turn.
    from primnox2 import paths
    assert (paths.traces_dir() / f"{tid}.json").is_file()
