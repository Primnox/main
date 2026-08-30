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

# Every number below is a DECLARED TUNABLE (settings/tunables.py), resolved per
# call: environment, then stored setting, then default. They are read through
# functions rather than bound at import so a change in the settings screen takes
# effect on the next turn instead of the next restart.
#
# The one that mattered: history was capped at a hardcoded 100 turns, which
# truncated a 500-turn conversation while 87% of the model's window sat unused
# and dropped the turns the user had cited by number. Crucible scored that
# CRITICAL. The cap is now a safety valve two orders of magnitude higher, and
# the token budget is what actually decides.
from ..settings import tunables


def _tune(key: str):
    return tunables.get(key)


def chars_per_token() -> float:
    return _tune("context.chars_per_token")


def output_reserve() -> float:
    return _tune("context.output_reserve")


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / chars_per_token())) if text else 0


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
    retrieved: list[str] = field(default_factory=list)   # which sources fired

    def to_dict(self) -> dict:
        return {
            "tokens": self.tokens, "budget": self.budget,
            "included_turns": self.included_turns, "dropped_turns": self.dropped_turns,
            "assets": self.asset_ids, "truncated_assets": self.truncated_assets,
            "pending_assets": self.pending_assets, "notes": self.notes,
            "retrieved": self.retrieved,
        }


def budget_for_model() -> int:
    provider, model = gateway.active_provider()
    caps = gateway.capabilities_for(getattr(provider, "base_url", "local"), model)
    return max(1024, int(caps.context_window * (1 - output_reserve())))


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

    rows = [dict(r) for r in db.connect().execute(
        "SELECT m.role, m.text, t.seq_in_conversation, t.id AS turn_id"
        "  FROM messages m JOIN turns t ON t.id = m.turn_id"
        " WHERE t.conversation_id = ? AND t.status IN ('completed','cancelled')"
        "   AND EXISTS (SELECT 1 FROM messages a"
        "                WHERE a.turn_id = t.id AND a.role = 'assistant')"
        " ORDER BY t.seq_in_conversation DESC,"
        "          CASE m.role WHEN 'assistant' THEN 0 ELSE 1 END"
        " LIMIT ?",
        (conversation_id, history_limit * 2),
    ).fetchall()]
    return _with_workspace_breadcrumbs(rows)


def _with_workspace_breadcrumbs(rows: list[dict]) -> list[dict]:
    """Note which workspace(s) a past assistant turn touched, so a later turn
    can find them again instead of guessing.

    Measured live: a turn that only called create_workspace — nothing else,
    because the model had nothing left to say once the tool ran — persists
    an assistant message that is blank. Whitespace has no signal in it, so
    the next turn's history shows a question with no answer, and the model
    either claims the work never happened or invents an id for
    update_workspace to fail on. workspace_files already knows the real
    content (read_workspace, above, is the honest way to fetch it) and
    turn_workspaces already knows which turn made it — this just says so,
    at the one place history is read for replay, so nothing written to disk
    has to change and no other reader of `messages.text` is affected.
    """
    try:
        from ..workspaces import service as workspaces
    except Exception:
        return rows

    for r in rows:
        if r.get("role") != "assistant" or not r.get("turn_id"):
            continue
        try:
            touched = workspaces.for_turn(r["turn_id"])
        except Exception:
            continue
        if not touched:
            continue
        note = "; ".join(
            f'workspace {w["id"]} "{w["title"]}" ({w["kind"]}, v{w["current_version"]})'
            for w in touched
        )
        breadcrumb = f"[{note} — call read_workspace with this id to see its current content]"
        r["text"] = (r["text"] + "\n\n" + breadcrumb) if (r["text"] or "").strip() else breadcrumb
    return rows


