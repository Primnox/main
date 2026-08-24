"""What an operation IS, separately from how any one tool performs it.

Everything in this package currently knows about operations by having been
written to handle them. `_click_element` knows a click cannot be undone
because `_reversal_for` says so; `_replay_step` knows the same thing again,
in its own words; the permission gate knows a third version, expressed as a
danger level on a tool spec. Three descriptions of one fact, none of which can
be consulted by anything that does not already contain a copy.

That is fine while there is one execution path. It stops being fine the moment
there are several — a batch that must know which of its steps are safe to
speculate on, a recovery engine deciding whether a retry is safe, a router
choosing between a pattern and a coordinate — because each of those needs to
ask questions ABOUT an operation before performing it, and there is currently
nothing to ask.

So this is the noun. A verb declares what it costs, what it needs, what it
leaves behind, and which routes can carry it, in one place that the executor,
the recorder, the policy gate and the replayer all read from.

Two fields do the real work, and keeping them separate is deliberate:

  `side_effect` is how much it matters if this happens and should not have.
  `reversible` is whether Primnox captured enough to put it back.

They are not the same question and collapsing them produces the wrong answer
in both directions. Scrolling changes the viewport and nothing else, so it is
harmless — and Primnox records no reversal for it, so it is not reversible.
A click is the mirror image: it looks like the cheapest thing in the list and
it is the most dangerous entry here, because "press this button" and "send
this email" are the same operation seen from different sides, and only the
application knows which one just happened.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import actions

# ── Side-effect classes, least to most consequential ────────────────────────

READ = "read"                    # observes; changes nothing
REVERSIBLE = "reversible"        # changes state, and the prior state was kept
DESTRUCTIVE = "destructive"      # changes state on this machine, unrecoverably
EXTERNAL = "external"            # leaves the machine: send, submit, publish
IRREVERSIBLE = "irreversible"    # nobody can undo it, including the user

# Ordered, because the useful question is almost always a comparison: "is this
# batch entirely at or below REVERSIBLE" decides whether it can run unattended.
SEVERITY = {READ: 0, REVERSIBLE: 1, DESTRUCTIVE: 2, EXTERNAL: 3, IRREVERSIBLE: 4}


@dataclass(frozen=True)
class Verb:
    """One operation, described rather than performed."""
    name: str
    side_effect: str
    # Whether running it twice is the same as running it once. This is about
    # the OPERATION, not the target: setting a field to "hello" twice leaves
    # the same text, so a retry after an ambiguous failure is safe. Pressing a
    # button twice is two presses, and a retry may buy something twice.
    idempotent: bool
    # Whether Primnox itself records a reversal. Not "could this in principle
    # be undone" — the application's own Ctrl+Z is a different mechanism with
    # a different owner, and offering it as this one is how a model comes to
    # take risks on a promise nothing here can keep.
    reversible: bool
    # Delivery routes, best first. The first entry is what the executor should
    # try; the rest are the ladder it descends when that is unavailable.
    routes: tuple[str, ...]
    # What must be true before it can run, and what is true afterwards. Prose
    # for now, by design: these are read by a person auditing the table far
    # more often than by code, and a predicate language invented before there
    # is an engine to evaluate it would be a guess at its own requirements.
    requires: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    # How an effect is confirmed, or "" where nothing can confirm it. The
    # empty string is a real answer and the most important one in the table:
    # it is the set of operations that can only ever return NOT VERIFIED.
    verifier: str = ""
    note: str = ""

    @property
    def severity(self) -> int:
        return SEVERITY[self.side_effect]

    def safe_to_repeat(self) -> bool:
        """Whether a failed attempt may simply be tried again.

        Idempotence alone is not enough. An operation that leaves the machine
        is not repeatable however idempotent its local effect looks, because
        the thing that may have already happened is on the other side of a
        network and out of reach of any reasoning done here.
        """
        return self.idempotent and self.severity < SEVERITY[EXTERNAL]


VERBS: dict[str, Verb] = {
    "read": Verb(
        "read", READ, idempotent=True, reversible=False,
        routes=(actions.ROUTE_PATTERN,),
        produces=("a stamped snapshot; the session generation advances",),
        verifier="element count",
        note="Advances the generation, which is why it is not free: refs "
             "handed out before it are stale afterwards."),
    "capture": Verb(
        "capture", READ, idempotent=True, reversible=False,
        routes=(actions.ROUTE_MESSAGE,),
        requires=("the window is not minimized and not DRM-protected",),
        verifier="image dimensions"),
    "type": Verb(
        "type", REVERSIBLE, idempotent=True, reversible=True,
        routes=(actions.ROUTE_PATTERN, actions.ROUTE_MESSAGE),
        requires=("the element exposes set_value and is enabled",),
        produces=("the element's value is exactly the text given",),
        verifier="value readback",
        note="Idempotent because SetValue replaces rather than appends "
             "— which stops being true when append is set, and the caller "
             "narrowing this is the caller's job."),
    "click": Verb(
        "click", IRREVERSIBLE, idempotent=False, reversible=False,
        routes=(actions.ROUTE_PATTERN, actions.ROUTE_MESSAGE),
        requires=("the element is enabled",),
        produces=("whatever the application does; unknowable from here",),
        verifier="",
        note="The most dangerous entry in this table and the one that reads "
             "as the cheapest. Invoking a control runs the application's "
             "code, and nothing on this side can tell 'expand a panel' from "
             "'send the message'. Narrowed to REVERSIBLE only where the "
             "element is a toggle and its prior state was captured."),
    "scroll": Verb(
        "scroll", READ, idempotent=False, reversible=False,
        routes=(actions.ROUTE_MESSAGE,),
        produces=("the viewport moves; no application state changes",),
        verifier="",
        note="READ because nothing durable changes, and NOT idempotent "
             "because scrolling twice goes twice as far. Those two are "
             "genuinely independent here."),
    "keys": Verb(
        "keys", IRREVERSIBLE, idempotent=False, reversible=False,
        routes=(actions.ROUTE_ATTACHED, actions.ROUTE_FOREGROUND),
        requires=("the window accepts input",),
        produces=("whatever the application binds those keys to",),
        verifier="",
        note="Ctrl+Enter sends the mail. A keystroke is an unlabelled click "
             "with no element to inspect first, so it cannot be classified "
             "lower than the worst thing it might be bound to."),
    "wait": Verb(
        "wait", READ, idempotent=True, reversible=False,
        routes=(actions.ROUTE_PATTERN,),
        requires=("the window is still open and its application responding",),
        produces=("nothing; the world changes, this only notices",),
        verifier="the predicate itself",
        note="The only operation here that is defined by NOT acting. It is "
             "READ because it changes nothing, and idempotent because waiting "
             "twice for something already true costs a poll."),
    "undo": Verb(
        "undo", REVERSIBLE, idempotent=False, reversible=False,
        routes=(actions.ROUTE_PATTERN,),
        requires=("a reversal was recorded for the last change",),
        produces=("the prior state is restored",),
        verifier="value readback"),
}


class UnknownVerb(KeyError):
    """An operation nobody declared. Refused rather than defaulted."""


def spec(verb: str) -> Verb:
    """The declaration for a verb, or a refusal.

    Deliberately not `VERBS.get(verb, SOMETHING_SAFE)`. A default would let a
    new operation reach the executor without anyone deciding what it costs,
    and the failure that produces is silent: the operation runs, the gate
    reads whatever the default said, and the first person to find out what it
    actually does is the user.
    """
    try:
        return VERBS[verb]
    except KeyError:
        raise UnknownVerb(
            f"{verb!r} is not a declared operation. Every operation must "
            f"declare its side effect before it can be performed. Declared: "
            f"{', '.join(sorted(VERBS))}.")


@dataclass(frozen=True)
class Operation:
    """A verb applied to a target — the canonical form every layer speaks.

    The target is a dict rather than a type because there are three genuinely
    different ways to name a thing and they are not interchangeable:

        {"ref": "e12@481"}     an execution-time handle, from a read
        {"selector": {...}}    role/name/ordinal, survives a re-read
        {"point": [x, y]}      client coordinates, for windows with no tree

    A recorded workflow stores the selector form, because it is the only one
    that still means anything tomorrow. A live turn uses the ref form, because
    it is the only one the model has. Keeping both in one shape is what lets
    the same executor run a live action and a replayed one.
    """
    verb: str
    target: "dict | None" = None
    arguments: dict = field(default_factory=dict)

    @property
    def spec(self) -> Verb:
        return spec(self.verb)

    def side_effect(self, *, reversal_captured: bool = False) -> str:
        """This operation's class, narrowed by what the caller established.

        A click on a toggle whose prior state was read first really is
        reversible, and refusing to say so would push every toggle through the
        confirmation path that exists for irreversible things — which trains
        the user to click through it, which is worse than not having it.
        """
        if reversal_captured and self.spec.reversible is False:
            return REVERSIBLE
        return self.spec.side_effect

    def to_json(self) -> dict:
        payload = {"verb": self.verb, "arguments": dict(self.arguments)}
        if self.target is not None:
            payload["target"] = dict(self.target)
        return payload

    @staticmethod
    def from_json(payload: dict) -> "Operation":
        verb = (payload or {}).get("verb") or ""
        spec(verb)              # refuse an undeclared verb at the boundary
        return Operation(verb=verb, target=payload.get("target"),
                         arguments=dict(payload.get("arguments") or {}))


def batch_severity(batch: "list[Operation]") -> str:
    """The class of a whole batch: the worst thing in it.

    This is the question speculative multi-action has to answer before it runs
    anything, and averaging would be exactly wrong — a batch of nine reads and
    one send is a send.
    """
    if not batch:
        return READ
    return max((op.spec.side_effect for op in batch), key=lambda s: SEVERITY[s])
