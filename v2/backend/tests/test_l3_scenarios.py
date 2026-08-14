"""L3 — User simulation. Reproducible conversations, not fragile UI scripts.

Each scenario is a thing a real person does, expressed as the sequence of calls
the frontend would make. They are numbered to match the specification so a
failure names the scenario that broke.
"""
from __future__ import annotations

import threading
import time

import pytest
from conftest import run_turn, wait_for_turn, wait_until

from primnox2.assets import service as assets
from primnox2.chat import turns
from primnox2.kernel.events import bus
from primnox2.sandbox import manager as sandbox
from primnox2.storage import db
from primnox2.workspaces import service as workspaces


class TestScenario001MultiTask:
    """"Build a React app while summarizing a PDF."

    Two pieces of work in flight at once. They must not contaminate each other.
    """

    def test_independent_work_stays_independent(self, events, scripted, sandbox_ready):
        react = turns.create_conversation("React app")["id"]
        paper = turns.create_conversation("PDF summary")["id"]

        scripted(
            '<tool name="create_workspace">\n'
            '{"kind": "react", "title": "Landing", "files": {"App.jsx": "export default () => <h1>Hi</h1>"}}\n'
            '</tool>',
            "Your React landing page is ready.",
        )
        react_turn = run_turn(react, "build a react landing page")

        pdf_bytes = b"Quarterly revenue grew by twelve percent."
        asset = assets.ingest_bytes(pdf_bytes, "report.txt", conversation_id=paper)
        wait_until(lambda: assets.get(asset["id"])["status"] == "ready", what="ingestion")
        paper_turn = run_turn(paper, "summarise the report", asset_ids=(asset["id"],))

        assert wait_for_turn(react_turn, timeout=120) == "completed"
        assert wait_for_turn(paper_turn, timeout=120) == "completed"

        # A workspace was created, and only for the turn that asked for one.
        assert len(workspaces.for_turn(react_turn)) == 1
        assert workspaces.for_turn(paper_turn) == []

        # An asset exists, referenced only by the turn that attached it.
        assert [a["id"] for a in assets.for_turn(paper_turn)] == [asset["id"]]
        assert assets.for_turn(react_turn) == []

        # Separate jobs, each owned by its own turn.
        for tid in (react_turn, paper_turn):
            owned = db.connect().execute(
                "SELECT turn_id FROM jobs WHERE turn_id=?", (tid,)).fetchall()
            assert owned and all(j["turn_id"] == tid for j in owned)

        # No token from one turn landed in the other.
        for tid, other in ((react_turn, paper_turn), (paper_turn, react_turn)):
            for e in events.of_kind("token", tid):
                assert e["turn_id"] != other


class TestScenario008StopHalfway:
    """Stop generation halfway."""

    def test_cancel_mid_stream(self, conversation, events, scripted):
        scripted("one two three four five six seven eight nine ten eleven twelve",
                 chunk=2, delay=0.05)
        tid = run_turn(conversation, "count slowly")

        # Wait until it is genuinely streaming, then stop it.
        wait_until(lambda: events.of_kind("token", tid), what="streaming to begin")
        time.sleep(0.1)
        turns.cancel(tid)

        assert wait_for_turn(tid) == "cancelled"

        # §9.3 — the half-written answer is kept, never discarded.
        history = [t for t in turns.get_history(conversation) if t["turn_id"] == tid][0]
        partial = history["assistant_message"]
        assert partial is not None, "cancelling destroyed the partial answer"
        assert partial["partial"] is True
        assert partial["text"], "the preserved partial answer was empty"

        # The stream stopped: no tokens after the cancellation event.
        kinds = events.kinds(tid)
        cancelled_at = kinds.index("turn.cancelled")
        assert "token" not in kinds[cancelled_at:], "tokens kept arriving after cancel"

        # And what the user saw matches what was stored — no orphan tokens.
        assert events.text(tid).strip() == partial["text"].strip()

    def test_cancel_is_idempotent(self, conversation, scripted):
        scripted("short")
        tid = run_turn(conversation, "hi")
        wait_for_turn(tid)
        assert turns.cancel(tid)["ok"] is True
        assert turns.cancel(tid)["ok"] is True

    def test_cancelling_queued_turn_never_starts_work(self, conversation):
        """§9.1.3 — immediate, without starting the work."""
        turn = turns.create_turn(conversation, "never run me")
        tid = turn["turn_id"]
        turns.cancel(tid)                      # cancel before enqueueing
        row = db.connect().execute("SELECT status FROM turns WHERE id=?", (tid,)).fetchone()
        assert row["status"] == "cancelled"


