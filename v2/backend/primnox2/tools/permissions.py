"""Permission broker — CRS §5.1 `awaiting_input`, §3.6 permission events.

V1 asked for permission with a blocking modal owned by the UI. That coupling is
why permission could not be requested from a background job, could not be
answered from a second window, and could not survive a reconnect.

Here the question is an event and the answer is an HTTP call. The turn parks in
`awaiting_input` — which is exactly the state that exists for it — and the
worker thread waits on an Event rather than a UI callback.

A pending request is deliberately NOT durable across a restart. On boot every
non-terminal turn is failed (§10.3.2), so a question whose asker no longer
exists must not linger and be answerable into the void.
"""
from __future__ import annotations

import os
import threading
import time

from ..chat import turns
from ..kernel.events import bus

ALLOW_ONCE, ALLOW_TURN, DENY = "allow_once", "allow_turn", "deny"
ALLOW_AUTO = "allow_auto"

# Outcomes of a question that produced no usable answer. Three distinct values
# rather than one, because the model should say different things: nobody was
# there, the user declined to pick, or the turn was being cancelled anyway.
# Collapsing them would have the model report "you chose X" for all three.
ANSWER_TIMEOUT, ANSWER_UNCLEAR, ANSWER_CANCELLED = (
    "__timeout__", "__unclear__", "__cancelled__")

# How much is approved without asking.
#
#   all   nothing prompts. Every request is granted and recorded.
#   safe  the sandboxed, offline, workspace-only tier is granted; shell and
#         anything reaching beyond the workspace still prompts.
#   off   every request prompts.
#
# The default is `all` because this is a local-first single-user app whose
# owner asked not to be interrupted. It is a real reduction in defence: a
# prompt is the last gate before model-generated code runs, and removing it
# means the sandbox boundary (§sandbox/permissions.py) is the ONLY thing
# standing between a bad generation and the machine. That boundary is
# measured and real, which is what makes this a defensible default rather
# than a reckless one.
#
# Every auto-approval still emits `permission.request` and
# `permission.resolved` with `choice: allow_auto`, so the UI and the event log
# show exactly what was granted. Set PRIMNOX2_AUTO_APPROVE=off to restore
# prompting.
AUTO_APPROVE = os.getenv("PRIMNOX2_AUTO_APPROVE", "all").strip().lower()

# How long a question waits before it answers itself with a denial. A worker
# blocked forever on an unanswered prompt is a leaked thread and a turn that
# never terminates.
DEFAULT_TIMEOUT_S = 600


class _Pending:
    __slots__ = ("event", "choice", "turn_id", "created_at",
                 "request_id", "action", "detail", "options", "kind")

    def __init__(self, turn_id: str | None, *, request_id: str = "",
                 action: str = "", detail: str = "",
                 options: list[dict] | None = None,
                 kind: str = "permission") -> None:
        # "permission" is a safety decision with a fixed vocabulary;
        # "question" is the model admitting it does not know something, and its
        # options are whatever it needed to ask. They are parked and resolved
        # the same way and must not be rendered the same way.
        self.kind = kind
        self.event = threading.Event()
        self.choice: str | None = None
        self.turn_id = turn_id
        self.created_at = time.time()
        # Kept so the question can be handed to a client that arrives after it
        # was asked — see `pending_for_turn`.
        self.request_id = request_id
        self.action = action
        self.detail = detail
        self.options = options or []


