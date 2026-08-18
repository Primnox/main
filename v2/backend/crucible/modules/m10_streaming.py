"""Module 10 — Streaming Torture.

Replays a token stream that has been duplicated, reordered and holed, and asks
whether the reconstruction matches the clean original.

WHY THIS MATTERS MORE THAN IT LOOKS. Every other subsystem's correctness is
invisible to the user; this one is the user's entire experience of the product.
A duplicated packet shows as stuttered text, a reordered one as scrambled text,
and a dropped one as a sentence that never finishes — and all three look like
the model is broken rather than the transport.

RECOVERY BEHAVIOUR EXPECTED. The client holds a cursor; on reconnect it asks for
everything after it. Replay must return the missing events ONLY, in order, with
no duplicates — which is exactly what the gapless global sequence exists for.
"""
from __future__ import annotations

import time

from primnox2.storage import db

from ..generate import event_stream
from ..scoring import CRITICAL, HIGH, ModuleResult

KEY, NAME = "M10", "Streaming Torture"


def _reconstruct(events: list[dict]) -> str:
    """What a correct client does: order by sequence, drop repeats, join."""
    seen: set[int] = set()
    ordered = []
    for e in sorted(events, key=lambda x: x["sequence"]):
        if e["sequence"] in seen:
            continue
        seen.add(e["sequence"])
        ordered.append(e)
    return "".join(e["payload"]["text"] for e in ordered)


def run(ctx) -> ModuleResult:
    result = ModuleResult(key=KEY, name=NAME)
    started = time.perf_counter()

    stream = event_stream(count=400, seed=ctx.seed)
    rebuilt = _reconstruct(stream["mangled"])
    expected_without_dropped = "".join(
        e["payload"]["text"] for e in stream["clean"]
        if e["sequence"] not in set(stream["dropped"]))

    # Duplicates and reordering must be fully recoverable; only genuinely
    # dropped packets should be missing, and those are what replay fetches.
    dedup_ok = rebuilt == expected_without_dropped
    gap_count = len(stream["dropped"])

    # The real question: does the server's own sequence let a client detect the
    # holes at all? A gapless counter makes a gap unambiguous; without it, a
    # missing event is indistinguishable from nothing having happened.
    conn = db.connect()
    row = conn.execute("SELECT value FROM event_seq WHERE id=1").fetchone()
    counter = row["value"] if row else None
    max_seq = conn.execute("SELECT MAX(sequence) m FROM events").fetchone()["m"]
    gapless = counter is not None and (max_seq is None or max_seq <= counter)

    result.measurements = {
        "events": len(stream["clean"]),
        "duplicates_injected": 20,
        "packets_dropped": gap_count,
        "reconstruction_matches": dedup_ok,
        "event_seq_counter": counter,
        "max_event_sequence": max_seq,
        "counter_is_authoritative": gapless,
    }

    if not dedup_ok:
        result.find(
            title="Duplicate or reordered packets corrupt the reconstruction",
            severity=CRITICAL, owner="Event Bus",
            what_happened=("Replaying a duplicated and reordered stream did not "
                           "reproduce the original text."),
            reproduction="crucible.generate.event_stream(); reconstruct the mangled list.",
            probable_cause="Ordering by arrival rather than by sequence.",
            suggested_fix="Order by `sequence` and treat it as the identity of an event.",
        )

    if not gapless:
        result.find(
            title="Event sequence is not authoritative",
            severity=CRITICAL, owner="Event Bus",
            what_happened=(f"The counter reads {counter} while the highest stored "
                           f"sequence is {max_seq}. A client cannot tell a gap "
                           f"from a quiet period."),
            reproduction="Compare event_seq.value against MAX(events.sequence).",
            probable_cause="A sequence issued outside the counter transaction.",
            suggested_fix="Only ever mint a sequence by incrementing the counter row.",
        )

    # A hole must be *detectable*, which is the property that makes reconnect
    # possible. This is the check that would catch a regression to AUTOINCREMENT.
    holes = sorted(set(range(1, 401)) - {e["sequence"] for e in stream["mangled"]})
    detectable = holes == sorted(stream["dropped"])
    if not detectable:
        result.find(
            title="Dropped packets are not detectable from the sequence alone",
            severity=HIGH, owner="Event Bus",
            what_happened="The set of missing sequences did not match what was dropped.",
            reproduction="Diff the received sequences against the expected range.",
            probable_cause="Sequences are not contiguous, so absence is ambiguous.",
            suggested_fix="Keep the counter gapless; never use AUTOINCREMENT.",
        )

    result.score(
        correctness=10 if dedup_ok else 0,
        consistency=10 if detectable else 4,
        recovery=10 if (dedup_ok and detectable) else 5,
        performance=10,
        ux_stability=10 if dedup_ok else 2,
    )
    result.duration_s = time.perf_counter() - started
    return result