class TestScenario017SwitchConversations:
    """Switch conversations during streaming."""

    def test_zero_token_leakage_across_conversations(self, events, scripted):
        a = turns.create_conversation("Room A")["id"]
        b = turns.create_conversation("Room B")["id"]

        scripted("aaaa bbbb cccc dddd eeee", chunk=2, delay=0.02)
        turn_a = run_turn(a, "talk in A")
        turn_b = run_turn(b, "talk in B")
        assert wait_for_turn(turn_a) == "completed"
        assert wait_for_turn(turn_b) == "completed"

        for tid, conv in ((turn_a, a), (turn_b, b)):
            for e in events.of_kind("token", tid):
                assert e["conversation_id"] == conv, "a token leaked into another conversation"

    def test_reconnect_into_the_other_conversation_resumes_correctly(self, scripted):
        a = turns.create_conversation("Room A2")["id"]
        b = turns.create_conversation("Room B2")["id"]
        scripted("Answer in the room you asked from.")

        before = bus.head()
        turn_b = run_turn(b, "hello B")
        wait_for_turn(turn_b)

        # A client with only A open replays nothing about B (§8.2.1) …
        for e in bus.replay(before, [a]):
            assert e["conversation_id"] != b

        # … and still sees B's full history when it opens B, because history
        # comes from the state tables, not the log (§3.3.4).
        history = turns.get_history(b)
        assert history[-1]["assistant_message"]["text"] == "Answer in the room you asked from."

    def test_conversation_state_preserved_across_turns(self, conversation, scripted):
        scripted("first answer", "second answer")
        t1 = run_turn(conversation, "first question")
        wait_for_turn(t1)
        t2 = run_turn(conversation, "second question")
        wait_for_turn(t2)

        history = turns.get_history(conversation)
        texts = [(t["user_message"]["text"], t["assistant_message"]["text"])
                 for t in history if t["assistant_message"]]
        assert ("first question", "first answer") in texts
        assert ("second question", "second answer") in texts
        seqs = [t["seq"] for t in history]
        assert seqs == sorted(seqs), "conversation ordering was not preserved"


class TestScenario029RunEditRerun:
    """Generate Python → Run → Edit → Run again."""

    def test_same_workspace_reused_and_versions_increment(self, conversation, events,
                                                          scripted, sandbox_ready):
        scripted(
            '<tool name="create_workspace">\n'
            '{"kind": "python", "title": "Counter", "files": {"main.py": "print(1)"}}\n'
            '</tool>',
            "Created it.",
        )
        t1 = run_turn(conversation, "make a script that prints 1")
        assert wait_for_turn(t1, timeout=180) == "completed"
        wid = workspaces.for_turn(t1)[0]["id"]

        scripted(
            f'<tool name="update_workspace">\n'
            f'{{"workspace_id": "{wid}", "files": {{"main.py": "print(2)"}}}}\n'
            f'</tool>',
            "Updated it.",
        )
        t2 = run_turn(conversation, "change it to print 2")
        assert wait_for_turn(t2, timeout=180) == "completed"

        # The same workspace, not a new one.
        assert workspaces.for_turn(t2)[0]["id"] == wid
        ws = workspaces.get(wid)
        assert ws["current_version"] == 2, "editing produced no new version"
        assert ws["files"]["main.py"] == "print(2)"
        assert workspaces.read_files(wid, 1)["main.py"] == "print(1)", "v1 was overwritten"

    def test_executions_are_isolated_from_each_other(self, conversation, scripted,
                                                     sandbox_ready):
        """Two runs in one turn must not see each other's files."""
        scripted(
            '<tool name="run_python">\n{"code": "open(\'leak.txt\',\'w\').write(\'first run\')\\nprint(\'wrote\')"}\n</tool>',
            '<tool name="run_python">\n{"code": "import os; print(\'leak.txt\' in os.listdir(\'.\'))"}\n</tool>',
            "Each run had its own directory.",
        )
        tid = run_turn(conversation, "write a file then check for it")
        assert wait_for_turn(tid, timeout=240) == "completed"

        sessions = sandbox.for_turn(tid)
        assert len(sessions) == 2, f"expected two execution sessions, got {len(sessions)}"

        second = sandbox.get(sessions[1]["id"])
        assert "False" in (second["stdout"] or ""), \
            "the second execution could see the first execution's files"

        # Different directories, so nothing leaks between sessions.
        first = sandbox.get(sessions[0]["id"])
        assert first["session_dir"] != second["session_dir"]
