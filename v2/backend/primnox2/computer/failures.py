"""Why a desktop action failed, as a code rather than a sentence.

Every refusal in this package is already written to be read by a model, and
those sentences are good — but a sentence cannot be dispatched on. "That window
has been closed" and "the active session is for Notepad, not Calculator" call
for completely different responses, and today the only thing that can tell them
apart is a language model spending a turn reading English.

That is the wrong division of labour. Most desktop failures have a *correct*
response that needs no intelligence at all: a stale target should be re-resolved
and retried once, a window that is not ready should be waited for, a permission
refusal should stop immediately and ask. Codes are what let the runtime do that
work itself, and reserve the model for the failures that genuinely need
judgement.

The taxonomy is deliberately small. A code earns its place by having a
DIFFERENT recovery from its neighbours; anything that would be handled
identically belongs under the same code, however differently it reads.

Nothing here changes what the model is told. The sentence still travels with
the result — the code travels alongside it, for the runtime.
"""
from __future__ import annotations

# ── The taxonomy ────────────────────────────────────────────────────────────

TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
TARGET_STALE = "TARGET_STALE"
PRECONDITION_FAILED = "PRECONDITION_FAILED"
EXECUTION_FAILED = "EXECUTION_FAILED"
POSTCONDITION_FAILED = "POSTCONDITION_FAILED"
PERMISSION_DENIED = "PERMISSION_DENIED"
FOCUS_CHANGED = "FOCUS_CHANGED"
WINDOW_CHANGED = "WINDOW_CHANGED"
UI_NOT_READY = "UI_NOT_READY"
APP_NOT_RESPONDING = "APP_NOT_RESPONDING"
VISUAL_GROUNDING_FAILED = "VISUAL_GROUNDING_FAILED"
VERIFICATION_UNAVAILABLE = "VERIFICATION_UNAVAILABLE"
TIMEOUT = "TIMEOUT"
USER_INTERVENED = "USER_INTERVENED"

# ── What the runtime should do about each ───────────────────────────────────
#
# These are policies, not suggestions: the recovery engine dispatches on them
# before the model is consulted. Four strategies, and the distinctions matter:
#
#   REGROUND  the target moved or went stale. Re-read, rematch by selector,
#             try once more. Safe because nothing was changed by the failure.
#   WAIT      the UI is not ready yet. Wait on a readiness predicate rather
#             than sleeping, then retry.
#   ASK       ambiguous or blocked in a way only the user can settle. Stop and
#             put a real question, with the real options.
#   STOP      do not retry. Either it will fail identically, or retrying is
#             itself unsafe.
#
# STOP is the default for anything unclassified, and that is deliberate: an
# unrecognised failure retried automatically is how one broken action becomes
# several.
REGROUND, WAIT, ASK, STOP = "reground", "wait", "ask", "stop"

RECOVERY: dict[str, str] = {
    TARGET_NOT_FOUND: REGROUND,
    TARGET_STALE: REGROUND,
    WINDOW_CHANGED: REGROUND,
    FOCUS_CHANGED: REGROUND,
    UI_NOT_READY: WAIT,
    APP_NOT_RESPONDING: WAIT,
    TIMEOUT: WAIT,
    TARGET_AMBIGUOUS: ASK,
    PERMISSION_DENIED: STOP,
    USER_INTERVENED: STOP,
    PRECONDITION_FAILED: STOP,
    POSTCONDITION_FAILED: STOP,
    EXECUTION_FAILED: STOP,
    VISUAL_GROUNDING_FAILED: STOP,
    VERIFICATION_UNAVAILABLE: STOP,
}

# Codes that PROVE the operation never ran.
#
# This is the distinction that decides whether an automatic retry is safe, and
# it is not the same question as whether the operation is idempotent. A click
# is emphatically not idempotent — pressing Send twice sends twice — and yet a
# click that failed with TARGET_NOT_FOUND is perfectly safe to retry, because
# there was no target, so nothing was pressed.
#
# The complement is the dangerous set. TIMEOUT, FOCUS_CHANGED and
# APP_NOT_RESPONDING all mean "we stopped waiting for an answer", which is not
# the same as "it did not happen" — the application may well be part-way
# through. Those may only be retried when repeating the operation is harmless
# on its own terms, which is where `Verb.safe_to_repeat` comes in.
BEFORE_EXECUTION = frozenset({
    TARGET_NOT_FOUND, TARGET_STALE, TARGET_AMBIGUOUS, PRECONDITION_FAILED,
    UI_NOT_READY, PERMISSION_DENIED, VISUAL_GROUNDING_FAILED,
})

# How many times the runtime may act on the strategy by itself. Once, for the
# retryable classes: a target that is still stale after one clean re-read is
# not a timing problem, and a second automatic attempt just spends the turn
# arriving at the same place more slowly.
MAX_AUTOMATIC_ATTEMPTS = 1


class Failure(Exception):
    """A desktop failure that knows its own kind.

    Subclassed by the existing exception types rather than replacing them, so
    every current `except grants.Denied` keeps working and the codes arrive as
    an addition rather than a migration.
    """

    code = EXECUTION_FAILED

    def __init__(self, message: str, code: "str | None" = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


def classify(exc: BaseException) -> str:
    """The code for an exception, however it was raised.

    Explicit beats inferred: an exception carrying its own `code` is trusted,
    because the raise site knew more than any inspection can recover. What is
    left is the long tail — the plain `ValueError`s and `LookupError`s this
    package still raises in places — and for those the type is the best
    available signal.
    """
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in RECOVERY:
        return code

    # Imported here rather than at module scope: every one of these modules
    # imports something that would import this one back.
    from . import actions, grants, session, targets, vision

    if isinstance(exc, grants.Denied):
        return PERMISSION_DENIED
    if isinstance(exc, targets.Stale):
        return TARGET_STALE
    if isinstance(exc, session.Ambiguous):
        return TARGET_AMBIGUOUS
    if isinstance(exc, vision.CaptureError):
        return VISUAL_GROUNDING_FAILED
    if isinstance(exc, actions.ActionFailed):
        return EXECUTION_FAILED
    if isinstance(exc, LookupError):
        return TARGET_NOT_FOUND
    if isinstance(exc, TimeoutError):
        return TIMEOUT
    return EXECUTION_FAILED


def recovery_for(code: str) -> str:
    return RECOVERY.get(code, STOP)


def describe(code: str) -> dict:
    """The code and its policy, as a caller would attach them to a result."""
    return {"code": code, "recovery": recovery_for(code)}