def build(
    conversation_id: str,
    user_text: str,
    *,
    turn_id: str | None = None,
    budget: int | None = None,
    system_prompt: str | None = None,
    extra_system: str | None = None,
    history_limit: int | None = None,
) -> ContextBundle:
    """Assemble everything the model will see for this turn."""
    bundle = ContextBundle(budget=budget or budget_for_model())
    spent = 0

    system_text = system_prompt or _default_system()
    # Everything the caller will actually put in front of the model, costed
    # here rather than bolted on afterwards. The tool grammar (~2,530 tokens)
    # and any inlined skill bodies (up to `skills.inline_budget_chars`, ~9,100
    # tokens) used to be inserted into `bundle.messages` by the scheduler after
    # this function had already returned, so `budget_for_model()` under-counted
    # every request by up to ~11,600 tokens — and the retrieval and history
    # below were sized against a budget that had already been spent.
    if extra_system:
        system_text = system_text + "\n\n" + extra_system
    system_cost = estimate_tokens(system_text)

    # The current prompt is not optional. It is reserved before history so a
    # long conversation can never squeeze out the thing being asked.
    user_cost = estimate_tokens(user_text)
    if system_cost + user_cost > bundle.budget:
        keep = int((bundle.budget - system_cost) * chars_per_token())
        if keep < 200:
            bundle.notes.append("prompt exceeds the model's context window")
            user_text = user_text[:200]
        else:
            user_text = user_text[:keep]
            bundle.notes.append("prompt truncated to fit the context window")
        user_cost = estimate_tokens(user_text)
    spent += system_cost + user_cost

    # ── retrieval, done by the runtime ────────────────────────────────────
    # FIRST, before assets and before history. The order is the architecture:
    # the graph is what the model is given, and raw text is what it falls back
    # to. Running retrieval after assets meant a single large document could
    # consume the window and leave the graph — the cheaper, more precise source
    # — nothing to spend.
    #
    # It also survives truncation. A chat fifty turns deep is exactly where the
    # model most needs reminding what the codebase looks like, and exactly
    # where history would otherwise have eaten the budget first.
    graph_budget = max(_tune("context.graph_tokens_min"),
                       min(_tune("context.graph_tokens_max"),
                           int((bundle.budget - spent) * _tune("context.graph_share"))))
    retrieval_blocks: list[str] = []
    for label, text in _retrieve(conversation_id, user_text, graph_budget):
        cost = estimate_tokens(text)
        if spent + cost > bundle.budget:
            continue
        retrieval_blocks.append(text)
        bundle.retrieved.append(label)
        spent += cost

    # ── assets, only what the graph did not already cover ─────────────────
    asset_block = ""
    if turn_id:
        bundle.pending_assets = assets.pending_for_turn(turn_id)
        attached = [a for a in assets.for_turn(turn_id) if a["status"] == "ready"]
        # An asset already reachable through the graph is not pasted in whole.
        # This is the token argument the whole design rests on: the graph answer
        # is bounded by its budget, the document is bounded by nothing.
        indexed = _indexed_assets({a["id"] for a in attached})
        unindexed = [a for a in attached if a["id"] not in indexed]
        bundle.asset_ids = [a["id"] for a in attached]
        if indexed:
            bundle.retrieved.append(f"assets_via_graph:{len(indexed)}")
        if unindexed:
            allowance = int((bundle.budget - spent) * _tune("context.asset_share"))
            asset_block, used, truncated = _render_assets(unindexed, allowance)
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
    rows = _history_rows(conversation_id,
                         history_limit or _tune("context.history_turns"))

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
    for block in retrieval_blocks:
        messages.append({"role": "system", "content": block})
    if asset_block:
        messages.append({"role": "system", "content": asset_block})
    messages.extend({"role": m["role"], "content": m["content"]} for m in selected)
    messages.append({"role": "user", "content": user_text})

    bundle.messages = messages
    bundle.tokens = spent
    return bundle


def _indexed_assets(asset_ids: set[str]) -> set[str]:
    """Which of these assets already have nodes in the knowledge graph."""
    if not asset_ids:
        return set()
    try:
        placeholders = ",".join("?" * len(asset_ids))
        rows = db.connect().execute(
            f"SELECT DISTINCT scope FROM knowledge_nodes"
            f" WHERE scope IN ({placeholders})",
            tuple(f"asset:{a}" for a in asset_ids),
        )
        return {r["scope"].split(":", 1)[1] for r in rows}
    except Exception:
        return set()


def _retrieve(conversation_id: str, user_text: str,
              graph_budget: int | None = None) -> list[tuple[str, str]]:
    """Everything the runtime looks up on the user's behalf, before the model runs.

    Each source is guarded independently. Retrieval is an enhancement; a graph
    that fails to load must cost the answer its extra context, never the answer
    itself — and these run on the hot path of every single turn.
    """
    out: list[tuple[str, str]] = []

    # Permanent memory: who the user is. Injected whole, because it is small by
    # construction and filtering it by relevance would mean a preference only
    # applies to questions that happen to mention it.
    try:
        from ..memory import service as memory

        block = memory.render_for_prompt()
        if block:
            out.append(("memory", _clip(block, _tune("context.memory_tokens"))))
    except Exception:
        pass

    # The conversation's own graph: what THIS chat has established.
    try:
        from ..knowledge import live

        graph = live.for_conversation(conversation_id)
        block = graph.render(limit=12)
        if block:
            out.append(("conversation", _clip(
                "Established in this conversation:\n" + block, _tune("context.live_tokens"))))
    except Exception:
        pass

    # The knowledge graph: what the indexed corpus says about the words the
    # user actually used.
    try:
        from ..knowledge import graph as knowledge

        hits = knowledge.query(user_text, token_budget=graph_budget)
        if hits:
            out.append(("graph",
                        "Relevant code and documents, with citations. Cite the "
                        "file and line when you use one:\n" + hits))
    except Exception:
        pass

    return out


def _clip(text: str, token_budget: int) -> str:
    limit = int(token_budget * chars_per_token())
    if len(text) <= limit:
        return text
    cut = text[:limit].rfind("\n")
    return text[: cut if cut > 0 else limit] + "\n…"


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

        limit_chars = int(per_asset * chars_per_token())
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
