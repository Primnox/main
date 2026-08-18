"""Module 7 — Memory Torture.

Writes months of preferences, then reverses three of them, then asks the two
questions a memory system has to get right: which preference changed most
recently, and what is true now.

WHY SMALL MODELS STRUGGLE. Given "I prefer dark mode" and "I prefer light mode
now" in one prompt, a 7B picks whichever is nearer the end. The store must not
hand it both as equals — resolving contradictions is the runtime's job, and
pushing it to the model is how a memory system becomes a random-answer generator.

RECOVERY BEHAVIOUR EXPECTED. A superseded memory is not deleted; it is ordered
behind the newer one. "What did I used to prefer" must stay answerable.
"""
from __future__ import annotations

import time

from primnox2.memory import service as memory
from primnox2.storage import db

from ..generate import memory_timeline
from ..scoring import HIGH, MEDIUM, ModuleResult

KEY, NAME = "M07", "Memory Torture"


def run(ctx) -> ModuleResult:
    result = ModuleResult(key=KEY, name=NAME)
    started = time.perf_counter()

    with db.tx() as c:
        c.execute("DELETE FROM memories")

    timeline = memory_timeline(seed=ctx.seed)
    for entry in timeline:
        memory.remember(entry["text"], category=entry["category"])
        # Ordered writes: chronology is the thing under test, so the entries
        # must land in a knowable order rather than inside one millisecond.
        time.sleep(0.002)

    live = memory.live()
    contradictions = [e for e in timeline if e.get("contradicts")]

    # 1. Is the newest statement reachable first?
    newest = live[0]["text"] if live else ""
    chronology_ok = newest == timeline[-1]["text"]

    # 2. Are both sides of each contradiction still present, and does search
    #    surface the newer one first?
    resolved, unresolved = 0, []
    for entry in contradictions:
        hits = memory.search(entry["text"][:24])
        if hits and hits[0]["text"] == entry["text"]:
            resolved += 1
        else:
            unresolved.append(entry["text"])

    # 3. The prompt block: what the model is actually told.
    block = memory.render_for_prompt()
    both_present = all(
        e["contradicts"] in block and e["text"] in block for e in contradictions)

    result.measurements = {
        "written": len(timeline),
        "live": len(live),
        "contradictions": len(contradictions),
        "newer_ranked_first": f"{resolved}/{len(contradictions)}",
        "chronology_preserved": chronology_ok,
        "both_sides_in_prompt": both_present,
        "prompt_block_chars": len(block),
    }

    if not chronology_ok:
        result.find(
            title="Most recent memory is not the most recent row",
            severity=HIGH, owner="Memory Service",
            what_happened=f"Expected {timeline[-1]['text']!r} first, got {newest!r}.",
            reproduction="Write crucible.generate.memory_timeline() in order; read memory.live().",
            probable_cause="Ordering by a column that is not write time.",
            suggested_fix="ORDER BY created_at DESC with an id tie-break.",
        )

    if both_present:
        result.find(
            title="Contradicting memories are given to the model as equals",
            severity=HIGH, owner="Memory Service",
            what_happened=(
                "The prompt block contains both 'I prefer dark mode' and 'I "
                "prefer light mode now', with nothing marking which supersedes "
                "which. Resolution is pushed onto the model, and a 7B resolves "
                "it by position — so the answer depends on write order rather "
                "than on what the user last said."),
            reproduction=(
                "Write the timeline; call memory.render_for_prompt(); observe "
                "both sides of each reversal present and unordered."),
            probable_cause=(
                "`remember()` suppresses near-DUPLICATES by word overlap, but a "
                "reversal is not a duplicate — 'dark' and 'light' differ by one "
                "token and the Jaccard score stays below the threshold. Nothing "
                "in the store models supersession."),
            suggested_fix=(
                "Add a supersedes edge. On write, find live memories in the same "
                "category above a similarity floor, and mark them superseded "
                "rather than deleted — 'what did I used to prefer' stays "
                "answerable, and render_for_prompt() emits only the live head of "
                "each chain. This is the same shape as knowledge_edges; the "
                "memory store is the one place still treating facts as a flat "
                "list."),
            evidence=f"{len(contradictions)} reversals, all with both sides in the block",
        )

    if resolved < len(contradictions):
        result.find(
            title=f"Search ranks a superseded memory above its replacement "
                  f"({len(contradictions) - resolved} of {len(contradictions)})",
            severity=MEDIUM, owner="Memory Service",
            what_happened=f"Older statements ranked first for: {unresolved}",
            reproduction="memory.search() on the text of a reversing memory.",
            probable_cause="Ranking is word overlap only; recency is not a term.",
            suggested_fix="Break overlap ties by created_at DESC.",
        )

    result.score(
        correctness=10 if chronology_ok else 4,
        consistency=round(10 * resolved / max(len(contradictions), 1)),
        # Nothing was lost — both sides survive, which is the recoverable state.
        recovery=10,
        performance=10,
        ux_stability=4 if both_present else 10,
    )
    result.duration_s = time.perf_counter() - started
    return result
