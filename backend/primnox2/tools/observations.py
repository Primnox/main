"""Tool results as an append-only ledger, so a turn stops paying for its past.

Measured against a real provider, the cost of a turn is superlinear in steps:
350, 848, 2,283 and 7,032 billed token-equivalents at one, two, four and eight
steps. Eight steps costs 20x one step, not 8x. The extra is not output size —
it is that every tool result is re-sent, and re-billed, on every step that
follows it. Result one is paid eight times.

Caching recovers some of that (7,032 down to 4,376 at eight steps) and cannot
fix it, because caching makes re-sending cheaper rather than making it stop.
This makes it stop.

THE RULE THAT SHAPES EVERYTHING HERE: nothing already sent may be rewritten.

That is not tidiness, it is the whole reason caching keeps working. Both the
local KV cache and a provider cache key on an exact prefix, so editing an
earlier message invalidates everything after it — a reducer that rewrote
history each step would pay a cache write every step and never collect a
read, losing more than compaction saves. The two optimisations look additive
and are actually in opposition unless the compacted form is immutable.

Which rules out the obvious design. "Keep the newest result in full, compact
the older ones" requires going back and editing a message that has already
been sent. So the decision is made ONCE, at the moment a result is appended,
and never revisited:

    under the threshold   append the result in full
    over the threshold    append a compact observation, forever

Early results in a turn are cheap and stay verbatim. Once a turn has
accumulated enough tool output to be worth worrying about, everything after
that point is compact. No message is ever touched twice.

NOTHING IS LOST. Every compact observation names the asset holding the full
result, and `read_asset` fetches it. The model trades having everything in
front of it for having to ask — which is the same trade a person makes with a
filing cabinet.
"""
from __future__ import annotations

# When a turn's accumulated tool output crosses this, later results are
# appended compact. Deliberately not zero: at one and two steps the measured
# cost is 350 and 848 tokens, the preamble dominates, and compacting there
# would trade real information for a saving too small to measure. The
# superlinear part only bites from about four steps on.
COMPACT_AFTER_TOKENS = 1200

# What a compact observation may cost. Enough for a status line, a count and a
# handful of names — the things a model needs to decide what to do next —
# without the body it can retrieve if it turns out to need it.
OBSERVATION_TOKENS = 120


def _estimate(text: str) -> int:
    from ..context.service import estimate_tokens
    return estimate_tokens(text)


class Ledger:
    """One turn's tool output, and the decision of what to send for each.

    Holds only counters and the decisions already made. It does not hold the
    message list and cannot edit it — the caller appends what this returns,
    which is what makes "never rewrite" structural rather than a convention
    somebody has to remember.
    """

    def __init__(self, *, threshold: int = COMPACT_AFTER_TOKENS) -> None:
        self.threshold = threshold
        self.accumulated = 0
        self.count = 0
        # What was compacted, so a turn can say so and a benchmark can check
        # it actually happened rather than trusting that it did.
        self.compacted: list[str] = []

    def record(self, formatted: str, result: dict) -> str:
        """The text to append for this result — full, or compact.

        Called once per tool result, in order. The answer for a given result
        never changes after this returns.
        """
        self.count += 1
        cost = _estimate(formatted)

        if self.accumulated < self.threshold:
            # Still cheap. Send it whole, and count it against the budget so
            # the NEXT one knows.
            self.accumulated += cost
            return formatted

        # Already small, or with nowhere to point. Both mean compaction is the
        # wrong move, for different reasons.
        #
        # A result that fits in roughly an observation saves nothing by
        # becoming one. And a result with no `result_ref` was never written to
        # an asset — `_store_output` only promotes output ABOVE the inline cap
        # — so replacing it with a summary would not defer the detail, it
        # would destroy it. Compaction that loses information is not
        # compaction.
        if cost <= OBSERVATION_TOKENS * 2 or not result.get("result_ref"):
            self.accumulated += cost
            return formatted

        observation = self.observe(result)
        self.accumulated += _estimate(observation)
        self.compacted.append(f"R{self.count}")
        return observation

    def observe(self, result: dict) -> str:
        """A result reduced to what the next decision needs.

        Status, the summary the tool already wrote, and a pointer. Deliberately
        built from fields the tool produced rather than by summarising its
        output: a parser can compress machine-generated text, and spending
        model tokens to compress information that was structured to begin with
        is the cost this module exists to avoid.
        """
        name = result.get("tool", "tool")
        status = result.get("status", "success")
        summary = (result.get("summary") or "").strip()

        lines = [f"Observation R{self.count}: {name} "
                 f"{'completed' if status == 'success' else 'failed'}."]
        if summary:
            lines.append(f"Summary: {summary[:400]}")

        # The pointer is what makes this lossless. Without an id the model has
        # no way back to the detail and compaction becomes deletion.
        ref = result.get("result_ref")
        if ref:
            lines.append(f'Full output is asset {ref} — read_asset it if you '
                         f'need the detail.')
        else:
            lines.append("The full output was not stored; this summary is all "
                         "that remains of it.")

        if status != "success":
            lines.append("Fix the cause before retrying.")

        text = "\n".join(lines)
        cap = OBSERVATION_TOKENS * 4
        return text if len(text) <= cap else text[:cap] + "…"


def strategy(predicted_steps: int) -> dict:
    """How a turn of this predicted length should be sent.

    One decision point, taken from one signal, because the two knobs answer to
    the same fact. Caching a conversation costs a cache WRITE every step and
    only repays it if the prefix is read back enough times — measured, it is a
    1% LOSS at one step, breaks even at two, and reaches 38% at eight. So the
    same estimate that says "this needs one call" also says "do not cache",
    and there is no reason for those to be separate settings anybody can set
    inconsistently.
    """
    if predicted_steps < 2:
        return {"cache_conversation": False, "compact": False,
                "why": "one step — nothing recurs, so a cache write never pays"}
    if predicted_steps < 4:
        return {"cache_conversation": True, "compact": False,
                "why": "short — caching breaks even, accumulation is not yet "
                       "the problem"}
    return {"cache_conversation": True, "compact": True,
            "why": "long — accumulated results dominate, and they grow "
                   "superlinearly"}
