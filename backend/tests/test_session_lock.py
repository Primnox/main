"""Tests for core.py's per-session processing lock — added because
POST /message spawns an independent background thread per request with no
serialization. A slow skill invocation (e.g. PDF generation, ~10-15s) could
overlap with a quick follow-up message in the same session; the follow-up
would read chat history from before the first reply landed and answer as if
it hadn't happened, appearing interleaved/out of order in the transcript.

PrimnoxCore itself isn't instantiated here — its __init__ starts real
background threads (FeedManager, MeetingRecorder) that aren't needed to
test the locking primitive itself, which is a plain module-level function
operating on a module-level dict."""
import threading
import time

import core


class TestGetSessionLock:
    def setup_method(self):
        core._session_locks.clear()

    def test_same_session_id_returns_the_same_lock_object(self):
        lock1 = core._get_session_lock("session-a")
        lock2 = core._get_session_lock("session-a")
        assert lock1 is lock2

    def test_different_session_ids_return_different_lock_objects(self):
        lock_a = core._get_session_lock("session-a")
        lock_b = core._get_session_lock("session-b")
        assert lock_a is not lock_b

    def test_concurrent_access_to_the_same_session_lock_serializes(self):
        lock = core._get_session_lock("session-a")
        order = []

        def slow_holder():
            with lock:
                order.append("first-start")
                time.sleep(0.2)
                order.append("first-end")

        def waiter():
            time.sleep(0.05)  # ensure slow_holder acquires first
            with lock:
                order.append("second-start")
                order.append("second-end")

        t1 = threading.Thread(target=slow_holder)
        t2 = threading.Thread(target=waiter)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # The second acquirer must never interleave with the first — its
        # start/end must both come after the first's end.
        assert order == ["first-start", "first-end", "second-start", "second-end"]

    def test_different_sessions_do_not_block_each_other(self):
        lock_a = core._get_session_lock("session-a")
        lock_b = core._get_session_lock("session-b")
        order = []

        def hold_a():
            with lock_a:
                order.append("a-start")
                time.sleep(0.2)
                order.append("a-end")

        def hold_b():
            time.sleep(0.05)
            with lock_b:
                order.append("b-start")
                order.append("b-end")

        t1 = threading.Thread(target=hold_a)
        t2 = threading.Thread(target=hold_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # session-b's work must complete WHILE session-a's lock is still
        # held — i.e. it isn't blocked by an unrelated session.
        assert order.index("b-start") < order.index("a-end")


class TestProcessInputAcquiresTheSessionLock:
    def test_empty_input_returns_before_touching_the_lock(self, monkeypatch):
        # A lightweight stand-in exercising just the two methods under test,
        # avoiding PrimnoxCore.__init__'s real background threads.
        class _Bare:
            _process_input = core.PrimnoxCore._process_input

            def _process_input_locked(self, *a, **kw):
                raise AssertionError("should not be called for empty input")

        core._session_locks.clear()
        _Bare()._process_input("", "User")
        assert core._session_locks == {}

    def test_process_input_calls_the_locked_implementation_under_the_session_lock(self):
        calls = []

        class _Bare:
            _process_input = core.PrimnoxCore._process_input

            def _process_input_locked(self, raw_text, speaker, input_mode="text", session_id="current", user_text=None, images_b64=None):
                # The session's lock must already be held while this runs.
                lock = core._get_session_lock(session_id)
                assert lock.locked()
                calls.append((raw_text, session_id))

        core._session_locks.clear()
        _Bare()._process_input("hello", "User", session_id="s1")
        assert calls == [("hello", "s1")]
        # Lock is released once processing completes.
        assert not core._get_session_lock("s1").locked()
