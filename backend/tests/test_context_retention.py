"""Heavy tests for CONTEXT HANDLING: what actually survives into the payload
that reaches the model, across a long conversation.

Two independent layers carry context in Primnox, and these tests keep them
apart on purpose because they behave very differently:

  1. Conversation history — chat_manager stores every turn; context_manager
     .build_history() selects a *recency* suffix that fits the active model's
     token budget (model_registry.py). Chronological, no relevance ranking,
     no summarisation.
  2. Long-term memory — memory.py, searched by FTS5/bm25 *relevance* and
     injected by core.py as a "[RELEVANT MEMORIES]" block. Relevance-ranked,
     no recency ranking.

Everything here is deterministic: the chat DB and memory DB are redirected to
tmp_path, and requests.post is replaced with a capture stub, so no user data is
touched and no model is called. The assertions are made against the real
outbound request payload brain.py builds, not against a re-implementation of
it.

Architectural gaps these tests pin down (documented, not papered over):
  * build_history() DROPS old turns, it does not compress or summarise them —
    its own docstring flags summarisation as future work. An early decision in
    a long enough conversation is simply gone from history.
  * search_memories() has NO recency preference, so a superseded decision can
    outrank the decision that replaced it (see TestContradictionSupersession).
"""
import pytest

import brain
import chat_manager
import memory
import settings_manager
from context_manager import DEFAULT_RESERVE_TOKENS, estimate_tokens
from model_registry import MODEL_REGISTRY, get_model_metadata


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def chat_db(tmp_path, monkeypatch):
    """Redirect chat_manager at a throwaway sqlite file. Never the real
    %APPDATA%/primnox_extension/chat.db."""
    monkeypatch.setattr(chat_manager, "DB_FILE", str(tmp_path / "chat.db"))
    chat_manager.init_chat_db()
    return chat_manager


