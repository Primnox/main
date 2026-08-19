"""Tests for permission_manager.py — the confirm-before-destructive-action
gate for LLM-initiated tool calls (delete_memory/delete_note in tools.py)."""
import threading
import time

import permission_manager


def _reset():
    with permission_manager._lock:
        permission_manager._pending.clear()
        permission_manager._granted_scopes.clear()
    permission_manager._broadcast_cb = None


def _answering(answer: bool, log: list):
    """Broadcast callback that answers every prompt with `answer` and records
    each one, so a test can count how many times the user was asked."""
    def fake_broadcast(event_type, data):
        log.append(data)
        threading.Thread(
            target=lambda: permission_manager.resolve_permission(data["token"], answer)
        ).start()
    return fake_broadcast


class TestRunScopedApproval:
    """One Allow covers a whole multi-step run. Before this, a skill that ran
    5 sandboxed commands showed 5 separate Allow/Deny dialogs — including for
    fragments like a lone import line."""

    def setup_method(self):
        _reset()

    def test_second_request_in_the_same_scope_does_not_prompt(self):
        prompts = []
        permission_manager.set_broadcast_callback(_answering(True, prompts))
        scope = permission_manager.open_scope()

        assert permission_manager.request_permission("run_python", "step 1", scope=scope, timeout=5) is True
        assert permission_manager.request_permission("run_python", "step 2", scope=scope, timeout=5) is True
        assert permission_manager.request_permission("run_python", "step 3", scope=scope, timeout=5) is True

        assert len(prompts) == 1, "the user should only be asked once per run"

    def test_the_one_prompt_is_flagged_as_covering_the_run(self):
        prompts = []
        permission_manager.set_broadcast_callback(_answering(True, prompts))
        permission_manager.request_permission(
            "run_python", "step 1", scope=permission_manager.open_scope(), timeout=5)
        assert prompts[0]["covers_run"] is True

    def test_unscoped_requests_still_prompt_every_time(self):
        # tools.py's delete_memory/delete_note pass no scope and must keep
        # asking for each individual destructive action.
        prompts = []
        permission_manager.set_broadcast_callback(_answering(True, prompts))

        permission_manager.request_permission("delete_note", "Delete A?", timeout=5)
        permission_manager.request_permission("delete_note", "Delete B?", timeout=5)

        assert len(prompts) == 2
        assert prompts[0]["covers_run"] is False

    def test_deny_is_never_remembered(self):
        # A Deny aborts the run, so there is nothing to inherit — and
        # remembering it would silently suppress a later, legitimate prompt.
        prompts = []
        permission_manager.set_broadcast_callback(_answering(False, prompts))
        scope = permission_manager.open_scope()

        assert permission_manager.request_permission("run_python", "step 1", scope=scope, timeout=5) is False
        assert permission_manager.request_permission("run_python", "step 2", scope=scope, timeout=5) is False

        assert len(prompts) == 2

    def test_separate_runs_do_not_share_an_approval(self):
        prompts = []
        permission_manager.set_broadcast_callback(_answering(True, prompts))

        permission_manager.request_permission("run_python", "run A", scope=permission_manager.open_scope(), timeout=5)
        permission_manager.request_permission("run_python", "run B", scope=permission_manager.open_scope(), timeout=5)

        assert len(prompts) == 2

    def test_released_scope_prompts_again(self):
        prompts = []
        permission_manager.set_broadcast_callback(_answering(True, prompts))
        scope = permission_manager.open_scope()

        permission_manager.request_permission("run_python", "step 1", scope=scope, timeout=5)
        permission_manager.release_scope(scope)
        permission_manager.request_permission("run_python", "later", scope=scope, timeout=5)

        assert len(prompts) == 2

    def test_grant_expires_even_if_never_released(self):
        prompts = []
        permission_manager.set_broadcast_callback(_answering(True, prompts))
        scope = permission_manager.open_scope()
        permission_manager.request_permission("run_python", "step 1", scope=scope, timeout=5)

        # Backdate the grant past the TTL, as if the run crashed before its
        # finally block could release it.
        with permission_manager._lock:
            permission_manager._granted_scopes[scope] -= permission_manager._SCOPE_TTL_SECONDS + 1

        permission_manager.request_permission("run_python", "much later", scope=scope, timeout=5)
        assert len(prompts) == 2

    def test_release_of_unknown_or_blank_scope_is_a_no_op(self):
        permission_manager.release_scope("")
        permission_manager.release_scope("never-granted")


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
