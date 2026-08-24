"""Control grants — the unit of authority for touching the real desktop.

A `sandbox.permissions.Manifest` answers "what may this code reach on disk and
on the network". That question has no meaning here. The question this module
answers is "which window, doing what, for how long", and it is deliberately a
different shape rather than an extension of the existing one, because the two
have no overlapping vocabulary and merging them would produce a permission
object where most fields are inapplicable in any given use.

Three properties, each of which exists because its absence is a known failure:

  Scoped to one window. Not to an application, and not to a process — a
  browser is one process holding a documents tab and a bank tab, and
  "control Chrome" is not a question anybody can answer responsibly.

  Expiring. An agent that was granted a window twenty minutes ago is acting
  on a desktop the user has since rearranged. Authority that outlives the
  user's attention is authority nobody is supervising.

  Explicit about writing. Reading a window — its tree, its picture — is a
  disclosure risk. Clicking in it is an integrity risk, and irreversible in
  the way that matters: there is no undo for a sent message. A grant that
  covers reading does not imply the other.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import targets

# Reading is a strictly weaker authority than acting, and separating them lets
# a model look before it is trusted to touch anything.
READ, ACT = "read", "act"

# How long a grant stays good. Short by intent: the cost of re-asking is one
# prompt, and the cost of not re-asking is an agent acting on a window whose
# contents changed while nobody was watching.
DEFAULT_TTL_S = 300

# How many actions one approval covers. A grant was time-boxed and nothing
# else: `actions_used` was counted and never read, so an approval to control a
# window for five minutes was an approval for however many clicks a model
# could emit in five minutes. At the rate these tools run that is thousands,
# and the shape of the failure is not one catastrophic action — it is a loop
# that fills a form, clears it, and fills it again while a user watches a
# timeline scroll past faster than they can read it.
#
# Sixty is chosen to be uncomfortable for a runaway and invisible to real
# work: filling a long form with twelve fields, tabbing between them and
# saving is around thirty. Hitting this is a signal, not a limit to tune —
# a session that needs more than sixty actions is a session where the user
# should get to see what happened and say yes again.
MAX_ACTIONS = 60


@dataclass
class Grant:
    """Authority over exactly one window, for a bounded time."""
    handle: str
    label: str
    scope: str                       # READ or ACT
    granted_at: float = field(default_factory=time.time)
    ttl_s: int = DEFAULT_TTL_S
    actions_used: int = 0

    def expired(self) -> bool:
        return (time.time() - self.granted_at) > self.ttl_s

    def remaining_s(self) -> int:
        return max(0, int(self.ttl_s - (time.time() - self.granted_at)))

    def allows(self, scope: str) -> bool:
        if self.expired():
            return False
        return True if scope == READ else self.scope == ACT

    def describe(self) -> str:
        """What the user reads in the approval prompt.

        Written as a plain sentence about consequences rather than a list of
        capabilities. "Send input to window handle 0x40E2A" is technically
        complete and tells a person nothing about what they are agreeing to.
        """
        if self.scope == READ:
            return (
                f"Read the contents of {self.label}.\n\n"
                "Primnox will capture a picture of this window and read its "
                "on-screen text and controls. Anything visible in it — "
                "including messages, documents, and account details — becomes "
                "part of this conversation. Nothing will be clicked or typed.")
        return (
            f"Control {self.label}.\n\n"
            "Primnox will click buttons, select items, and type text in this "
            "window, in the background — your mouse pointer will not move and "
            "your focus will not change. Actions inside another program cannot "
            "be undone by Primnox: a message it sends is sent, and a file it "
            "saves is saved.\n\n"
            f"This applies to this one window and expires in "
            f"{self.ttl_s // 60} minutes.")

    def to_json(self) -> dict:
        return {
            "handle": self.handle, "label": self.label, "scope": self.scope,
            "granted_at": self.granted_at, "ttl_s": self.ttl_s,
            "remaining_s": self.remaining_s(), "expired": self.expired(),
            "actions_used": self.actions_used,
        }


class Denied(PermissionError):
    """No grant covers this. The message is written for the model."""


def require(grant: "Grant | None", scope: str, target: targets.Target) -> Grant:
    """The single gate every action passes through."""
    if grant is None:
        raise Denied(
            f"There is no active control session for {target.label()}. Open "
            "one with control_window first — the user has to approve control "
            "of a window before it can be read or operated.")
    if grant.handle != target.handle:
        raise Denied(
            f"The active session is for {grant.label}, not {target.label()}. "
            "A session covers one window only. Open a separate session for "
            "this window if it is genuinely needed.")
    if grant.expired():
        raise Denied(
            f"The control session for {grant.label} expired. Sessions are "
            "short on purpose, because the window may have changed since the "
            "user approved it. Open a new one if the work is not finished.")
    if not grant.allows(scope):
        raise Denied(
            f"This session may only read {grant.label}, not act in it. The "
            "user approved looking at this window, not operating it. Ask for "
            "a control session if acting is genuinely required, and say why.")
    # Checked only for acting. Reading is free by design — the whole point of
    # the cheap-read work is that looking again should never be the expensive
    # option, and a cap that made a model ration its reads would push it back
    # towards acting on a stale picture.
    if scope == ACT and grant.actions_used >= MAX_ACTIONS:
        raise Denied(
            f"This session has done {grant.actions_used} things to "
            f"{grant.label}, which is the most one approval covers. That is "
            "usually a sign of a loop rather than a long task. Tell the user "
            "what has been done so far and what is left, and ask them to "
            "approve a new session if the work is genuinely unfinished.")
    return grant
