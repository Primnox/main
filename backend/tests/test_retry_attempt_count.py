"""The attempt number on a failed turn is counted, not assumed.

RecoveryBlock used to render "Attempt 1/3" on every failure, because the view
hardcoded it and the component defaulted to the same numbers. Somebody on their
third retry was told they were on their first, and told they had two tries left
against a ceiling that does not exist — a user retry creates a new turn and
nothing caps how many.

These tests pin the two things that made the fabrication possible: that the
count comes off the retry chain, and that it is reported without a denominator.
"""
from __future__ import annotations

from primnox2.chat import ephemeral, turns


def test_original_turn_is_attempt_one(conversation):
    turn = turns.create_turn(conversation, "first ask")
    assert turns.attempt_number(turn["turn_id"]) == 1


def test_each_retry_increments(conversation):
    first = turns.create_turn(conversation, "do the thing")["turn_id"]
    turns.fail(first, "provider_error", "boom", True)

    second = turns.retry_turn(first)["turn_id"]
    assert turns.attempt_number(second) == 2

    turns.fail(second, "provider_error", "boom again", True)
    third = turns.retry_turn(second)["turn_id"]
    assert turns.attempt_number(third) == 3


def test_failure_event_carries_the_real_attempt(conversation, events):
    """The number has to reach the wire — computing it and dropping it is the
    same defect wearing a different hat."""
    first = turns.create_turn(conversation, "will fail")["turn_id"]
    turns.fail(first, "provider_error", "boom", True)
    second = turns.retry_turn(first)["turn_id"]
    turns.fail(second, "provider_error", "boom", True)

    assert events.of_kind("turn.failed", first)[0]["payload"]["attempt"] == 1
    assert events.of_kind("turn.failed", second)[0]["payload"]["attempt"] == 2


def test_no_max_attempts_is_reported(conversation):
    """A user retry has no ceiling, so the payload must not imply one. The bug
    was a denominator, not just a wrong numerator."""
    turn = turns.create_turn(conversation, "no ceiling")["turn_id"]
    turns.fail(turn, "provider_error", "boom", True)

    payload = turns_failed_payload(turn)
    assert "attempt" in payload
    assert "max_attempts" not in payload
    assert "maxAttempts" not in payload


def test_unknown_turn_does_not_raise():
    """Reading a count must never be what takes down the render of the error
    the user is trying to read."""
    assert turns.attempt_number("turn_does_not_exist") == 1


def test_cycle_terminates():
    """retry_of_turn_id is a nullable self-reference. A cycle should not hang
    the request; the walk is bounded on purpose."""
    from primnox2.storage import db

    with db.tx() as c:
        c.execute("INSERT INTO conversations (id,title,incognito,created_at,updated_at)"
                  " VALUES ('conv_cycle','cycle',0,0,0)")
        # completed_at is not optional here: the schema CHECKs that a terminal
        # status and a completion timestamp agree with each other.
        for seq, tid in enumerate(("turn_a", "turn_b"), start=1):
            c.execute("INSERT INTO turns"
                      " (id,conversation_id,seq_in_conversation,status,created_at,completed_at)"
                      " VALUES (?, 'conv_cycle', ?, 'failed', 0, 0)", (tid, seq))
        c.execute("UPDATE turns SET retry_of_turn_id='turn_b' WHERE id='turn_a'")
        c.execute("UPDATE turns SET retry_of_turn_id='turn_a' WHERE id='turn_b'")

    assert turns.attempt_number("turn_a") <= 64


def test_incognito_chain_counts_without_a_table():
    """An incognito turn has no row in `turns`, so the durable walk finds
    nothing. The link lives on the in-memory record instead."""
    conv = turns.create_conversation("incognito run", incognito=True)["id"]

    first = turns.create_turn(conv, "secret ask")["turn_id"]
    assert ephemeral.attempt_number(first) == 1

    turns.fail(first, "provider_error", "boom", True)
    second = turns.retry_turn(first)["turn_id"]
    assert ephemeral.attempt_number(second) == 2


def turns_failed_payload(turn_id: str) -> dict:
    """Read the persisted failure back the way a reconnecting client would."""
    from primnox2.storage import db

    row = db.connect().execute(
        "SELECT payload FROM events WHERE turn_id=? AND kind='turn.failed'"
        " ORDER BY sequence DESC LIMIT 1", (turn_id,),
    ).fetchone()
    assert row is not None, f"no turn.failed event for {turn_id}"
    import json
    return json.loads(row["payload"])
