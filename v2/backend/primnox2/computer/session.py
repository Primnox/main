"""Control sessions — the live record of what the agent did to the desktop.

A session is a grant plus the log of everything done under it. The log is not
a debugging aid; it is the reason the feature is defensible. Actions taken in
somebody else's application cannot be rolled back in general — Primnox can
undo an edit to its own workspace, and cannot unsend a message — so the
compensating control is that every action is visible as it happens, in order,
with its result, and the session can be cut off mid-run.

Which is why an action is announced BEFORE it is attempted and its outcome
after. Emitting once on completion would mean the action that hangs, or the
one that crashes the target application, is the single action that never
appears in the timeline — the exact case where the user most needs to know
what was just done.

Three things live here that look like they belong elsewhere, and do not:

  The element ref table, because a ref is only meaningful against the tree it
  came from. Acting on `e12` from a read taken before a dialog opened would
  operate whatever now occupies that position, so a read replaces the table
  wholesale rather than merging into it.

  The undo journal, because reversibility is a property of a session's
  history rather than of an action type. `set_value` is undoable only if
  something captured what the value was first, and the only place that can
  happen is at the moment of the call.

  The recording, because a replayable step needs a selector that outlives the
  read it came from (`tree.selector_for`), and the session is what holds both
  the read and the action.

And one thing that looks like decoration and is not: the on-screen pointer
(`pointer.py`) is driven from `act`, because the timeline and the pointer are
the same guarantee told twice. The log says WHAT happened and is the record;
the pointer says WHERE, while it is happening, and is the part a user actually
notices from across a desk. Driving it from the call sites instead would mean
every new tool has to remember to — and the one that forgets is invisible,
which is precisely the failure the log exists to prevent.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace

from ..ids import new_id
from ..kernel.events import bus
from . import actions, grants, operations, pointer, targets, tree, vision

# Sessions per conversation. Several are allowed — driving a browser and a
# spreadsheet in one task is a real thing to want — but not many. The user has
# to be able to follow a timeline that interleaves several applications, and
# past a handful nobody can.
MAX_SESSIONS = 4

# How many past reads keep their selectors, so a ref from an older read can be
# rebound rather than refused. Four is a judgement about what "the model is a
# little behind" looks like: a plan written against one read, executed across
# two or three more as dialogs open and close. Beyond that the model is not
# behind, it is talking about a different window, and rebinding a ref from
# fifteen reads ago would be honouring a claim nobody should still trust.
REBIND_HISTORY = 4

_sessions: dict[str, dict[str, "Session"]] = {}
_lock = threading.RLock()


class Ambiguous(LookupError):
    """Several windows are under control and the call did not say which."""


def _detached(snapshot: "tree.Snapshot | None") -> "tree.Snapshot | None":
    """The same read with its live COM controls dropped.

    A Snapshot holds one COM object per element so that patterns can be
    operated without re-finding anything. That is right for the CURRENT read
    and wrong for a kept one: an element in a previous read cannot be operated
    — the whole reason it is previous is that the window moved on — so holding
    its control keeps a handle open on something nobody will ever call.
    """
    if snapshot is None:
        return None
    return tree.Snapshot(
        handle=snapshot.handle, title=snapshot.title,
        truncated=snapshot.truncated, generation=snapshot.generation,
        elements=[replace(e, control=None) for e in snapshot.elements])


@dataclass
class Verification:
    """What a verifier established about an action's EFFECT.

    Three outcomes, and the middle one is the point:

      confirmed    the expected state was observed
      unconfirmed  nothing could be observed — no verifier, or the read failed
      contradicted the state WAS read, and it is not what the action claimed

    Collapsing `unconfirmed` into `confirmed` is the bug this exists to end:
    `type_into` reported "set Text editor to 'PRIMNOX WAS HERE'" while typing
    into a different window of the same name, because the operation returning
    without raising was taken as proof it worked. It is not. A tool that says
    "done" when it cannot tell is worse than one that says "I could not check".

    `confidence` describes the quality of the EVIDENCE, not a model's belief:
    an exact value readback is 0.99 because the control was asked and answered,
    and no amount of the model feeling sure moves it.
    """
    effect: str
    confidence: float
    evidence: list
    detail: str = ""

    @staticmethod
    def unavailable(why: str) -> "Verification":
        return Verification("unconfirmed", 0.0, [], why)

    def as_payload(self) -> dict:
        return {"effect": self.effect, "confidence": round(self.confidence, 3),
                "evidence": self.evidence, "detail": self.detail}


class Reversal:
    """One undoable step: what it was, and how to put it back.

    Only some actions can produce one. A click cannot: pressing Send has no
    inverse, and pretending otherwise is worse than admitting it, because a
    model told "undo is available" will take risks on that basis.
    """
    __slots__ = ("description", "restore")

    def __init__(self, description: str, restore) -> None:
        self.description = description
        self.restore = restore


class Session:
    """One approved window and everything done to it."""

    def __init__(self, grant: grants.Grant, target: targets.Target, *,
                 conversation_id: str, turn_id: "str | None") -> None:
        self.id = new_id("cua")
        self.grant = grant
        self.target = target
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.snapshot: "tree.Snapshot | None" = None
        # The read before this one, so a re-read can report the delta instead
        # of the whole tree. Held detached; see `_detached`.
        self.previous: "tree.Snapshot | None" = None
        # The same pair for the page inside a browser window, read over CDP.
        # Kept alongside the window rather than replacing it: the page has the
        # content, the window has the tabs and the address bar.
        self.page: "tree.Snapshot | None" = None
        self.previous_page: "tree.Snapshot | None" = None
        # Which read the current snapshot is. Counted per session and never
        # reset, so a ref from generation 3 is distinguishable from the ref
        # with the same number in generation 4 for the life of the window.
        self.generation = 0
        # Selectors for the last few reads, so a stale ref can be REBOUND
        # instead of merely refused: {generation: {ref: selector}}. Selectors
        # only, never snapshots — a snapshot holds live COM controls, and
        # keeping four of those alive per session is a handle leak with a
        # timer on it.
        self._selectors: dict[int, dict[str, dict]] = {}
        self.log: list[dict] = []
        self.reversals: list[Reversal] = []
        self.recording: "list[dict] | None" = None
        # How the most recent ref was resolved, for provenance. Set by
        # `element`, consumed by `act` — an action that operated a REBOUND
        # element is a materially different claim from one that operated
        # exactly what the model named, and the log has to be able to say so.
        self.last_resolution: "dict | None" = None
        self.closed = False
        self._lock = threading.RLock()

    # ── The timeline ────────────────────────────────────────────────────────

    def _emit(self, kind: str, payload: dict) -> None:
        try:
            bus.emit(kind, {"session_id": self.id, **payload},
                     conversation_id=self.conversation_id, turn_id=self.turn_id)
        except Exception:
            # A session must not die because its narration failed. The action
            # log below is the durable record; the event stream is the live
            # view of it.
            pass

    def record(self, kind: str, description: str, *, status: str,
               detail: str = "", provenance: "dict | None" = None) -> dict:
        entry = {
            "id": new_id("act"), "kind": kind, "description": description,
            "status": status, "detail": detail, "at": time.time(),
        }
        if provenance:
            entry["provenance"] = provenance
        with self._lock:
            self.log.append(entry)
        self._emit("computer.action", entry)
        return entry

    def provenance(self, route: "str | None") -> dict:
        """Where this action came from and how it was delivered.

        A log that says "clicked Save" answers what happened and nothing about
        whether to believe it. Three facts change how the same sentence should
        be read, and none of them are recoverable afterwards:

          the ROUTE — a pattern invocation that fails means the control
          changed; a coordinate click that fails usually means only that
          something moved. Same sentence, opposite diagnosis.

          the RESOLUTION — whether the element operated is the one the model
          named, or one the runtime rebound to after the ref went stale.
          Rebinding is correct and quiet, and it is still a substitution; a
          replay that goes wrong three steps later starts here.

          the GENERATION — which read the window was on. Two actions against
          "the same" ref in different generations are two different actions.
        """
        with self._lock:
            resolution, self.last_resolution = self.last_resolution, None
            generation = self.generation
        record = {
            "generation": generation,
            # The session, not the grant — a Grant is authority over a window
            # and several sessions can hold one over time, so the session id is
            # what makes an entry attributable to a single approved run.
            "session_id": self.id,
            "scope": self.grant.scope,
            "target": {"handle": self.target.handle, "pid": self.target.pid,
                       "title": self.target.title},
        }
        if route:
            record["route"] = route
            record["rung"] = actions.RUNGS.get(route, "?")
        if resolution:
            record["resolution"] = resolution
        return record

    def act(self, kind: str, description: str, operation, *,
            reversal: "Reversal | None" = None, step: "dict | None" = None,
            at: "tuple[int, int] | None" = None,
            route: "str | None" = None,
            verify=None):
        """Announce, run, then report — in that order, always.

        `operation` returns a human sentence describing what happened, which
        becomes the settled description. The provisional one is what the user
        sees while it runs, so it is phrased as an intention.

        `at` is where on screen this is happening, if anywhere: the pointer
        goes there first, so it is already sitting on the control at the
        moment the control is operated. Actions with no place — a keystroke
        goes to a window, not to a point — pass nothing and leave the pointer
        where it was, which is honest: moving it somewhere arbitrary would
        show the user a location that means nothing.
        """
        grants.require(self.grant, grants.ACT, self.target)
        # Captured BEFORE the operation runs, because `element()` set it and
        # the operation may resolve another ref before this one finishes.
        origin = self.provenance(route)
        # The side-effect class, narrowed by what this call actually
        # established. `operations` declares a click IRREVERSIBLE because the
        # application decides what a click means; a click on a toggle whose
        # prior state was captured really is reversible, and the caller
        # passing a reversal is the evidence for that. Recorded rather than
        # inferred later, because the reversal exists only at this moment.
        try:
            origin["side_effect"] = operations.Operation(kind).side_effect(
                reversal_captured=reversal is not None)
        except operations.UnknownVerb:
            pass
        if at is not None:
            self._point_at(at)
            origin["at"] = list(at)
        started = self.record(kind, description, status="running",
                              provenance=origin)
        try:
            result = operation()
        except Exception as exc:
            self._resolve(started, "failed", description, str(exc))
            raise
        self.grant.actions_used += 1
        # Only after the action succeeded. A reversal for something that never
        # happened would put the window back to a state it never left.
        if reversal is not None:
            with self._lock:
                self.reversals.append(reversal)
        if step is not None and self.recording is not None:
            with self._lock:
                self.recording.append(step)

        # Ask what actually happened, rather than inferring it from the fact
        # that nothing threw. A verifier that itself fails leaves the action
        # UNCONFIRMED, never confirmed and never failed: losing the check is
        # not evidence either way, and pretending otherwise in either direction
        # is how a caller ends up trusting a claim nobody tested.
        outcome = Verification.unavailable("no verifier for this action")
        if verify is not None:
            try:
                outcome = verify() or outcome
            except Exception as exc:                    # pragma: no cover
                outcome = Verification.unavailable(
                    f"the check itself failed ({exc})")

        settled = result or description
        if outcome.effect == "contradicted":
            # It ran and did not take. Reporting "done" here is precisely the
            # failure this whole path exists to prevent.
            self._resolve(started, "failed", settled, outcome.detail,
                          verification=outcome)
            raise actions.ActionFailed(
                f"{settled} — but the change did not take: {outcome.detail}")

        self._resolve(started, "done", settled, verification=outcome)

        # The model reads the returned sentence, not the event payload, so the
        # caveat has to travel in the sentence. A confirmed write and one that
        # could not be checked must not read identically — that identity IS
        # the false-success bug, restated at the point the model consumes it.
        if outcome.effect == "confirmed":
            return settled
        return f"{settled} — NOT VERIFIED ({outcome.detail})"

    def _point_at(self, at: "tuple[int, int]") -> None:
        """Put the on-screen pointer on the thing about to be acted on.

        Never raises, and never delays the action by more than the time it
        takes to hand off a coordinate: the glide runs on the overlay's own
        thread. A machine that will not give us the overlay — a session with
        no desktop, a locked workstation — loses the picture and keeps the
        feature, which is the right way round. Losing the click because the
        decoration failed would not be.
        """
        try:
            overlay = pointer.acquire()
            if overlay is not None:
                overlay.move_to(at[0], at[1])
        except Exception:                                # pragma: no cover
            pass

    def _resolve(self, entry: dict, status: str, description: str,
                 detail: str = "", verification: "Verification | None" = None) -> None:
        with self._lock:
            entry.update(status=status, description=description, detail=detail,
                         resolved_at=time.time())
            if verification is not None:
                entry.update(verification.as_payload())
        self._emit("computer.action", entry)

    # ── Reading ─────────────────────────────────────────────────────────────

    def _stamp(self, snapshot: tree.Snapshot) -> tree.Snapshot:
        """Give a read its generation and file its selectors.

        Shared by both backends deliberately. A window read and a page read
        advance the SAME counter, because "how far behind is this ref" is one
        question about one session — two counters would make `e4@7` and `p2@7`
        two different sevens, and a model holding both would have no way to
        know which of its refs had gone stale.
        """
        with self._lock:
            self.generation += 1
            snapshot.generation = self.generation
            self._selectors.setdefault(self.generation, {}).update(
                {e.ref: tree.selector_for(snapshot, e)
                 for e in snapshot.elements})
            for old_generation in sorted(self._selectors)[:-REBIND_HISTORY]:
                self._selectors.pop(old_generation, None)
        return snapshot

    def read_page(self) -> tree.Snapshot:
        """The web page inside a browser window, read over its own protocol.

        A separate read from `read_tree` rather than a replacement for it,
        because the two see different things and both are real: the page has
        the content, the window has the address bar, the tabs and the back
        button. A model asked to open a new tab needs the second one.

        Refs are `p1`, `p2` and so on — the prefix is what makes the two
        readable together. `e3@7` and `p3@7` are unambiguous, so the model can
        hold refs from both and act on either without either the model or the
        runtime having to remember which read produced which.
        """
        grants.require(self.grant, grants.READ, self.target)
        self.target = targets.resolve(self.grant.handle)
        from . import chromium

        snapshot = chromium.read(self.target)
        for index, element in enumerate(snapshot.elements, 1):
            element.ref = f"p{index}"
        with self._lock:
            self.previous_page = _detached(self.page)
            self.page = self._stamp(snapshot)
        self.record("read", f"read {len(snapshot.elements)} page elements from "
                            f"{self.target.title}", status="done")
        return snapshot

    def read_tree(self) -> tree.Snapshot:
        grants.require(self.grant, grants.READ, self.target)
        self.target = targets.resolve(self.grant.handle)   # confirm still ours
        snapshot = tree.read(self.target)
        with self._lock:
            # Kept for the diff, stripped of live controls. A Snapshot holds a
            # COM object per element; hanging on to a whole previous one per
            # session is a handle leak, and the diff needs none of it — only
            # what each element WAS.
            self.previous = _detached(self.snapshot)
            self.snapshot = self._stamp(snapshot)
        self.record("read", f"read {len(snapshot.elements)} elements from "
                            f"{self.target.title}", status="done")
        return snapshot

    def capture(self):
        grants.require(self.grant, grants.READ, self.target)
        self.target = targets.resolve(self.grant.handle)
        image = vision.capture(self.target)
        self.record("capture", f"captured {self.target.title} "
                               f"({image.width}×{image.height})", status="done")
        return image

    def element(self, ref: str) -> tree.Element:
        """Resolve a ref against the CURRENT read, rebinding it if it is stale.

        The old contract was "refs are only valid against the read that
        produced them", which is true and was enforced by nothing: `e12` from
        two reads ago resolves perfectly well against this read, to whatever
        happens to be twelfth now. The window moving on did not make the ref
        fail, it made it point somewhere else — a silent misclick that then
        verifies clean, because the wrong control really did get set.

        Stamping the read closes that. A ref carries the generation it came
        from, so an older one is *detectable*, and the runtime does the obvious
        thing with it: look up what that ref meant at the time (role, name,
        ordinal) and find that same thing in the current read. Save is still
        Save after a dialog opens, even though it is no longer twelfth.

        Rebinding is deliberately quiet. The model does not get a turn spent
        on "your ref expired, here is the tree again" for something the
        runtime can settle from what it already knows; it gets the element.
        What it does NOT get is a guess — if the selector finds nothing, this
        raises, because "I could not find what you meant" and "here is
        something else" are not close together.
        """
        parsed, stamp = tree.parse_ref(ref)
        # The prefix says which backend the ref came from, so a page ref and a
        # window ref can be held at the same time without either the model or
        # this method having to remember which read produced which.
        wants_page = parsed.startswith("p")
        with self._lock:
            snapshot = self.page if wants_page else self.snapshot
            generation = self.generation
            history = dict(self._selectors)

        if snapshot is None:
            raise LookupError(
                "This page has not been read yet, so 'p' refs mean nothing. "
                "Call read_page first."
                if wants_page else
                "This window has not been read yet, so element refs mean "
                "nothing. Call read_window first, then act on a ref it "
                "returned.")

        if stamp is not None and stamp > generation:
            # There has never been a read that high. Either the model invented
            # the ref or it belongs to a different window; both are worth
            # refusing rather than rounding down to the current read.
            raise targets.Stale(
                f"{ref!r} names read {stamp} of this window, but there have "
                f"only been {generation}. Read the window and use a ref from "
                "that read.")

        if stamp is None or stamp == generation:
            element = snapshot.by_ref(parsed)
            if element is not None:
                self.last_resolution = {"ref": parsed, "resolved": "direct",
                                        "generation": generation}
                return element
            available = ", ".join(e.qualified(generation)
                                  for e in snapshot.actionable()[:12])
            raise LookupError(
                f"There is no element {parsed!r} in the last read of this "
                f"window. Actionable refs were: {available or 'none'}. Read "
                "the window again if it has changed.")

        # Stale, and recent enough to still know what it meant.
        selector = history.get(stamp, {}).get(parsed)
        if selector is None:
            raise targets.Stale(
                f"{ref!r} is from read {stamp}; this window is now at read "
                f"{generation} and read {stamp} is no longer remembered. Read "
                "the window again.")
        element = tree.resolve_selector(snapshot, selector)
        if element is None:
            name = selector.get("name") or "(unlabelled)"
            raise targets.Stale(
                f"{ref!r} was {selector.get('role')} {name!r} at read {stamp}, "
                f"and there is nothing matching it in the current read "
                f"(read {generation}). The window has changed. Read it again "
                "and act on what is there now.")
        self.last_resolution = {
            "ref": parsed, "resolved": "rebound", "generation": generation,
            "from_generation": stamp, "now": element.ref,
            "selector": {k: v for k, v in selector.items()
                         if k in ("role", "name", "ordinal")},
        }
        return element

    # ── Undo ────────────────────────────────────────────────────────────────

    def undo(self) -> str:
        """Reverse the most recent reversible action, or say why not.

        Deliberately narrow. Only actions that captured their prior state get
        a reversal, so this never guesses — the alternative, sending Ctrl+Z
        and hoping, belongs to the application's own undo stack and is offered
        as that rather than dressed up as this.
        """
        grants.require(self.grant, grants.ACT, self.target)
        with self._lock:
            reversal = self.reversals.pop() if self.reversals else None
        if reversal is None:
            raise LookupError(
                "Nothing done in this window can be undone by Primnox. Only "
                "changes that captured their previous state are reversible — "
                "setting a field's text, flipping a toggle. Clicking a button "
                "is not: the application has already done whatever it does, "
                "and there is no inverse to send it. If the application has "
                "its own undo, press_keys with ctrl+z asks IT to undo, which "
                "is a different thing and worth saying plainly to the user.")

        started = self.record("undo", f"undo {reversal.description}",
                              status="running")
        try:
            result = reversal.restore()
        except Exception as exc:
            self._resolve(started, "failed", f"undo {reversal.description}",
                          str(exc))
            raise
        self._resolve(started, "done", result or f"undid {reversal.description}")
        return result or f"undid {reversal.description}"

    # ── Recording ───────────────────────────────────────────────────────────

    def start_recording(self) -> None:
        with self._lock:
            self.recording = []

    def stop_recording(self) -> list[dict]:
        with self._lock:
            steps, self.recording = self.recording or [], None
        return steps

    def close(self, reason: str = "finished") -> dict:
        with self._lock:
            if self.closed:
                return self.summary()
            self.closed = True
        # Off screen the moment the authority ends. A pointer still sitting
        # over someone's spreadsheet after the grant expired would be claiming
        # a presence that no longer exists.
        try:
            pointer.release()
        except Exception:                                # pragma: no cover
            pass
        self._emit("computer.session.ended", {
            "handle": self.grant.handle, "label": self.grant.label,
            "reason": reason, "actions": self.grant.actions_used,
        })
        return self.summary()

    def summary(self) -> dict:
        with self._lock:
            entries = list(self.log)
        return {
            "session_id": self.id, "handle": self.grant.handle,
            "window": self.grant.label, "scope": self.grant.scope,
            "closed": self.closed, "actions": self.grant.actions_used,
            "remaining_s": self.grant.remaining_s(),
            "undoable": len(self.reversals),
            "log": entries,
        }


# ── Lifecycle ───────────────────────────────────────────────────────────────

def open_session(target: targets.Target, scope: str, *, conversation_id: str,
                 turn_id: "str | None", ttl_s: int = grants.DEFAULT_TTL_S) -> Session:
    """Start a session on a window, or replace that window's existing one."""
    grant = grants.Grant(handle=target.handle, label=target.label(),
                         scope=scope, ttl_s=ttl_s)
    session = Session(grant, target, conversation_id=conversation_id,
                      turn_id=turn_id)

    with _lock:
        held = _sessions.setdefault(conversation_id, {})
        # Expired sessions are swept here rather than by a timer: this is the
        # only moment the count matters, and a background reaper would be a
        # thread whose entire job is to notice something that can be checked
        # for free at the one point of contention.
        for handle, existing in list(held.items()):
            if existing.closed or existing.grant.expired():
                if not existing.closed:
                    existing.close("expired")
                held.pop(handle, None)

        previous = held.get(target.handle)
        if previous is None and len(held) >= MAX_SESSIONS:
            oldest = min(held.values(), key=lambda s: s.grant.granted_at)
            oldest.close("superseded")
            held.pop(oldest.grant.handle, None)
        held[target.handle] = session

    if previous is not None and not previous.closed:
        # Re-approving the SAME window replaces its grant rather than stacking
        # a second one, so the timeline keeps one story per window.
        previous.close("reopened")

    session._emit("computer.session.started", {
        "handle": target.handle, "label": grant.label, "scope": scope,
        "process": target.process, "ttl_s": ttl_s,
        "bounds": list(target.bounds),
    })
    return session