class PermissionBroker:
    def __init__(self) -> None:
        self._pending: dict[str, _Pending] = {}
        self._granted_for_turn: dict[tuple[str, str], bool] = {}
        self._lock = threading.RLock()

    def request(
        self,
        *,
        request_id: str,
        action: str,
        detail: str,
        turn_id: str | None = None,
        conversation_id: str | None = None,
        reusable: bool = False,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        should_cancel=None,
    ) -> str:
        """Ask, park the turn, and block this worker until answered.

        Returns one of ALLOW_ONCE / ALLOW_TURN / DENY. Never raises: a denial
        is a normal outcome, not an error.
        """
        # An approval already given for this turn covers a reusable action.
        #
        # It is still announced. Returning silently here meant a turn that used
        # a tool three times produced ONE record of one grant, which made the
        # log a summary of what was decided rather than an account of what ran
        # — and that account is the entire reason auto-approval is defensible.
        granted = self._granted_for_turn.get((turn_id, action)) if turn_id else None
        if reusable and granted:
            self._announce(request_id, action, detail, granted,
                           turn_id=turn_id, conversation_id=conversation_id)
            return granted

        # Auto-approval. Announced on the event stream rather than granted
        # silently — the user should be able to see afterwards exactly what ran
        # without having been interrupted at the time.
        if AUTO_APPROVE == "all" or (AUTO_APPROVE == "safe" and reusable):
            self._announce(request_id, action, detail, ALLOW_AUTO,
                           turn_id=turn_id, conversation_id=conversation_id)
            if reusable and turn_id:
                self._granted_for_turn[(turn_id, action)] = ALLOW_AUTO
            return ALLOW_AUTO

        options = [
            {"id": ALLOW_ONCE, "label": "Allow once"},
            *([{"id": ALLOW_TURN, "label": "Allow for this turn"}] if reusable else []),
            {"id": DENY, "label": "Don't allow"},
        ]

        pending = _Pending(turn_id, request_id=request_id, action=action,
                           detail=detail, options=options)
        with self._lock:
            self._pending[request_id] = pending

        prior = None
        if turn_id:
            prior = _status_of(turn_id)
            try:
                turns.set_status(turn_id, "awaiting_input")
            except ValueError:
                # A turn that cannot legally park here (already terminal) must
                # not have its permission question silently granted.
                pass

        if conversation_id:
            bus.emit("permission.request", {
                "job_id": request_id, "action": action,
                "detail": detail, "options": options,
            }, conversation_id=conversation_id, turn_id=turn_id)

        deadline = time.time() + timeout_s
        choice = DENY
        while time.time() < deadline:
            if pending.event.wait(timeout=0.2):
                choice = pending.choice or DENY
                break
            # CRS §9.2 — cancelling a turn must not leave it parked on a
            # question nobody is going to answer.
            if should_cancel is not None and should_cancel():
                choice = DENY
                break
        else:
            choice = DENY

        with self._lock:
            self._pending.pop(request_id, None)

        if choice == ALLOW_TURN and turn_id:
            self._granted_for_turn[(turn_id, action)] = ALLOW_TURN

        if conversation_id:
            bus.emit("permission.resolved", {"job_id": request_id, "choice": choice},
                     conversation_id=conversation_id, turn_id=turn_id)

        # Restore the state the turn was in before it asked, so the lifecycle
        # continues where it left off rather than jumping.
        if turn_id and prior and prior not in turns.TERMINAL:
            try:
                turns.set_status(turn_id, prior)
            except ValueError:
                pass
        return choice

    def _announce(self, request_id: str, action: str, detail: str, choice: str,
                  *, turn_id: str | None, conversation_id: str | None) -> None:
        """Record a grant that was never put to the user.

        Both the request and its answer, so a grant nobody was asked about
        appears in the log in the same shape as one they answered.
        """
        if not conversation_id:
            return
        bus.emit("permission.request", {
            "job_id": request_id, "action": action, "detail": detail,
            "options": [], "auto": True,
        }, conversation_id=conversation_id, turn_id=turn_id)
        bus.emit("permission.resolved", {"job_id": request_id, "choice": choice},
                 conversation_id=conversation_id, turn_id=turn_id)

    def resolve(self, request_id: str, choice: str) -> bool:
        with self._lock:
            pending = self._pending.get(request_id)
        if pending is None:
            return False

        if pending.kind == "question":
            # A question's options are the model's own, so the permission
            # vocabulary does not apply. Anything unrecognised still falls back
            # to the escape hatch rather than being taken as an answer — a
            # question resolved with a value nobody offered would put words in
            # the user's mouth, which is the thing this feature exists to stop.
            valid = {o["id"] for o in pending.options}
            pending.choice = choice if choice in valid else ANSWER_UNCLEAR
        else:
            pending.choice = choice if choice in (ALLOW_ONCE, ALLOW_TURN, DENY) else DENY
        pending.event.set()
        return True

    def ask(self, *, request_id: str, question: str, options: list[dict],
            turn_id: str | None = None, conversation_id: str | None = None,
            timeout_s: int | None = None, should_cancel=None) -> str:
        """Put a question to the user and block until it is answered.

        Deliberately NOT routed through `request()`, for one reason:
        auto-approval. `PRIMNOX2_AUTO_APPROVE=all` is a defensible default for
        permissions — the user chose to stop being interrupted about tools they
        trust. Applying it here would answer a question the model asked because
        it did not know something, by silently choosing the first option. That
        is a fabricated answer attributed to the user, and it is worse than the
        guess the model would have made unaided, because it looks confirmed.

        A question is always put to the user, whatever the permission setting.
        """
        # Read at call time, not bound as a default argument. `timeout_s: int =
        # DEFAULT_TIMEOUT_S` binds the module value once at import, so changing
        # it afterwards — from a test, or from a setting — has no effect and the
        # call still waits the original ten minutes. Found the hard way: a test
        # that patched it hung for the full duration.
        timeout_s = DEFAULT_TIMEOUT_S if timeout_s is None else timeout_s

        pending = _Pending(turn_id, request_id=request_id, action="question",
                           detail=question, options=options, kind="question")
        with self._lock:
            self._pending[request_id] = pending

        if conversation_id:
            bus.emit("question.asked", {
                "job_id": request_id, "question": question, "options": options,
            }, conversation_id=conversation_id, turn_id=turn_id)

        prior = None
        if turn_id:
            prior = _status_of(turn_id)
            try:
                turns.set_status(turn_id, "awaiting_input")
            except ValueError:
                pass

        # Same poll-with-cancel loop as `request()`: a cancelled turn must not
        # sit parked on a question nobody will answer (CRS §9.2).
        deadline = time.time() + timeout_s
        choice = ANSWER_TIMEOUT
        while time.time() < deadline:
            if pending.event.wait(timeout=0.2):
                choice = pending.choice or ANSWER_UNCLEAR
                break
            if should_cancel is not None and should_cancel():
                choice = ANSWER_CANCELLED
                break

        with self._lock:
            self._pending.pop(request_id, None)

        if conversation_id:
            bus.emit("question.resolved", {"job_id": request_id, "choice": choice},
                     conversation_id=conversation_id, turn_id=turn_id)

        if turn_id and prior and prior not in turns.TERMINAL:
            try:
                turns.set_status(turn_id, prior)
            except ValueError:
                pass
        return choice

    def cancel_for_turn(self, turn_id: str) -> int:
        """Deny every question belonging to a turn that is being cancelled."""
        n = 0
        with self._lock:
            items = [(rid, p) for rid, p in self._pending.items() if p.turn_id == turn_id]
        for rid, pending in items:
            pending.choice = DENY
            pending.event.set()
            n += 1
        return n

    def pending_for_turn(self, turn_id: str) -> dict | None:
        """The unanswered question a parked turn is waiting on, if any.

        Opening a conversation is a state read, never a replay (§3.3.3), and
        this question exists only here — the `permission.request` event is the
        announcement, not the record. Without this, a client that reloads while
        a turn is parked rebuilds it as `awaiting_input` with nothing on screen
        to answer, and the turn sits there until the request times out.
        """
        with self._lock:
            for pending in self._pending.values():
                if pending.turn_id == turn_id:
                    return {
                        "id": pending.request_id,
                        "action": pending.action,
                        "detail": pending.detail,
                        "options": list(pending.options),
                    }
        return None

    def pending_ids(self) -> list[str]:
        with self._lock:
            return list(self._pending)

    def forget_turn(self, turn_id: str) -> None:
        for key in [k for k in self._granted_for_turn if k[0] == turn_id]:
            self._granted_for_turn.pop(key, None)


def _status_of(turn_id: str) -> str | None:
    # Via `turns` rather than a direct read: an incognito turn has no row, and
    # a direct read reports it as missing rather than as parked.
    return turns.status_of(turn_id)


broker = PermissionBroker()
