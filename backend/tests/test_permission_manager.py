"""Tests for permission_manager.py — the confirm-before-destructive-action
gate for LLM-initiated tool calls (delete_memory/delete_note in tools.py)."""
import threading
import time

import permission_manager


def _reset():
    with permission_manager._lock:
        permission_manager._pending.clear()
    permission_manager._broadcast_cb = None


class TestRequestPermission:
    def setup_method(self):
        _reset()

    def test_allow_response_returns_true(self):
        captured = {}

        def fake_broadcast(event_type, data):
            captured["event_type"] = event_type
            captured["data"] = data
            # Simulate the frontend answering immediately, from another thread,
            # the same way POST /api/permission_response would.
            threading.Thread(
                target=lambda: permission_manager.resolve_permission(data["token"], True)
            ).start()

        permission_manager.set_broadcast_callback(fake_broadcast)
        result = permission_manager.request_permission("delete_memory", "Delete X?", session_id="s1", timeout=5)

        assert result is True
        assert captured["event_type"] == "permission_request"
        assert captured["data"]["action"] == "delete_memory"
        assert captured["data"]["session_id"] == "s1"

    def test_deny_response_returns_false(self):
        def fake_broadcast(event_type, data):
            threading.Thread(
                target=lambda: permission_manager.resolve_permission(data["token"], False)
            ).start()

        permission_manager.set_broadcast_callback(fake_broadcast)
        result = permission_manager.request_permission("delete_memory", "Delete X?", session_id="s1", timeout=5)
        assert result is False

    def test_timeout_fails_closed(self):
        permission_manager.set_broadcast_callback(lambda *a: None)  # nobody ever answers
        start = time.time()
        result = permission_manager.request_permission("delete_memory", "Delete X?", session_id="s1", timeout=0.2)
        elapsed = time.time() - start

        assert result is False
        assert elapsed >= 0.2

    def test_pending_entry_is_removed_after_resolution(self):
        def fake_broadcast(event_type, data):
            permission_manager.resolve_permission(data["token"], True)

        permission_manager.set_broadcast_callback(fake_broadcast)
        permission_manager.request_permission("delete_memory", "Delete X?", session_id="s1", timeout=5)
        assert permission_manager._pending == {}

    def test_resolve_unknown_token_returns_false(self):
        assert permission_manager.resolve_permission("not-a-real-token", True) is False

    def test_resolving_twice_is_a_noop_the_second_time(self):
        token_holder = {}

        def fake_broadcast(event_type, data):
            token_holder["token"] = data["token"]
            threading.Thread(
                target=lambda: permission_manager.resolve_permission(data["token"], True)
            ).start()

        permission_manager.set_broadcast_callback(fake_broadcast)
        # request_permission only returns after it has popped the entry (it
        # waits on the Event, then pops under the lock) — so by the time this
        # call returns, the first resolution is fully done and the entry is
        # gone, making a same-token second resolve() a well-defined "too late".
        result = permission_manager.request_permission("delete_memory", "Delete X?", session_id="s1", timeout=5)
        assert result is True
        assert permission_manager.resolve_permission(token_holder["token"], True) is False

    def test_broadcast_failure_does_not_prevent_the_wait(self):
        def broken_broadcast(event_type, data):
            raise RuntimeError("frontend unreachable")

        permission_manager.set_broadcast_callback(broken_broadcast)
        result = permission_manager.request_permission("delete_memory", "Delete X?", session_id="s1", timeout=0.2)
        assert result is False  # times out, doesn't crash


class TestSweepExpired:
    def setup_method(self):
        _reset()

    def test_sweep_prunes_long_dead_entries(self):
        with permission_manager._lock:
            permission_manager._pending["stale-token"] = {
                "event": threading.Event(),
                "result": None,
                "session_id": "s1",
                "created": time.time() - 10_000,  # long past created + timeout + 300
                "timeout": 120,
            }
        permission_manager._sweep_expired()
        assert "stale-token" not in permission_manager._pending

    def test_sweep_keeps_fresh_entries(self):
        with permission_manager._lock:
            permission_manager._pending["fresh-token"] = {
                "event": threading.Event(),
                "result": None,
                "session_id": "s1",
                "created": time.time(),
                "timeout": 120,
            }
        permission_manager._sweep_expired()
        assert "fresh-token" in permission_manager._pending
