"""Tests for recurring-error memory: a fingerprint that keeps reappearing
after being quiet for a while should eventually get written to memory as a
noticed pattern, once, with no LLM call involved.
"""
import pytest

import memory
from feed_manager import FeedManager, _is_terminal_process


@pytest.fixture
def fm():
    f = FeedManager.__new__(FeedManager)  # skip __init__'s screen/thread wiring
    f.error_recurrence_count = {}
    f.error_recurrence_recorded = set()
    f.RECURRING_ERROR_THRESHOLD = 3
    f.window_start_time = 0.0
    f.FOCUS_SUPPRESSION_SECONDS = 1200
    f._suppressed_nudges = []
    f.MAX_SUPPRESSED_NUDGES = 20
    f.callback = None
    return f


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test_memory.db")
    memory.init_db()
    return memory


class TestMaybeRecordRecurringError:
    def test_below_threshold_writes_nothing(self, fm, db):
        fm._maybe_record_recurring_error("fp1", "ModuleNotFoundError: foo", {})
        fm._maybe_record_recurring_error("fp1", "ModuleNotFoundError: foo", {})
        assert db.list_memories() == []

    def test_reaching_threshold_writes_one_memory(self, fm, db):
        for _ in range(3):
            fm._maybe_record_recurring_error("fp1", "ModuleNotFoundError: foo", {})
        memories = db.list_memories()
        assert len(memories) == 1
        assert "seen 3+ times" in memories[0]["text"]
        assert memories[0]["provenance"] == "inferred_screen"

    def test_does_not_re_record_past_threshold(self, fm, db):
        for _ in range(6):
            fm._maybe_record_recurring_error("fp1", "ModuleNotFoundError: foo", {})
        assert len(db.list_memories()) == 1

    def test_tags_project_topic_when_available(self, fm, db):
        uia_data = {"project": {"project_name": "primnox"}}
        for _ in range(3):
            fm._maybe_record_recurring_error("fp1", "TypeError: bad arg", uia_data)
        [mem] = db.list_memories()
        assert mem["topic"] == "project:primnox"

    def test_no_topic_when_project_unknown(self, fm, db):
        for _ in range(3):
            fm._maybe_record_recurring_error("fp1", "TypeError: bad arg", {})
        [mem] = db.list_memories()
        assert mem["topic"] is None

    def test_different_fingerprints_tracked_independently(self, fm, db):
        for _ in range(3):
            fm._maybe_record_recurring_error("fp1", "error one", {})
        fm._maybe_record_recurring_error("fp2", "error two", {})
        fm._maybe_record_recurring_error("fp2", "error two", {})
        assert len(db.list_memories()) == 1  # only fp1 crossed the threshold


class TestFocusModeSuppression:
    def test_not_in_focus_mode_before_threshold(self, fm):
        assert fm._is_in_focus_mode(current_time=1000.0) is False  # 1000s < 1200s

    def test_in_focus_mode_past_threshold(self, fm):
        assert fm._is_in_focus_mode(current_time=1300.0) is True  # 1300s > 1200s

    def test_emit_nudge_fires_immediately_when_not_focused(self, fm):
        received = []
        fm.callback = lambda t, p: received.append((t, p))
        fm._emit_nudge("proactive_message", {"message": "hi"}, current_time=100.0)
        assert received == [("proactive_message", {"message": "hi"})]
        assert fm._suppressed_nudges == []

    def test_emit_nudge_queues_when_focused(self, fm):
        received = []
        fm.callback = lambda t, p: received.append((t, p))
        fm._emit_nudge("proactive_message", {"message": "hi"}, current_time=1300.0)
        assert received == []
        assert fm._suppressed_nudges == [("proactive_message", {"message": "hi"})]

    def test_flush_delivers_and_clears_queue(self, fm):
        received = []
        fm.callback = lambda t, p: received.append((t, p))
        fm._emit_nudge("proactive_message", {"message": "one"}, current_time=1300.0)
        fm._emit_nudge("proactive_message", {"message": "two"}, current_time=1400.0)
        fm._flush_suppressed_nudges()
        assert received == [
            ("proactive_message", {"message": "one"}),
            ("proactive_message", {"message": "two"}),
        ]
        assert fm._suppressed_nudges == []

    def test_flush_with_nothing_queued_does_not_call_back(self, fm):
        received = []
        fm.callback = lambda t, p: received.append((t, p))
        fm._flush_suppressed_nudges()
        assert received == []


class TestIsTerminalProcess:
    """Error detection is scoped to editors + terminals (see feed_manager.py's
    two-stage LLM detector and clipboard detector) — a browser tab or chat
    app with the word "error" in it shouldn't trigger the same debug-offer
    flow as a real stack trace. This is the terminal half of that scoping
    (parse_editor_title covers the editor half)."""

    @pytest.mark.parametrize("process", [
        "WindowsTerminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
        "conhost.exe", "wt.exe", "Hyper.exe",
    ])
    def test_recognizes_windows_terminals(self, process):
        assert _is_terminal_process(process) is True

    @pytest.mark.parametrize("process", [
        "chrome.exe", "msedge.exe", "slack.exe", "Discord.exe", "code.exe",
    ])
    def test_does_not_match_non_terminal_processes(self, process):
        assert _is_terminal_process(process) is False

    def test_is_case_insensitive(self):
        assert _is_terminal_process("CMD.EXE") is True
        assert _is_terminal_process("PowerShell.Exe") is True

    def test_handles_none_and_empty(self):
        assert _is_terminal_process(None) is False
        assert _is_terminal_process("") is False
