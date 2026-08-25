"""Immutable, cache-preserving context compaction.

Compaction and caching pull in opposite directions unless compaction is
designed around the cache. A prompt cache works by matching a *prefix*: the
moment an earlier message is rewritten, every cached token after it is
invalidated and the whole prefix is re-billed. So the usual approach —
"summarise the conversation so far and replace it" — makes each compaction
cost a full cache miss, which is often more than it saved.

The rule here is therefore absolute:

    old cached prefix  →  never touched
    grown region       →  compacted ONCE into a frozen block
    new observations   →  appended after it

    [ cached prefix ][ frozen summary ][ new messages … ]
                     ↑ becomes part of the cached prefix next turn

Because the summary is immutable, it becomes part of the stable prefix on
the following turn and is itself cached. Compaction and caching compound
instead of fighting.

The default summariser is deterministic and evidence-preserving: it records
what was done, what failed, and the result IDs where the full outputs live,
so a compacted turn stays recoverable. A model summariser can be supplied,
but nothing here depends on one being reachable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from context_manager import estimate_tokens

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.compaction")
except Exception:  # pragma: no cover
    import logging

    log = logging.getLogger("v2.compaction")


# Below this, compaction is not worth a summarisation pass or the loss of
# verbatim detail.
MIN_TOKENS_TO_COMPACT = 1200

# How many trailing messages stay verbatim. The most recent exchange is what
# the model is actually reasoning about; summarising it degrades the answer
# to save tokens that had not yet accumulated.
DEFAULT_KEEP_RECENT = 4

# Token budget for the frozen summary block itself.
DEFAULT_SUMMARY_TOKENS = 350

# Result-store handles embedded in tool observations, e.g. "[result: res_ab12…]".
_RESULT_REF = re.compile(r"\bres_[0-9a-f]{16}\b")

_ERROR_LINE = re.compile(r"\b(error|failed|exception|traceback|denied|timeout)\b", re.I)

SUMMARY_HEADER = "[compacted context]"


@dataclass
class CompactionResult:
    """The outcome of a compaction pass."""

    messages: list[dict]
    boundary_index: int
    compacted: bool
    tokens_before: int
    tokens_after: int
    messages_compacted: int = 0
    summary: str = ""
    result_refs: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_before - self.tokens_after)


def _text_of(message: dict) -> str:
    """Best-effort text of a message in either V1 or OpenAI shape."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Vision-style content blocks: keep only the text parts.
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return message.get("text", "") or ""


def count_tokens(messages: list[dict]) -> int:
    """Estimated token cost of a message list."""
    return sum(estimate_tokens(_text_of(m)) for m in messages)


def _has_tool_calls(message: dict) -> bool:
    return bool(message.get("tool_calls"))


def _safe_tail_start(messages: list[dict], proposed: int) -> int:
    """Move a tail boundary forward until it is a legal place to cut.

    A `tool` message is only valid immediately after the assistant message
    that requested it. Cutting between them produces a transcript the
    provider rejects, so the boundary walks forward — into the compacted
    region, never out of it — until it lands somewhere safe.
    """
    index = max(0, min(proposed, len(messages)))
    while index < len(messages) and (
        messages[index].get("role") == "tool" or _has_tool_calls(messages[index])
    ):
        index += 1
    return index


def summarize_region(messages: list[dict], *, budget_tokens: int = DEFAULT_SUMMARY_TOKENS) -> tuple[str, list[str]]:
    """Deterministically summarise a region of transcript.

    Keeps the things a continuation actually needs — what was asked, what was
    done, what went wrong, and where the full evidence lives — and drops the
    prose. Returns the block and the result IDs it references.
    """
    asks: list[str] = []
    did: list[str] = []
    errors: list[str] = []
    refs: list[str] = []

    for message in messages:
        role = message.get("role")
        text = _text_of(message).strip()
        for ref in _RESULT_REF.findall(text):
            if ref not in refs:
                refs.append(ref)

        if not text:
            if _has_tool_calls(message):
                for call in message.get("tool_calls") or []:
                    name = (call.get("function") or {}).get("name")
                    if name:
                        did.append(f"called {name}")
            continue

        if role == "user":
            asks.append(text)
        elif role == "tool":
            name = message.get("name") or "tool"
            first = text.splitlines()[0][:160]
            (errors if _ERROR_LINE.search(text) else did).append(f"{name}: {first}")
        elif role == "assistant":
            first = text.splitlines()[0][:200]
            (errors if _ERROR_LINE.search(first) else did).append(first)

    def block(title: str, items: list[str], limit: int) -> list[str]:
        if not items:
            return []
        kept = items[-limit:]
        lines = [title] + [f"  · {item}" for item in kept]
        if len(items) > len(kept):
            lines.insert(1, f"  · …{len(items) - len(kept)} earlier omitted")
        return lines

    lines = [f"{SUMMARY_HEADER} {len(messages)} messages"]
    lines += block("Asked:", asks, 3)
    lines += block("Did:", did, 8)
    lines += block("Errors:", errors, 4)
    if refs:
        lines.append(f"Full results: {', '.join(refs[:10])}")

    text = "\n".join(lines)
    if estimate_tokens(text) > budget_tokens:
        text = text[: budget_tokens * 4].rstrip() + "\n…[summary truncated]"
    return text, refs