@pytest.fixture
def mem_db(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.db")
    memory._reset_db_connection()
    memory.init_db()
    yield memory
    memory._reset_db_connection()


class _Capture:
    """Records every outbound request payload brain.py builds."""

    def __init__(self, reply="ok"):
        self.payloads = []
        self.reply = reply

    def __call__(self, url, headers=None, json=None, timeout=None, stream=None):
        self.payloads.append(json)
        return self

    # requests.Response surface used by think_stream's non-streaming path
    status_code = 200
    headers: dict = {}
    text = ""

    def json(self):
        return {"choices": [{"message": {"content": self.reply, "tool_calls": None}}]}

    def iter_lines(self):
        return iter(())

    @property
    def last(self):
        assert self.payloads, "no request was ever sent"
        return self.payloads[-1]

    def messages(self):
        return self.last["messages"]

    def transcript(self):
        """All message content flattened to one searchable string."""
        parts = []
        for m in self.messages():
            c = m.get("content")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                parts.extend(p.get("text", "") for p in c if isinstance(p, dict))
        return "\n".join(parts)


@pytest.fixture
def capture(monkeypatch):
    cap = _Capture()
    monkeypatch.setattr(brain.requests, "post", cap)
    return cap


def _use_model(monkeypatch, active_model="Groq_Llama_3", **extra):
    settings = {
        "active_model": active_model,
        # Privacy Mirror off: it is a separate subsystem with its own tests,
        # and leaving it on would pseudonymise the very strings asserted on.
        "privacy_mirror_enabled": False,
    }
    settings.update(extra)
    monkeypatch.setattr(settings_manager, "load_settings", lambda: settings)
    monkeypatch.setattr(brain, "get_api_key", lambda provider: "sk-fake")
    monkeypatch.setattr(brain, "get_groq_api_key", lambda: "sk-fake")
    return settings


def _seed(session_id, turns):
    """turns = [(speaker, text), ...] appended in order."""
    for speaker, text in turns:
        chat_manager.append_message_to_session(session_id, text, speaker)


def _filler(n, prefix="chatter"):
    """Unrelated small talk — the noise the relevant exchange must survive."""
    out = []
    topics = ["the weather", "lunch options", "a football score", "a meme",
              "keyboard switches", "coffee", "a movie trailer", "commute traffic"]
    for i in range(n):
        topic = topics[i % len(topics)]
        out.append(("User", f"{prefix} {i}: what do you think about {topic}?"))
        out.append(("Primnox", f"{prefix} {i}: honestly {topic} is fine, no strong opinion"))
    return out


SANDBOX_DECISION = (
    "ok final answer on the sandbox: we are going with a Windows AppContainer "
    "for isolation, not a full VM, because startup cost matters more than "
    "kernel-level separation here"
)
SANDBOX_QUESTION = "What did we decide about the sandbox?"


# ── 23. Context compression / retrieval ──────────────────────────────────────

class TestRelevantExchangeSurvivesChatter:
    """A decision made earlier must still be reachable when the user asks about
    it later, and unrelated small talk must not be what fills the budget."""

    def test_earlier_decision_reaches_the_model_when_it_fits_the_budget(
            self, chat_db, capture, monkeypatch):
        _use_model(monkeypatch)
        session = chat_manager.create_session("ctx")["id"]

        _seed(session, [
            ("User", "how should we isolate code execution?"),
            ("Primnox", SANDBOX_DECISION),
        ] + _filler(12) + [("User", SANDBOX_QUESTION)])

        list(brain.think_stream(SANDBOX_QUESTION, session_id=session))

        transcript = capture.transcript()
        assert "AppContainer" in transcript, (
            "the earlier sandbox decision never reached the model — history "
            "selection dropped the one exchange the question is about"
        )
        assert SANDBOX_QUESTION in transcript

    def test_history_is_chronological_so_the_model_can_order_events(
            self, chat_db, capture, monkeypatch):
        _use_model(monkeypatch)
        session = chat_manager.create_session("ctx")["id"]
        _seed(session, [("User", f"turn {i}") for i in range(10)])

        list(brain.think_stream("and now?", session_id=session))

        transcript = capture.transcript()
        positions = [transcript.index(f"turn {i}") for i in range(10)]
        assert positions == sorted(positions), "history reached the model out of order"

    def test_unrelated_chatter_is_what_gets_dropped_first_by_the_memory_layer(
            self, mem_db):
        """The retrieval layer (memory.py) is what excludes noise — it is
        relevance-ranked, unlike history selection. Assert both halves: the
        decision is returned AND the chatter is not."""
        memory.add_memory(SANDBOX_DECISION, category="project")
        for i in range(20):
            memory.add_memory(f"user mentioned that lunch option {i} was fine", category="session")

        hits = [m["text"] for m in memory.search_memories(SANDBOX_QUESTION, limit=5)]

        assert any("AppContainer" in h for h in hits), (
            f"relevant decision not retrieved for {SANDBOX_QUESTION!r}; got {hits}"
        )
        assert not any("lunch option" in h for h in hits), (
            f"unrelated chatter leaked into the retrieved context: {hits}"
        )

    def test_long_conversation_drops_the_early_decision_from_history(
            self, chat_db, capture, monkeypatch):
        """ARCHITECTURAL GAP, pinned deliberately.

        build_history() drops oldest-first; it does not summarise. Past the
        token budget the early decision is simply absent from history — the
        only thing that can still surface it is the memory layer above. This
        test exists so that if real compression/summarisation is ever added,
        it fails loudly and gets updated rather than silently passing.
        """
        _use_model(monkeypatch)
        session = chat_manager.create_session("ctx")["id"]

        meta = get_model_metadata("Groq_Llama_3")
        budget_chars = (meta["safe_request_ceiling"] - DEFAULT_RESERVE_TOKENS) * 4
        # Enough bulk after the decision to push it out of the budget entirely.
        bulk = "z" * 4000
        _seed(session, [("Primnox", SANDBOX_DECISION)]
              + [("User", f"{bulk} {i}") for i in range(int(budget_chars / 4000) + 5)]
              + [("User", SANDBOX_QUESTION)])

        list(brain.think_stream(SANDBOX_QUESTION, session_id=session))

        transcript = capture.transcript()
        assert "AppContainer" not in transcript, (
            "history now retains the early decision past the token budget — "
            "compression/summarisation may have been implemented; update this "
            "test and the module docstring's 'gaps' list"
        )
        # ...but it must still have produced a usable, non-empty context.
        assert SANDBOX_QUESTION in transcript
        assert len(capture.messages()) >= 2


# ── 24. Decision preservation ────────────────────────────────────────────────

SQLITE_DECISION = "decision: we'll use SQLite instead of JSON for storage"
STORAGE_QUESTION = "What storage approach did we decide on?"


class TestDecisionPreservation:
    def test_decision_survives_into_the_payload(self, chat_db, capture, monkeypatch):
        _use_model(monkeypatch)
        session = chat_manager.create_session("ctx")["id"]
        _seed(session, [("User", SQLITE_DECISION)] + _filler(10)
              + [("User", STORAGE_QUESTION)])

        list(brain.think_stream(STORAGE_QUESTION, session_id=session))

        transcript = capture.transcript()
        assert "SQLite" in transcript, "the storage decision was lost from history"

    def test_decision_is_recalled_from_memory_by_a_differently_worded_question(
            self, mem_db):
        """The user does not repeat the exact words — retrieval has to bridge
        "use SQLite instead of JSON" to "what storage approach did we decide"."""
        memory.add_memory(SQLITE_DECISION, category="project")
        memory.add_memory("user's cat is named Marbles", category="personal")

        hits = [m["text"] for m in memory.search_memories(STORAGE_QUESTION, limit=5)]

        assert any("SQLite" in h for h in hits), f"decision not recalled; got {hits}"
        assert not any("Marbles" in h for h in hits)

    def test_decision_is_not_silently_deduped_away_by_a_similar_earlier_note(
            self, mem_db):
        """dedup runs at 0.85 similarity — a real decision must not be
        swallowed just because a vaguely similar sentence exists."""
        memory.add_memory("we might use JSON for storage, undecided", category="project")
        stored = memory.add_memory(SQLITE_DECISION, category="project")

        assert stored is True
        texts = [m["text"] for m in memory.list_memories()]
        assert SQLITE_DECISION in texts


# ── 25. Contradiction — the latest decision must supersede ───────────────────

JSON_DECISION = "we'll use JSON files for storage"
SWITCH_DECISION = "we've decided to switch to SQLite for storage, dropping JSON"
NOW_QUESTION = "What are we using now?"


class TestContradictionSupersession:
    def test_history_preserves_order_so_the_latest_decision_is_last(
            self, chat_db, capture, monkeypatch):
        """The mechanism that actually delivers correct supersession today:
        conversation history is chronological, so the newer decision sits
        nearer the current turn and the model reads it last."""
        _use_model(monkeypatch)
        session = chat_manager.create_session("ctx")["id"]
        _seed(session, [("User", JSON_DECISION)] + _filler(5)
              + [("User", SWITCH_DECISION)] + _filler(3)
              + [("User", NOW_QUESTION)])

        list(brain.think_stream(NOW_QUESTION, session_id=session))

        transcript = capture.transcript()
        assert JSON_DECISION in transcript and SWITCH_DECISION in transcript
        assert transcript.index(SWITCH_DECISION) > transcript.index(JSON_DECISION), (
            "the superseding decision reached the model BEFORE the one it "
            "replaces — the model has no way to tell which is current"
        )

    def test_both_decisions_are_stored_rather_than_deduped(self, mem_db):
        memory.add_memory(JSON_DECISION, category="project")
        assert memory.add_memory(SWITCH_DECISION, category="project") is True

    def test_memory_retrieval_has_NO_recency_preference(self, mem_db):
        """REAL FINDING, asserted as current behaviour rather than wished away.

        memory.search_memories() orders purely by bm25 relevance. Given a
        superseded decision and the decision that replaced it, the SUPERSEDED
        one can rank first. core.py then injects the hits as a flat
        "- {text}" list with NO timestamps (see core.py's memory_context
        block), so the model receives "we'll use JSON" ahead of "we switched
        to SQLite" and nothing in the prompt says which is newer.

        This test documents the gap precisely. If recency ranking (or
        timestamp annotation) is added, this test SHOULD fail and be replaced
        with the stronger assertion in the sibling test below.
        """
        memory.add_memory(JSON_DECISION, category="project")
        memory.add_memory(SWITCH_DECISION, category="project")

        hits = memory.search_memories(NOW_QUESTION, limit=5)
        texts = [h["text"] for h in hits]

        assert JSON_DECISION in texts and SWITCH_DECISION in texts, (
            f"both decisions should be retrievable; got {texts}"
        )
        # The ordering is relevance-only, and demonstrably not recency:
        newest_first = sorted(hits, key=lambda h: h["timestamp"], reverse=True)
        assert texts != [h["text"] for h in newest_first], (
            "search_memories now appears to return newest-first — recency "
            "ranking may have been implemented; promote the xfail sibling test"
        )

    @pytest.mark.xfail(
        reason="REAL GAP: search_memories ranks by bm25 relevance only. A "
               "superseded decision can outrank the one that replaced it, and "
               "core.py injects hits without timestamps, so the model cannot "
               "tell which is current. Fix = order by recency (or annotate "
               "each injected memory with its timestamp).",
        strict=True,
    )
    def test_latest_decision_should_rank_first(self, mem_db):
        memory.add_memory(JSON_DECISION, category="project")
        memory.add_memory(SWITCH_DECISION, category="project")

        hits = memory.search_memories(NOW_QUESTION, limit=5)

        assert hits[0]["text"] == SWITCH_DECISION

    def test_timestamps_are_available_to_fix_this_without_a_schema_change(
            self, mem_db):
        """The data needed for the fix already exists on every hit — the gap
        above is a ranking/formatting choice, not a missing column."""
        memory.add_memory(SWITCH_DECISION, category="project")
        [hit] = memory.search_memories(NOW_QUESTION, limit=5)
        assert hit["timestamp"]


# ── 26. Context limit — degrade, don't die ───────────────────────────────────

def _payload_tokens(payload):
    total = 0
    for m in payload["messages"]:
        c = m.get("content")
        if isinstance(c, str):
            total += estimate_tokens(c)
        elif isinstance(c, list):
            total += sum(estimate_tokens(p.get("text", "")) for p in c if isinstance(p, dict))
    return total


class TestContextWindowLimit:
    @pytest.mark.parametrize(
        "active_model",
        ["Groq_Llama_3", "OpenAI_GPT_4o", "Anthropic_Claude_3", "Gemini_Flash", "Ollama_Local"],
    )
    def test_oversized_conversation_is_trimmed_below_the_safe_ceiling(
            self, chat_db, capture, monkeypatch, active_model):
        """The whole point of context_manager: a conversation far past the
        model's window must come back trimmed, NOT sent whole and rejected by
        the provider with a context-length error."""
        _use_model(monkeypatch, active_model=active_model)
        session = chat_manager.create_session("ctx")["id"]

        meta = get_model_metadata(active_model, is_local=(active_model == "Ollama_Local"))
        ceiling = meta["safe_request_ceiling"]
        # Roughly 3x the model's entire safe ceiling, in realistic chunks.
        chunk = "lorem ipsum dolor sit amet " * 200          # ~5400 chars
        needed = int((ceiling * 4 * 3) / len(chunk)) + 2
        _seed(session, [("User", f"{chunk} #{i}") for i in range(needed)])

        list(brain.think_stream("summarise", session_id=session))

        assert _payload_tokens(capture.last) <= ceiling, (
            f"{active_model}: payload exceeded safe_request_ceiling "
            f"({_payload_tokens(capture.last)} > {ceiling}) — this is the "
            f"request that dies with an API context-length error"
        )

    def test_it_degrades_rather_than_emptying_the_context(
            self, chat_db, capture, monkeypatch):
        """Trimming must not be so aggressive that the model loses the thread:
        the system prompt, several recent turns, and the current question all
        have to survive."""
        _use_model(monkeypatch)
        session = chat_manager.create_session("ctx")["id"]
        chunk = "context filler " * 400
        _seed(session, [("User", f"{chunk} #{i}") for i in range(60)]
              + [("User", "MOST RECENT TURN: what is the status?")])

        list(brain.think_stream("what is the status?", session_id=session))

        msgs = capture.messages()
        assert msgs[0]["role"] == "system" and msgs[0]["content"]
        assert len(msgs) >= 3, "context collapsed to almost nothing"
        assert "MOST RECENT TURN" in capture.transcript(), (
            "the newest turn was trimmed away — trimming must drop OLDEST first"
        )

    def test_no_api_context_length_error_is_produced(
            self, chat_db, monkeypatch):
        """End-to-end shape of the failure being prevented: simulate a
        provider that rejects anything over its window, and confirm the
        oversized conversation still yields a normal answer."""
        _use_model(monkeypatch)
        session = chat_manager.create_session("ctx")["id"]
        chunk = "x" * 5000
        _seed(session, [("User", f"{chunk} #{i}") for i in range(200)])

        ceiling = get_model_metadata("Groq_Llama_3")["safe_request_ceiling"]

        class _StrictProvider:
            status_code = 200
            headers: dict = {}
            text = ""

            def __call__(self, url, headers=None, json=None, timeout=None, stream=None):
                if _payload_tokens(json) > ceiling:
                    self.status_code = 400
                    self.text = ("{'error': {'message': 'Request too large for model "
                                 "context window', 'code': 'context_length_exceeded'}}")
                return self

            def json(self):
                return {"choices": [{"message": {"content": "here is the status", "tool_calls": None}}]}

            def iter_lines(self):
                return iter(())

        monkeypatch.setattr(brain.requests, "post", _StrictProvider())

        out = "".join(t for t in brain.think_stream("status?", session_id=session) if t)

        assert "context_length_exceeded" not in out
        assert "[API ERROR" not in out
        assert "here is the status" in out

    def test_every_registry_model_has_a_ceiling_under_its_context_window(self):
        """Guard on the data the trimming depends on — a new provider entry
        whose safe ceiling exceeded its own window would silently disable the
        protection above."""
        for name, meta in MODEL_REGISTRY.items():
            assert meta["safe_request_ceiling"] <= meta["context_window"], name
            assert meta["safe_request_ceiling"] > DEFAULT_RESERVE_TOKENS, (
                f"{name}: ceiling leaves no room for the reserve"
            )


class TestCurrentTurnIsNotBudgeted:
    """ARCHITECTURAL GAP: build_history() budgets the *stored history* only.

    The current user turn, the injected context block (memories + visible UI
    text from core.py), and the tool schemas are all covered by a single flat
    DEFAULT_RESERVE_TOKENS = 2000 allowance. A large paste in the current turn
    blows straight through it — nothing clamps it.
    """

    def test_a_huge_current_turn_is_sent_unclamped(
            self, chat_db, capture, monkeypatch):
        _use_model(monkeypatch)
        session = chat_manager.create_session("ctx")["id"]
        _seed(session, [("User", "hi"), ("Primnox", "hey")])

        huge_paste = "PASTED DOCUMENT LINE. " * 20_000      # ~440k chars, ~110k tokens
        list(brain.think_stream(huge_paste, session_id=session))

        ceiling = get_model_metadata("Groq_Llama_3")["safe_request_ceiling"]
        sent = _payload_tokens(capture.last)
        assert sent > ceiling, (
            "the current turn now appears to be budgeted too — if a clamp was "
            "added, replace this test with an assertion that it stays under "
            f"the ceiling (sent={sent}, ceiling={ceiling})"
        )

    def test_the_reserve_is_the_only_allowance_for_it(self):
        assert DEFAULT_RESERVE_TOKENS == 2000