def live(conversation_id: str) -> list[Session]:
    """Every session still holding authority, oldest first."""
    with _lock:
        held = list(_sessions.get(conversation_id, {}).values())
    alive = []
    for session in held:
        if session.closed:
            continue
        if session.grant.expired():
            session.close("expired")
            continue
        alive.append(session)
    return sorted(alive, key=lambda s: s.grant.granted_at)


def current(conversation_id: str, handle: "str | None" = None) -> "Session | None":
    """The session a call meant.

    With one window under control the handle is optional, because requiring
    it would make the common case wordier for no benefit. With several it is
    required, and the failure is `Ambiguous` rather than a guess — picking
    the most recent would eventually click Send in the wrong application.
    """
    alive = live(conversation_id)
    if handle:
        return next((s for s in alive if s.grant.handle == handle), None)
    if len(alive) == 1:
        return alive[0]
    if len(alive) > 1:
        raise Ambiguous(
            "More than one window is under control right now: "
            + "; ".join(f"{s.grant.label} ({s.grant.handle})" for s in alive)
            + ". Pass the window handle to say which one you mean.")
    return None


def close_session(conversation_id: str, handle: "str | None" = None,
                  reason: str = "finished") -> "dict | None":
    session = current(conversation_id, handle)
    if session is None:
        return None
    summary = session.close(reason)
    with _lock:
        _sessions.get(conversation_id, {}).pop(session.grant.handle, None)
    return summary


def close_all(reason: str = "shutdown",
              conversation_id: "str | None" = None) -> int:
    """Drop grants. Called on shutdown, and available as a panic stop.

    Authority over the user's desktop must not survive the process that was
    exercising it — a grant is a live thing, not a stored preference.
    """
    with _lock:
        if conversation_id is None:
            groups = list(_sessions.values())
            _sessions.clear()
        else:
            groups = [_sessions.pop(conversation_id, {})]
    closed = 0
    for group in groups:
        for session in group.values():
            if not session.closed:
                session.close(reason)
                closed += 1
    return closed
