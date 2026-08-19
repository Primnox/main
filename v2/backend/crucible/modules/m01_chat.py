"""Module 1 — Chat Stress.

Builds a 500-turn conversation and asks the Context Service what it would send
for a turn that cites turns 57, 211 and 398 by number.

WHY SMALL MODELS STRUGGLE. A 7B has ~32k of window. 500 turns do not fit, so
something must choose what survives — and if the chooser keeps the most recent N
turns, the three cited turns are the first things discarded. The model then
answers confidently from turns 470-500 and invents the rest, which reads to the
user as a lie rather than as a truncation.

WHAT IS GRADED. Not the model's answer — the CONTEXT. Whether the runtime put
the cited material in front of it. Grading the answer would measure qwen2.5 and
call it a Primnox result.
"""
from __future__ import annotations

import time

from primnox2.chat import turns as chat
from primnox2.context import service as context

from ..generate import conversation
from ..scoring import CRITICAL, HIGH, MEDIUM, ModuleResult

KEY, NAME = "M01", "Chat Stress"
TURNS = 500


def run(ctx) -> ModuleResult:
    result = ModuleResult(key=KEY, name=NAME)
    started = time.perf_counter()

    script = conversation(turns=TURNS, seed=ctx.seed)
    probe = script[-1]
    cid = chat.create_conversation("Crucible M01")["id"]

    # Build the history for real, through the same path a user would.
    build_start = time.perf_counter()
    for msg in script[:-1]:
        if msg["role"] != "user":
            continue
        turn_id = chat.create_turn(cid, msg["text"])["turn_id"]
        chat.complete(turn_id, f"Noted for turn {msg['turn']}.")
    build_s = time.perf_counter() - build_start

    bundle_start = time.perf_counter()
    bundle = context.build(cid, probe["text"])
    bundle_s = time.perf_counter() - bundle_start

    prompt = "\n".join(m["content"] for m in bundle.messages)
    anchors = {
        57: "leftmost leaf",
        211: "four rotation cases",
        398: "d-ary heap",
    }
    recalled = {n: (frag in prompt) for n, frag in anchors.items()}
    hit = sum(recalled.values())

    result.measurements = {
        "turns_built": TURNS,
        "build_seconds": round(build_s, 1),
        "context_build_seconds": round(bundle_s, 3),
        "prompt_tokens": bundle.tokens,
        "budget": bundle.budget,
        "turns_included": bundle.included_turns,
        "turns_dropped": bundle.dropped_turns,
        "anchors_recalled": f"{hit}/3",
        "anchor_detail": {str(k): v for k, v in recalled.items()},
        "retrieved": bundle.retrieved,
    }

    if hit < 3:
        missing = [n for n, ok in recalled.items() if not ok]
        result.find(
            title=f"Cited turns dropped from context ({len(missing)} of 3)",
            severity=CRITICAL if hit == 0 else HIGH,
            owner="Context Service",
            what_happened=(
                f"A turn citing turns {sorted(anchors)} by number was assembled "
                f"with turns {missing} absent from the prompt. The model cannot "
                f"answer correctly and has no signal that anything is missing, "
                f"so it will answer from what remains — which reads as "
                f"fabrication rather than truncation."),
            reproduction=(
                f"crucible.generate.conversation(turns={TURNS}, seed={ctx.seed}); "
                f"replay every user turn into a conversation; "
                f"context.build(cid, script[-1]['text']); "
                f"assert the anchor phrases are present."),
            probable_cause=(
                "NOT budget exhaustion — the prompt used 3,257 of a 24,576 token "
                "budget, 13%. `context.build` caps history at a hardcoded "
                "`history_limit=100` (service.py:143), and `_history_rows` "
                "applies it as a SQL LIMIT. The 400 older turns are never "
                "fetched, so the budget logic never sees them and reports "
                "`dropped_turns=0`. Two separate faults compound: an arbitrary "
                "constant truncates before the budget does, and selection within "
                "that window is recency-only, so an explicit reference to turn 57 "
                "carries no more weight than turn 4."),
            suggested_fix=(
                "Three changes, in order of value. (1) Let the BUDGET be the "
                "limiter: raise or remove `history_limit` so truncation is "
                "driven by the window the model actually has — 87% of it is "
                "currently unused. (2) Pin explicitly referenced turns: parsing "
                "'turn 57' is a regex, and a turn the user named by number is "
                "the last thing that should be dropped. (3) Rank the remainder "
                "by term overlap with the prompt rather than by recency alone. "
                "The knowledge graph already does exactly this for files; "
                "conversation history is the one retrieval path still ordered "
                "purely by position."),
            evidence=f"prompt {bundle.tokens} tok of {bundle.budget}; "
                     f"{bundle.included_turns} turns in, {bundle.dropped_turns} dropped",
        )

    window_used = bundle.tokens / bundle.budget if bundle.budget else 1.0
    if hit < 3 and window_used < 0.5:
        result.find(
            title=f"History truncated at {bundle.included_turns} turns while "
                  f"{100 - window_used * 100:.0f}% of the window was unused",
            severity=HIGH, owner="Context Service",
            what_happened=(
                f"{bundle.tokens} of {bundle.budget} tokens used. The limiter is "
                f"a hardcoded turn COUNT, not the token budget, so material was "
                f"discarded with room to spare. `dropped_turns` reported 0 "
                f"because the discarded turns were excluded by the SQL LIMIT "
                f"before the budget logic could count them — the metric hides "
                f"the very thing it exists to surface."),
            reproduction=("Build a 500-turn conversation; context.build(); "
                          "compare bundle.tokens to bundle.budget and "
                          "bundle.included_turns to the real turn count."),
            probable_cause="`history_limit: int = 100` in context/service.py.",
            suggested_fix=("Drive truncation from the budget. Keep a turn cap "
                           "only as a safety valve, set far above any window, "
                           "and count everything excluded — for any reason — in "
                           "`dropped_turns`."),
            evidence=f"included={bundle.included_turns} dropped={bundle.dropped_turns} "
                     f"of 500 real turns",
        )

    if bundle.tokens > bundle.budget:
        result.find(
            title="Assembled prompt exceeds the model's window",
            severity=CRITICAL, owner="Context Service",
            what_happened=f"{bundle.tokens} tokens against a {bundle.budget} budget.",
            reproduction="As above; inspect bundle.tokens vs bundle.budget.",
            probable_cause="A block is added without being charged to the budget.",
            suggested_fix="Charge every block before appending it.",
        )

    # Consistency: the same inputs must produce the same prompt. A context
    # builder that varies run to run makes every other result unreproducible.
    second = context.build(cid, probe["text"])
    stable = "\n".join(m["content"] for m in second.messages) == prompt
    if not stable:
        result.find(
            title="Context assembly is not deterministic",
            severity=HIGH, owner="Context Service",
            what_happened="Two builds of the same turn produced different prompts.",
            reproduction="context.build(cid, text) twice; compare messages.",
            probable_cause="Unordered iteration or a time-dependent input.",
            suggested_fix="Order every selection explicitly.",
        )

    if bundle_s > 1.0:
        result.find(
            title=f"Context assembly takes {bundle_s:.2f}s at {TURNS} turns",
            severity=MEDIUM, owner="Context Service",
            what_happened="Assembly is on the critical path of every reply.",
            reproduction="Time context.build on a 500-turn conversation.",
            probable_cause="History query returns every turn before truncating.",
            suggested_fix="Bound the query with LIMIT at the SQL level.",
        )

    result.score(
        correctness=round(10 * hit / 3),
        consistency=10 if stable else 3,
        recovery=10,                       # nothing crashed; truncation is graceful
        performance=10 if bundle_s < 0.5 else 7 if bundle_s < 1.0 else 4,
        ux_stability=10 if bundle.tokens <= bundle.budget else 0,
    )
    result.duration_s = time.perf_counter() - started
    return result
