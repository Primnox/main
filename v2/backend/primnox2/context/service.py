"""Context Service — a kernel pillar.

Context assembly leaves the chat path entirely. Chat asks for a bundle and
sends it; it does not decide what goes in one.

Inputs:  conversation history, referenced assets, the user's prompt
Output:  a ContextBundle — the only thing the model ever sees

Three properties the verification layer asserts directly:

  token budget respected   nothing is sent that exceeds the window
  ordering preserved       history reaches the model in the order it happened
  asset references intact  a referenced asset appears, or is named as missing

Ambient inputs (active window, clipboard) belong here too, per the
architecture. They are not wired yet — the ambient layer is V2.3 — and this
module has the seam for them rather than a pretence that they exist.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..assets import service as assets
from ..chat import ephemeral
from ..models import gateway
from ..storage import db

# Characters per token. Deliberately conservative: over-estimating the cost of
# text truncates a little early, while under-estimating it produces a request
# the provider rejects outright, which is the far worse failure.
CHARS_PER_TOKEN = 3.5

# Fraction of the model's window reserved for its reply.
OUTPUT_RESERVE = 0.25

# Never spend more than this share of the budget on asset text, so a large
# document cannot crowd out the conversation it is being discussed in.
ASSET_BUDGET_SHARE = 0.5


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / CHARS_PER_TOKEN)) if text else 0


@dataclass
class ContextBundle:
    messages: list[dict] = field(default_factory=list)
    tokens: int = 0
    budget: int = 0
    included_turns: int = 0
    dropped_turns: int = 0
    asset_ids: list[str] = field(default_factory=list)
    truncated_assets: list[str] = field(default_factory=list)
    pending_assets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tokens": self.tokens, "budget": self.budget,
            "included_turns": self.included_turns, "dropped_turns": self.dropped_turns,
            "assets": self.asset_ids, "truncated_assets": self.truncated_assets,
            "pending_assets": self.pending_assets, "notes": self.notes,
        }


def budget_for_model() -> int:
    provider, model = gateway.active_provider()
    caps = gateway.capabilities_for(getattr(provider, "base_url", "local"), model)
    return max(1024, int(caps.context_window * (1 - OUTPUT_RESERVE)))


def _history_rows(conversation_id: str, history_limit: int) -> list[dict]:
    """Prior exchanges, newest first, assistant before user within a turn.

    Two sources, one shape. An incognito conversation has no rows to select
    from — its history lives in memory for as long as the process does — and
    the selection rules have to be identical either way, or the model would see
    a differently-shaped conversation depending on which kind it is in.
    """
    if ephemeral.is_incognito(conversation_id):
        out: list[dict] = []
        for turn in sorted(ephemeral.history(conversation_id),
                           key=lambda t: t["seq"], reverse=True):
            assistant = turn.get("assistant_message")
            if turn["status"] not in ("completed", "cancelled") or not assistant:
                continue
            out.append({"role": "assistant", "text": assistant["text"],
                        "seq_in_conversation": turn["seq"]})
            user = turn.get("user_message")
            if user:
                out.append({"role": "user", "text": user["text"],
                            "seq_in_conversation": turn["seq"]})
        return out[:history_limit * 2]

    return [dict(r) for r in db.connect().execute(
        "SELECT m.role, m.text, t.seq_in_conversation"
        "  FROM messages m JOIN turns t ON t.id = m.turn_id"
        " WHERE t.conversation_id = ? AND t.status IN ('completed','cancelled')"
        "   AND EXISTS (SELECT 1 FROM messages a"
        "                WHERE a.turn_id = t.id AND a.role = 'assistant')"
        " ORDER BY t.seq_in_conversation DESC,"
        "          CASE m.role WHEN 'assistant' THEN 0 ELSE 1 END"
        " LIMIT ?",
        (conversation_id, history_limit * 2),
    ).fetchall()]


def build(
    conversation_id: str,
    user_text: str,
    *,
    turn_id: str | None = None,
    budget: int | None = None,
    system_prompt: str | None = None,
    history_limit: int = 100,
) -> ContextBundle:
    """Assemble everything the model will see for this turn."""
    bundle = ContextBundle(budget=budget or budget_for_model())
    spent = 0

    system_text = system_prompt or _default_system()
    system_cost = estimate_tokens(system_text)

    # The current prompt is not optional. It is reserved before history so a
    # long conversation can never squeeze out the thing being asked.
    user_cost = estimate_tokens(user_text)
    if system_cost + user_cost > bundle.budget:
        keep = int((bundle.budget - system_cost) * CHARS_PER_TOKEN)
        if keep < 200:
            bundle.notes.append("prompt exceeds the model's context window")
            user_text = user_text[:200]
        else:
            user_text = user_text[:keep]
            bundle.notes.append("prompt truncated to fit the context window")
        user_cost = estimate_tokens(user_text)
    spent += system_cost + user_cost

    # ── assets ────────────────────────────────────────────────────────────
    asset_block = ""
    if turn_id:
        bundle.pending_assets = assets.pending_for_turn(turn_id)
        attached = [a for a in assets.for_turn(turn_id) if a["status"] == "ready"]
        if attached:
            allowance = int((bundle.budget - spent) * ASSET_BUDGET_SHARE)
            asset_block, used, truncated = _render_assets(attached, allowance)
            bundle.asset_ids = [a["id"] for a in attached]
            bundle.truncated_assets = truncated
            spent += used

    # ── history, newest first, then restored to chronological order ───────
    # Only turns that actually produced a reply. A turn cancelled before its
    # first token has a user message and nothing else; including it puts an
    # unanswered question into the history, and the model answers THAT instead
    # of the current one.
    #
    # Measured: two stopped turns in a row left three consecutive user messages
    # in the prompt, and the reply came back about the first of them. Any user
    # who presses stop and then asks something else hits this.
    #
    # A cancelled turn WITH partial text is a real exchange and stays.
    rows = _history_rows(conversation_id, history_limit)

    selected: list[dict] = []
    seen_turns: set[int] = set()
    for r in rows:
        cost = estimate_tokens(r["text"])
        if spent + cost > bundle.budget:
            # Stop at the first message that does not fit rather than skipping
            # it and continuing: continuing would drop a turn from the middle
            # of the history and leave the model reading a conversation with a
            # hole in it.
            break
        selected.append({"role": r["role"], "content": r["text"], "seq": r["seq_in_conversation"]})
        seen_turns.add(r["seq_in_conversation"])
        spent += cost

    all_turns = {r["seq_in_conversation"] for r in rows}
    bundle.dropped_turns = len(all_turns - seen_turns)
    bundle.included_turns = len(seen_turns)

    # Reversing restores chronological order. The selection walked backwards to
    # keep the most recent context under budget; the model must still receive
    # the conversation forwards.
    selected.reverse()

    messages: list[dict] = [{"role": "system", "content": system_text}]
    if asset_block:
        messages.append({"role": "system", "content": asset_block})
    messages.extend({"role": m["role"], "content": m["content"]} for m in selected)
    messages.append({"role": "user", "content": user_text})

    bundle.messages = messages
    bundle.tokens = spent
    return bundle


def _render_assets(attached: list[dict], allowance: int) -> tuple[str, int, list[str]]:
    """Render asset text into one system block, fairly divided."""
    if allowance <= 0 or not attached:
        return "", 0, []

    per_asset = max(200, allowance // len(attached))
    truncated: list[str] = []
    parts: list[str] = []
    used = 0

    for a in attached:
        text = a.get("extracted_text") or ""
        header = f'--- {a["original_name"]} (asset {a["id"]}) ---'
        if not text:
            # The reference stays in the bundle even with no text, so the model
            # is told the file exists and why it cannot read it — rather than
            # being handed silence and inventing an answer.
            meta = a.get("metadata") or "{}"
            why = "needs OCR" if "ocr_required" in str(meta) else "no text could be extracted"
            parts.append(f"{header}\n[{why}]")
            used += estimate_tokens(header) + 8
            continue

        limit_chars = int(per_asset * CHARS_PER_TOKEN)
        if len(text) > limit_chars:
            text = text[:limit_chars] + "\n… document truncated …"
            truncated.append(a["id"])
        parts.append(f"{header}\n{text}")
        used += estimate_tokens(text) + estimate_tokens(header)

    block = "Attached documents:\n\n" + "\n\n".join(parts)
    return block, used, truncated


def _default_system() -> str:
    return (
        "You are Primnox, a local-first assistant. Be direct and concrete. "
        "When you reference an attached document, name it."
    )
