"""Computer Use — the agent's hands on the real desktop.

Every other subsystem in this codebase exists to keep model-generated code
*in*. The sandbox is a wall: an AppContainer with no network capability, an
ACL'd execution directory, and a job object holding the line on CPU and
memory. Computer Use is the exact inverse. It reaches *out*, to the live
desktop the user is sitting in front of, to windows holding unsaved work and
signed-in sessions, and it does so with no wall available even in principle —
you cannot sandbox someone else's running Word.

So none of the sandbox's machinery is reused here, and that is deliberate.
A `sandbox.permissions.Manifest` speaks about filesystem scopes, network
modes and resource ceilings; not one of those words means anything when the
question is "may this agent click the Send button in your mail client".
The unit of authority here is a *window*, and it lives in `grants.py`.

The safety model is therefore entirely different, and rests on three claims
that are measured rather than assumed (see `actions.py` for the evidence):

  1. Nothing here moves the user's mouse pointer or steals their focus.
     Actions are delivered through UI Automation control patterns and posted
     window messages, both of which address a window directly. The user can
     keep typing in another app while the agent works.
  2. Nothing here acts on a window that was not individually approved.
     A grant names one window, and it expires.
  3. Every action is on the record before it happens, not after.

Even keyboard shortcuts hold to this. Delivering Ctrl+S to a window nobody is
looking at appears impossible — posted keys carry no modifier state, and
synthesised ones go to the real foreground — and the first version of this
package refused to try. It is possible: attaching to the target thread shares
its keyboard state table, which makes the modifier true from the
application's point of view without the system foreground ever moving.
`actions.py` carries the measurements and the two details that make it safe.

What is NOT claimed: that the user gets a second SYSTEM mouse pointer.
Windows has one cursor and one input queue per desktop, and no supported way
to add another — separate desktop objects are isolated but input-dead, and a
real second pointer means a second machine. Nothing here needs one, which is
the point: a control pattern addresses a window directly, so the work happens
without a pointer at all.

What the user DOES get is a second pointer to look at, which is a different
claim and a weaker one, and it turns out to be the one that matters. Working
invisibly solves the safety problem and creates a legibility problem: an agent
filling in a spreadsheet without moving anything looks exactly like an agent
doing nothing, and a user who cannot tell those apart cannot supervise either.
So `pointer.py` paints one — a click-through, never-focusable overlay window
that glides to whatever is being operated, which is precisely how Microsoft
Teams shows a remote participant's cursor during Give Control. It is drawn,
not driven: the real cursor stays the user's, and the painted one cannot take
a click even in principle, because it is invisible to hit-testing.
"""
from __future__ import annotations

__all__ = ["targets", "vision", "tree", "actions", "grants", "session",
           "pointer", "workflows", "failures", "operations", "waiting", "chromium", "recovery", "observed"]