def compact(
    messages: list[dict],
    *,
    boundary_index: int = 0,
    keep_recent: int = DEFAULT_KEEP_RECENT,
    min_tokens: int = MIN_TOKENS_TO_COMPACT,
    budget_tokens: int = DEFAULT_SUMMARY_TOKENS,
    summarizer=None,
) -> CompactionResult:
    """Compact the region after `boundary_index`, leaving the prefix intact.

    `boundary_index` is where the already-cached prefix ends — everything
    before it is returned byte-identical, by reference, and is never passed
    to the summariser. The region between the boundary and the last
    `keep_recent` messages is replaced by one frozen block, and the returned
    `boundary_index` moves to just after that block so the next turn treats
    it as cached prefix.

    Returns unchanged input (with `compacted=False` and a reason) when there
    is nothing worth compacting — a no-op is cheaper than a cache miss.
    """
    total_before = count_tokens(messages)
    prefix = messages[:boundary_index]

    tail_start = _safe_tail_start(messages, max(boundary_index, len(messages) - keep_recent))
    region = messages[boundary_index:tail_start]
    tail = messages[tail_start:]

    if not region:
        return CompactionResult(
            messages=messages, boundary_index=boundary_index, compacted=False,
            tokens_before=total_before, tokens_after=total_before,
            reason="nothing outside the cached prefix and the recent tail",
        )

    region_tokens = count_tokens(region)
    if region_tokens < min_tokens:
        return CompactionResult(
            messages=messages, boundary_index=boundary_index, compacted=False,
            tokens_before=total_before, tokens_after=total_before,
            reason=f"region is only {region_tokens} tokens (threshold {min_tokens})",
        )

    summary, refs = summarize_region(region, budget_tokens=budget_tokens)
    origin = "deterministic"
    if summarizer is not None:
        try:
            produced = summarizer(region)
            if produced:
                summary = f"{SUMMARY_HEADER}\n{produced}"
                origin = "model"
        except Exception as exc:
            log.warning("compaction summarizer failed (%s); using deterministic summary", exc)

    frozen = {"role": "assistant", "content": summary, "compacted": True, "origin": origin}
    compacted_messages = prefix + [frozen] + tail
    total_after = count_tokens(compacted_messages)

    return CompactionResult(
        messages=compacted_messages,
        # The frozen block is stable from here on, so it belongs to the
        # cached prefix on the next turn.
        boundary_index=len(prefix) + 1,
        compacted=True,
        tokens_before=total_before,
        tokens_after=total_after,
        messages_compacted=len(region),
        summary=summary,
        result_refs=refs,
        reason=f"compacted {len(region)} messages ({region_tokens} tokens)",
    )


def prefix_unchanged(before: list[dict], after: list[dict], boundary_index: int) -> bool:
    """Verify the cached prefix survived a compaction pass byte-for-byte.

    Worth asserting rather than assuming: a compaction that quietly rewrites
    one cached message costs the entire prefix on the next request, and the
    symptom — a bill that went up after an optimisation — is a long way from
    the cause.
    """
    if boundary_index <= 0:
        return True
    if len(after) < boundary_index:
        return False
    return all(
        _text_of(before[i]) == _text_of(after[i])
        and before[i].get("role") == after[i].get("role")
        for i in range(boundary_index)
    )


def should_compact(
    messages: list[dict],
    *,
    boundary_index: int = 0,
    keep_recent: int = DEFAULT_KEEP_RECENT,
    min_tokens: int = MIN_TOKENS_TO_COMPACT,
) -> bool:
    """Cheap predicate for a tool loop: is there enough to be worth it?"""
    tail_start = _safe_tail_start(messages, max(boundary_index, len(messages) - keep_recent))
    return count_tokens(messages[boundary_index:tail_start]) >= min_tokens
