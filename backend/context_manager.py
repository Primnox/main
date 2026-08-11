"""Token-budgeted conversation history selection.

Replaces the flat `[-20:]` message-count cutoff + 16000-char-per-message cap
that used to live inline in brain.py's streaming path (comment there was
"Limit to 20 to prevent Groq crash" — a guess-based cap with no relationship
to what a given model/provider can actually handle). This module makes that
selection model-aware via model_registry.py instead.

Deliberately a *pure selection* function (no mutation, no DB writes, no
truncation of individual message text) so "drop oldest messages that don't
fit" can later be swapped for "replace oldest messages with an LLM summary"
(following memory.py's existing `compress_old_memories` pattern) without
touching call sites.

Scope note: this is only for the primary conversation history of the
session being continued. It intentionally does NOT cover the separate
`#hex`-cross-session-reference lookup in brain.py (a small fixed-budget
peek at a *different* chat, not the current conversation) — that keeps its
own independent, much smaller fixed cap.
"""

from model_registry import get_model_metadata

# Reserved for the system prompt, current user turn, tool schemas, and the
# model's own output — kept out of the history budget entirely.
DEFAULT_RESERVE_TOKENS = 2000

# Belt-and-suspenders ceiling independent of the token estimate: guards
# against a degenerate case (e.g. thousands of one-word messages) where a
# crude char-based token estimate could under-count and let an oversized
# request through purely on message count.
MAX_MESSAGE_COUNT = 80


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token for English).
    Not exact, but this only needs to be right enough to stay under a
    conservative safety ceiling, not match a real tokenizer."""
    if not text:
        return 1
    return max(1, len(text) // 4)


def build_history(
    messages: list[dict],
    active_model: str,
    is_local: bool = False,
    reserve_tokens: int = DEFAULT_RESERVE_TOKENS,
    max_message_count: int = MAX_MESSAGE_COUNT,
) -> list[dict]:
    """Selects the most recent messages from `messages` that fit under the
    active model's safe token budget, newest-first fill then reordered back
    to chronological order. Always keeps at least the single most recent
    message, even if it alone exceeds the budget (matches the old code's
    behavior of never producing an empty history for a single huge message).
    """
    if not messages:
        return []

    meta = get_model_metadata(active_model, is_local)
    budget = max(0, meta["safe_request_ceiling"] - reserve_tokens)

    candidates = messages[-max_message_count:] if max_message_count else list(messages)

    kept: list[dict] = []
    used = 0
    for msg in reversed(candidates):
        text = msg.get("text", "")
        cost = estimate_tokens(text)
        if used + cost > budget and kept:
            break
        kept.append(msg)
        used += cost

    kept.reverse()
    return kept
