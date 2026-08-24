"""Computer Use tools — the agent's hands, exposed to the model.

Where permission is enforced here is worth stating plainly, because it is not
where the rest of this package puts it.

Every other dangerous tool is gated per call by `runtime.execute`: run_python
asks before each run, and that is right, because each run is a different piece
of code with different consequences. Clicking is not like that. A session that
asked before every click would produce forty prompts to fill in one form, and
a user answering forty prompts is not reading any of them — the request loses
all of its meaning at that rate, which is a worse outcome than asking less.

So approval happens once, at `control_window`, and it is approval of a
*window* rather than of a keystroke. The action tools are registered LOW and
carry no manifest, so the runtime does not prompt for them; their authority
comes from `grants.require`, which every one of them passes through, and which
refuses on the wrong window, an expired grant, or a read-only session. The
compensating control for asking less often is that every action is on the
event stream before it is attempted (`session.act`), so the user watches it
happen and can cut the session at any point.

`control_window` itself is marked `always_ask`, which overrides
PRIMNOX2_AUTO_APPROVE. Auto-approval is defensible everywhere else here
because the sandbox survives a bad generation; this has no sandbox behind it,
so skipping the question does not weaken the boundary, it removes it.

Several windows may be under control at once, because driving a browser and a
spreadsheet in one task is an ordinary thing to want. Every tool therefore
takes an optional `window`, which is required only when it would otherwise be
ambiguous — with one session open, saying which one is noise; with three, a
guess would eventually click Send in the wrong application.
"""
from __future__ import annotations

import win32gui

from ..assets import service as assets
from ..computer import (actions, chromium, failures, grants, observed,
                        operations, recovery, session as sessions, targets,
                        tree, vision, waiting, workflows)
from .registry import HIGH, LOW, ToolContext, ToolSpec, register


def _session(ctx: ToolContext, args: dict) -> sessions.Session:
    active = sessions.current(ctx.conversation_id, (args.get("window") or "").strip() or None)
    if active is None:
        open_now = sessions.live(ctx.conversation_id)
        if open_now:
            raise grants.Denied(
                "That window is not under control. Currently controlled: "
                + "; ".join(f"{s.grant.label} ({s.grant.handle})" for s in open_now))
        raise _denied(
            "No window is under control right now. Call control_window first "
            "and let the user approve it — nothing can be read or clicked "
            "until they do.", failures.PRECONDITION_FAILED)
    return active


def _ok(summary: str, output: str = "", **extra) -> dict:
    return {"status": "success", "summary": summary,
            "output": output or summary, **extra}


def _bounded(output: str, name: str, ctx: ToolContext) -> str:
    """Keep a tree render inside the inline budget, archiving the remainder.

    Every other tool in this package already does this — `builtins._clip` and
    `builtins._store_output`, governed by `tools.inline_output_chars` — and the
    computer tools were the one family that bypassed it, returning whole
    element trees straight through `_ok`.

    That matters more here than anywhere else because of how the tool loop
    works: results are appended to the message list and re-sent on every
    subsequent iteration, so an unbounded tree is not paid once, it is paid
    once per remaining step. Measured, a browser read renders at 10,000-16,000
    tokens, and an eight-step turn re-billed its results to roughly 360,000
    input tokens before the provider refused the request outright.

    Imported from `builtins` rather than duplicated: two copies of a
    truncation rule drift, and the one that drifts is the one nobody tests. If
    a third consumer appears, these helpers should move to a shared module.
    """
    from .builtins import _inline_chars, _store_output

    cap = _inline_chars()
    if len(output) <= cap:
        return output

    asset_id = _store_output(output, name, ctx)
    remainder = len(output) - cap
    if asset_id:
        return (output[:cap] + f"\n… {remainder} more characters. The full "
                f"listing is asset {asset_id} — read_asset it if you need the "
                "rest, or read the window again for the part you need.")
    # The archive failing must not fail the read. Say what is missing, so the
    # model does not treat a truncated tree as the whole window.
    return (output[:cap] + f"\n… {remainder} more characters, not shown "
            "and not stored. This listing is INCOMPLETE — do not conclude that "
            "an element is absent from it.")


def _fenced(body: str, *, source: str, active) -> str:
    """Mark content that came off the screen as content that came off the screen.

    Element names, field values and page text are written by whoever wrote the
    application or the page — not by the user — and they arrive in the same
    context window, in the same format, as the user's actual request. The
    substrate is the only layer that still knows which is which; by the time
    this is a string in a message list the provenance is gone.

    A page that addresses the agent directly is also noted on the timeline.
    Not filtered — a page that legitimately contains the words "ignore
    previous instructions" is a page ABOUT prompt injection, and refusing to
    show it would make Primnox useless for exactly the work most worth doing
    carefully. Flagged, so the user watching knows the screen tried to talk to
    the agent.
    """
    if observed.looks_like_an_instruction(body):
        active.record(
            "observed", f"{source} contains text addressed to the agent - "
                        "treated as page content, not as instructions",
            status="done")
    return observed.fence(body, source=source)


def _fail(summary: str, code: "str | None" = None) -> dict:
    # Returned as a result rather than raised: a refusal is information the
    # model should act on, and the messages in this package are written to be
    # read by one.
    result = {"status": "error", "summary": summary, "output": summary}
    if code:
        result.update(failures.describe(code))
    return result


_RECOVERABLE = (grants.Denied, sessions.Ambiguous, targets.Stale,
                actions.ActionFailed, vision.CaptureError, LookupError,
                ValueError)


def _guard(operation, *, verb: "str | None" = None,
           ctx: "ToolContext | None" = None, args: "dict | None" = None):
    """Turn this package's exceptions into results a model can work with —
    and, where the code says so, fix them first.

    The classification half of this has been here since the taxonomy landed:
    the sentence goes to the model, the code goes to the runtime. What was
    missing is anything that ACTED on the code. Every failure, however
    mechanical, came back as prose, and the model spent a turn deciding to
    re-read the window and try again — which is precisely what
    `failures.RECOVERY` already said to do.

    The cost of that is worst exactly where it is least visible. A stale ref in
    the middle of a five-step batch does not cost one turn, it costs the batch:
    the run stops, the model re-reads, re-plans the remaining steps against a
    new tree and re-sends them, for a failure whose correct handling was "look
    again".

    One automatic attempt, never two, and only when `recovery.plan_for` says
    the operation either did not run or is harmless to repeat. Anything else
    is handed back with the reason attached, so a model that gets a failure
    can see that the runtime already considered fixing it and declined.
    """
    try:
        return operation()
    except _RECOVERABLE as exc:
        code = failures.classify(exc)
        plan = recovery.plan_for(code, verb)
        if not plan.retry or ctx is None:
            return _fail(str(exc), code)

        try:
            _reground(plan, ctx, args or {})
            result = operation()
        except _RECOVERABLE as second:
            # The retry failed too. The SECOND failure is what gets reported,
            # because it describes the world as it is now — reporting the
            # first would send the model to look at a window that has since
            # been re-read.
            second_code = failures.classify(second)
            failed = _fail(str(second), second_code)
            failed["retried"] = plan.strategy
            return failed

        if isinstance(result, dict) and result.get("status") == "success":
            # Said out loud rather than hidden. Recovery that is invisible is
            # recovery nobody can audit, and "it worked on the second try
            # after the window moved" is worth knowing when the same step
            # starts failing every time.
            note = (f" (the first attempt failed — {str(exc)[:120]} — so the "
                    f"window was re-read and this was retried once)")
            result["summary"] = result.get("summary", "") + note
            result["recovered"] = plan.strategy
        return result


def _reground(plan, ctx: ToolContext, args: dict) -> None:
    """Put the world back in a state worth retrying against.

    REGROUND re-reads, which is what makes the retry different from the first
    attempt rather than a repeat of it — the ref then rebinds by selector
    against the new tree. WAIT lets the window settle first, because the
    failure was that it was not ready, and reading it again immediately would
    find it not ready again.
    """
    active = sessions.current(ctx.conversation_id,
                              (args.get("window") or "").strip() or None)
    if active is None:
        return
    if plan.strategy == failures.WAIT:
        waiting.wait_until(active.target, waiting.settled(), timeout_s=5.0)
    active.read_tree()


def _truthy(value) -> bool:
    """Read a boolean argument from either protocol.

    A native tool call delivers a real bool; the emulated protocol delivers
    whatever the model typed inside a JSON block, which is routinely the
    string "true". Both have to mean the same thing here.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "y")
    return bool(value)


def _asset_bytes(asset_id: str) -> bytes:
    """Read a stored asset back off disk.

    Via the row rather than the path directly, so a workflow id that names
    something deleted, or something that was never an asset, fails as a
    sentence rather than as a FileNotFoundError from three frames down.
    """
    record = assets.get(asset_id)
    if record is None:
        raise ValueError(
            f"There is no asset {asset_id!r}. Workflow ids come from "
            "record_workflow — check the id, or record the workflow again.")
    try:
        with open(record["path"], "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise ValueError(f"{record.get('name', asset_id)!r} could not be read ({exc})")


def _window_argument(required: bool = False) -> dict:
    return {"window": {
        "type": "string", "required": required,
        "description": ("Which controlled window. Only needed when more than "
                        "one is under control.")}}


# ── Discovery ────────────────────────────────────────────────────────────────

def _list_windows(args: dict, ctx: ToolContext) -> dict:
    query = (args.get("query") or "").strip()
    found = targets.find(query) if query else targets.enumerate_windows()
    if not found:
        return _ok(
            f"no windows match {query!r}" if query else "no windows found",
            f"Nothing matched {query!r}. Call this again with no query to see "
            "every open window." if query else "No open windows were found.")

    lines = []
    for target in found[:40]:
        marks = " ".join(filter(None, [
            "FOREGROUND" if target.foreground else "",
            "MINIMIZED" if target.minimized else "",
            "BROWSER" if target.is_browser else ""]))
        width, height = target.size
        lines.append(f"{target.handle}  {target.label()}  "
                     f"({width}×{height}){' ' + marks if marks else ''}")

    return _ok(f"found {len(found)} windows",
               "\n".join(lines) + "\n\nUse the handle on the left with "
               "control_window to ask the user for access to one of these.")


register(ToolSpec(
    name="list_windows",
    description=("List the windows open on the user's desktop. Use this to "
                 "find a window before asking to control it."),
    parameters={"query": {
        "type": "string", "required": False,
        "description": "Optional filter: part of a window title or program name."}},
    # LOW, and this is a real judgement call rather than an oversight. Window
    # titles are disclosure — "Q3 redundancies.docx — Word" names a document
    # nobody offered to show. What makes listing acceptable without its own
    # prompt is that it is the step that lets the agent ASK a precise question:
    # the alternative is prompting the user to approve a window before either
    # party can name one. Nothing is read from inside a window here, and every
    # listing is on the event stream.
    danger=LOW,
    handler=_list_windows,
))


# ── The gate ─────────────────────────────────────────────────────────────────

def _denied(message: str, code: str) -> grants.Denied:
    """A refusal that declares its own kind.

    `grants.Denied` is the transport for every refusal the gate raises, so
    inferring a code from the type alone makes them all PERMISSION_DENIED —
    and "no window matches that name" would then be treated as a security
    refusal and told to STOP, when the correct response is to go and look
    again. The raise site knows which it is; this lets it say so.
    """
    error = grants.Denied(message)
    error.code = code
    return error


def _distinguish(target, siblings: list) -> str:
    """What to add when a title alone does not identify a window.

    Measured: ten windows titled "Untitled - Notepad" were open at once, which
    makes both the model's choice and the user's approval a coin flip. The
    approval prompt is the one screen the whole safety model rests on, so a
    title it shares with nine other windows is not good enough to approve
    against.
    """
    if not any(s.handle != target.handle and s.title == target.title
               for s in siblings):
        return ""
    width, height = target.size
    left, top = target.bounds[0], target.bounds[1]
    marks = [f"{width}×{height} at {left},{top}"]
    if target.foreground:
        marks.append("frontmost")
    if target.minimized:
        marks.append("minimized")
    return f" [{'; '.join(marks)}]"


def _resolve_window(value: str):
    """A handle, or a name the model actually has.

    `targets.resolve` takes `win_<hwnd>_<pid>`, which no model produces from a
    user saying "Notepad" — measured four times out of four, each costing a
    round-trip to be told off and go read the window list. Accepting a title
    here removes that turn from essentially every desktop task.

    A value SHAPED like a handle is still resolved strictly, and a stale one
    still fails: that identity check is what stops an expired approval for a
    text editor becoming live authority over whatever now owns the number.
    Falling back to a title search there would defeat it entirely.

    Ambiguity is refused rather than guessed, and the refusal carries the
    candidates so the model can choose one instead of burning a turn
    rediscovering them.
    """
    value = (value or "").strip()
    if not value:
        raise _denied("No window was named. Call list_windows first.",
                      failures.TARGET_NOT_FOUND)

    looks_like_handle = value.startswith("win_") and value.count("_") >= 2
    try:
        return targets.resolve(value)
    except targets.Stale:
        if looks_like_handle:
            raise

    matches = targets.find(value)
    if not matches:
        raise _denied(
            f"No open window matches {value!r}. Call list_windows to see what "
            "is actually open — the title may have changed, or the program "
            "may not be running.", failures.TARGET_NOT_FOUND)
    if len(matches) == 1:
        return matches[0]

    lines = [f"  {t.handle}  {t.label()}{_distinguish(t, matches)}"
             for t in matches[:10]]
    raise _denied(
        f"{len(matches)} windows match {value!r}, so it is not clear which one "
        "is meant. Pass one of these handles instead:\n" + "\n".join(lines),
        failures.TARGET_AMBIGUOUS)


def _describe_request(args: dict) -> str:
    """The sentence the user actually reads. See ToolSpec.prompt."""
    handle = args.get("window") or ""
    scope = grants.ACT if (args.get("mode") or "control") == "control" else grants.READ
    # Resolved the same way the handler will, so the window the user approves is
    # the window that gets operated. Previously this asked about "an unknown
    # window (Notepad)" whenever the model passed a title — a prompt that names
    # nothing cannot be meaningfully approved.
    try:
        target = _resolve_window(handle)
        handle = target.handle
        label = target.label() + _distinguish(target, targets.enumerate_windows())
    except (targets.Stale, grants.Denied):
        label = f"an unknown window ({handle})"

    grant = grants.Grant(handle=handle, label=label, scope=scope)
    reason = (args.get("reason") or "").strip()
    # The model's stated reason goes FIRST and is marked as the model's, not
    # as fact. It is the only part of this prompt that explains why the user
    # is being asked at all, and it is also the only part that could be a
    # misrepresentation — so it is attributed rather than asserted.
    header = f"Primnox says it needs this in order to: {reason}\n\n" if reason else ""
    return header + grant.describe()


def _control_window(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        target = _resolve_window(args.get("window"))
        mode = (args.get("mode") or "control").strip().lower()
        if mode not in ("control", "read"):
            return _fail(f"mode must be 'control' or 'read', not {mode!r}")
        scope = grants.ACT if mode == "control" else grants.READ

        active = sessions.open_session(
            target, scope, conversation_id=ctx.conversation_id,
            turn_id=ctx.turn_id)

        snapshot = active.read_tree()
        verb = "controlling" if scope == grants.ACT else "reading"
        body = [f"Session open on {target.label()} "
                f"({active.grant.remaining_s()}s remaining)."]

        if snapshot.blind:
            body.append(_blind_advice(target))
        else:
            body.append(f"\nElements you can act on:\n"
                        f"{snapshot.render(only_actionable=True)}")
            body.append(
                "\nAct on these with click_element and type_into, using the "
                "whole ref in brackets, including the part after @, "
                "which says which read it came from. Quote it back "
                "exactly: if the window has moved on, a stamped ref is "
                "matched to the same control in the current read rather "
                "than to whatever now sits in its place."
                if scope == grants.ACT else
                "\nThis session is read-only; nothing here can be clicked.")

        others = [s for s in sessions.live(ctx.conversation_id) if s is not active]
        if others:
            body.append("\nAlso under control: "
                        + "; ".join(f"{s.grant.label} ({s.grant.handle})"
                                    for s in others)
                        + ". Pass `window` to say which one you mean.")

        return _ok(f"{verb} {target.label()}",
                   _bounded("\n".join(body),
                            f"{target.label()} controls.txt", ctx),
                   session_id=active.id)

    return _guard(run)


register(ToolSpec(
    name="control_window",
    description=("Ask the user for permission to read or control one window "
                 "on their desktop. Required before any other computer tool. "
                 "Returns the window's controls."),
    parameters={
        "window": {"type": "string", "required": True,
                   "description": "A window handle from list_windows, or the "
                                  "window's title if you know it."},
        "reason": {"type": "string", "required": True,
                   "description": "What you intend to do, in one plain sentence. "
                                  "The user reads this before deciding."},
        "mode": {"type": "string", "required": False,
                 "description": "'control' to click and type, 'read' to only "
                                "look. Defaults to 'control'."},
    },
    # HIGH, so the grant is never reusable and never auto-covered by a
    # previous answer: each window is its own decision.
    danger=HIGH,
    # Asked even when PRIMNOX2_AUTO_APPROVE says otherwise. This question is
    # the only boundary between the agent and the user's real applications;
    # there is no sandbox behind it to fall back on.
    always_ask=True,
    prompt=_describe_request,
    handler=_control_window,
))


# ── Reading ──────────────────────────────────────────────────────────────────

def _blind_advice(target: targets.Target) -> str:
    """What to say about a window with no usable accessibility tree.

    The failure this prevents is specific: an empty element list reads to a
    model as an empty window, so it reports the application as blank and
    stops. Saying that the window is real but unreadable BY ELEMENT, and
    naming the route that still works, is the difference between a dead end
    and a fallback.
    """
    if target.is_browser:
        why = ("This browser is not exposing its page content to "
               "accessibility. Chromium builds enable that on demand and some "
               "only do so when assistive technology is detected, so the page "
               "is there and readable by eye but not as a list of elements.")
    else:
        why = ("This is normal for games, media players, and custom-drawn "
               "applications, which ship no UI Automation provider.")

    return (
        f"\n{target.label()} exposes no operable accessibility elements. "
        f"{why} The window is NOT empty — it simply cannot be read as a list "
        "of controls, and reporting it to the user as blank would be wrong.\n"
        "Work from a screenshot instead: call read_window with screenshot "
        "true, look at where things are, and use click_at with coordinates "
        "measured from the window's top-left corner. Every click is a guess "
        "at that point, so take a fresh screenshot after each one rather than "
        "assuming it landed.")


def _tree_or_delta(active, snapshot, *, only: bool, full: bool) -> str:
    """The whole tree, or only what moved since the last read.

    Re-reading is the most common thing a model does and the most wasteful.
    Nothing in a window changes between two reads except the part the model
    just acted on, and sending the tree again to communicate that costs the
    whole tree — measured at ~2,000 characters on an Explorer window to say
    one value moved. Worse, it buries the answer: the delta IS what the model
    wanted to know, and the tree is the haystack it is in.

    Three rules, and the second one is the one that keeps this honest:

      No previous read, or `full` — send the tree. There is nothing to diff
      against, or the caller said they want everything.

      A delta is only sent when it is genuinely smaller. A window that changed
      completely produces a diff longer than the tree, and sending that would
      be paying the cost of the idea without getting anything for it.

      Nothing changed is a REAL answer, and the most valuable one here. A
      model polling a window for a download to finish currently pays a full
      tree per check.
    """
    whole = snapshot.render(only_actionable=only)
    previous = active.previous
    if full or previous is None:
        return whole

    changes = tree.diff(previous, snapshot)
    if only:
        changes = [c for c in changes
                   if c.element is None or c.element.actionable()]
    delta = tree.render_diff(changes, generation=snapshot.generation,
                             against=previous.generation)
    if not changes:
        return (f"{delta}\nThe {len(snapshot.actionable())} elements from read "
                f"{previous.generation} are all still there, unchanged. Refs "
                f"from that read still work.")
    if len(delta) >= len(whole):
        return whole
    return (f"{delta}\n\nEverything else is as it was at read "
            f"{previous.generation}. Pass full=true for the whole tree.")


def _read_window(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        snapshot = active.read_tree()
        only = _truthy(args.get("only_actionable", True))

        # A window with no tree gets the screenshot whether or not one was
        # asked for. Refusing to volunteer the only usable view of it would
        # be technically obedient and useless.
        wants_image = _truthy(args.get("screenshot")) or snapshot.blind
        body = [snapshot.title or active.target.label()]

        if snapshot.blind:
            body.append(_blind_advice(active.target))
        else:
            body.append(_fenced(
                _tree_or_delta(active, snapshot, only=only,
                               full=_truthy(args.get("full"))),
                source=snapshot.title or active.target.label(),
                active=active))

        ref = None
        if wants_image:
            try:
                image = active.capture()
                stored = assets.ingest_bytes(
                    vision.to_png(image),
                    f"{snapshot.title or 'window'}.png",
                    # `screenshot`, not a new `computer_use` source: the assets
                    # table CHECKs this column against a fixed vocabulary, and
                    # a window capture is a screenshot by any reading. Adding a
                    # value would mean a migration to say nothing new.
                    source="screenshot",
                    conversation_id=ctx.conversation_id, turn_id=ctx.turn_id)
                ref = stored["id"]
                body.append(
                    f"\nA screenshot ({image.width}×{image.height}) was "
                    "captured and is shown to the user."
                    + ("" if snapshot.blind else
                       " Describe the window from the element list above — do "
                       "not claim to have seen anything in the image that the "
                       "list does not support."))
            except vision.CaptureError as exc:
                # The capture failing is not the read failing — the tree is
                # the reliable half and is already in hand. Unless there is no
                # tree either, in which case the advice just given (work from
                # a screenshot) has been overtaken, and leaving both sentences
                # standing would send the model looking for an image that does
                # not exist.
                if snapshot.blind:
                    body.append(
                        f"\nAnd there is no screenshot either: {exc}\n"
                        "So this window can be neither read nor seen. Do not "
                        "guess at coordinates — clicking blind in an "
                        "application nobody can observe is how something gets "
                        "broken silently. Tell the user plainly that Primnox "
                        "cannot work with this window, and ask them what they "
                        "want to do.")
                else:
                    body.append(f"\nNo screenshot: {exc}")

        return _ok(f"read {len(snapshot.elements)} elements from {snapshot.title}",
                   _bounded("\n".join(body),
                            f"{snapshot.title or 'window'} tree.txt", ctx),
                   result_ref=ref)

    return _guard(run, verb='read', ctx=ctx, args=args)


register(ToolSpec(
    name="read_window",
    description=("Read the controls and text of a controlled window. Call this "
                 "again after anything that changes it."),
    parameters={
        **_window_argument(),
        "only_actionable": {"type": "boolean", "required": False,
                            "description": "Only list elements that can be "
                                           "operated. Defaults to true."},
        "full": {"type": "boolean", "required": False,
                 "description": "Return the whole tree instead of only what "
                                "changed since the last read."},
        "screenshot": {"type": "boolean", "required": False,
                       "description": "Also capture a picture of the window."},
    },
    danger=LOW,
    handler=_read_window,
))


# ── Acting ───────────────────────────────────────────────────────────────────

def _centre(bounds: tuple) -> "tuple[int, int] | None":
    """The middle of a screen rectangle, or None if it has no area.

    Zero-area bounds are ordinary rather than exceptional — an offscreen or
    collapsed element reports them — and pointing at the top-left corner of
    the desktop because a control had no size would be worse than not
    pointing at all.
    """
    left, top, right, bottom = bounds
    if right <= left or bottom <= top:
        return None
    return ((left + right) // 2, (top + bottom) // 2)


def _same_text(wanted: str, got: str) -> bool:
    """Compare what was asked for against what the control now holds.

    Line endings are normalised because a write of "hello" into a document
    frequently reads back as "hello\r\n" — the control owns its own
    trailing newline, and treating that as a contradiction would flag a
    perfectly good write as a failure, which is its own kind of lie.
    """
    scrub = lambda s: s.replace("\r\n", "\n").strip()
    return scrub(wanted) == scrub(got)


def _verify_value(element, expected: str):
    """Confirm a write by asking the control what it now holds."""
    def check() -> sessions.Verification:
        got = tree.live_value(element)
        if got is None:
            return sessions.Verification.unavailable(
                f"{element.role} {element.name!r} did not report a value back")
        if _same_text(expected, got):
            return sessions.Verification(
                "confirmed", 0.99, [{"kind": "value_readback",
                                     "source": "uia"}])
        if expected and expected.strip() in got:
            # The text is present alongside something else — an append, a
            # prefix the control added. Real, but not the exact state asked
            # for, and the confidence says so.
            return sessions.Verification(
                "confirmed", 0.85,
                [{"kind": "value_readback", "source": "uia", "match": "contains"}],
                "the value contains the text but is not exactly it")
        shown = got if len(got) <= 60 else got[:60] + "…"
        return sessions.Verification(
            "contradicted", 0.99,
            [{"kind": "value_readback", "source": "uia"}],
            f"the field now reads {shown!r}")
    return check


def _verify_toggle(element, before: "str | None"):
    """Confirm a click on a toggle by watching the state flip.

    Only toggles have an observable postcondition here. A plain button press
    has none — whatever it did happened somewhere else — so it is reported
    UNCONFIRMED rather than assumed. That is the honest answer, and it is the
    one that stops a chain of unverified clicks reading as success.
    """
    def check() -> sessions.Verification:
        if before is None:
            return sessions.Verification.unavailable(
                "a button press has no state of its own to re-read; confirm it "
                "by reading the window and looking at what changed")
        after = tree.live_toggle(element)
        if after is None:
            return sessions.Verification.unavailable(
                "the toggle state could not be read back")
        if after != before:
            return sessions.Verification(
                "confirmed", 0.99,
                [{"kind": "toggle_state", "source": "uia",
                  "from": before, "to": after}])
        return sessions.Verification(
            "contradicted", 0.99,
            [{"kind": "toggle_state", "source": "uia", "state": after}],
            "the toggle is in the same state it started in")
    return check


def _click_element(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        element = active.element(args["ref"])
        reversal = _reversal_for(element)
        step = workflows.step_for(
            "click", tree.selector_for(active.snapshot, element), {})
        # Read BEFORE the click, or there is nothing to compare against.
        toggled_from = tree.live_toggle(element)
        result = active.act(
            "click", f"click {element.role} {element.name or element.ref!r}",
            lambda: actions.invoke(element), reversal=reversal, step=step,
            at=_centre(element.bounds), route=actions.ROUTE_PATTERN,
            verify=_verify_toggle(element, toggled_from))
        return _ok(result, f"{result}. Read the window again to see what "
                           "changed before acting further.")
    return _guard(run, verb='click', ctx=ctx, args=args)


def _reversal_for(element: tree.Element) -> "sessions.Reversal | None":
    """A toggle can be put back; a button press cannot.

    Undo exists only where the previous state was captured before the change.
    Offering it anywhere else would be a lie a model would act on.
    """
    if "toggle" not in element.patterns:
        return None
    try:
        before = element.control.GetTogglePattern().ToggleState
    except Exception:
        return None

    def restore() -> str:
        try:
            if element.control.GetTogglePattern().ToggleState != before:
                element.control.GetTogglePattern().Toggle()
        except Exception as exc:
            raise actions.ActionFailed(
                f"could not put {element.name!r} back ({exc})")
        return f"put {element.name or element.role} back"

    return sessions.Reversal(f"toggling {element.name or element.role}", restore)


register(ToolSpec(
    name="click_element",
    description=("Operate an element in a controlled window, by the ref from "
                 "read_window. Runs in the background: the user's mouse does "
                 "not move."),
    parameters={
        **_window_argument(),
        "ref": {"type": "string", "required": True,
                "description": "An element ref exactly as read_window "
                               "printed it, such as 'e12@3'."},
    },
    danger=LOW,
    handler=_click_element,
))


def _type_into(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        text = args.get("text") or ""
        ref = (args.get("ref") or "").strip()

        if ref:
            element = active.element(ref)
        else:
            if active.snapshot is None:
                active.read_tree()
            element = tree.find_text_target(active.snapshot)
            if element is None:
                return _fail(
                    "This window has no obvious text field, so there is "
                    "nowhere to type by default. Read the window and pass the "
                    "ref of the element you mean.")

        previous = element.value or ""
        if _truthy(args.get("append")):
            # SetValue replaces. Appending is therefore read-then-write, and
            # it is opt-in because silently appending would make it impossible
            # to clear a field.
            text = previous + text

        def restore() -> str:
            actions.set_value(element, previous)
            return f"restored {element.name or element.role} to its previous text"

        reversal = sessions.Reversal(
            f"setting {element.name or element.role}", restore)
        step = workflows.step_for(
            "type", tree.selector_for(active.snapshot, element),
            {"text": args.get("text") or "", "append": _truthy(args.get("append"))})

        result = active.act(
            "type", f"type into {element.name or element.role}",
            lambda: actions.set_value(element, text),
            reversal=reversal, step=step, at=_centre(element.bounds),
            route=actions.ROUTE_PATTERN, verify=_verify_value(element, text))
        return _ok(result)
    return _guard(run, verb='type', ctx=ctx, args=args)


def _read_page(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        try:
            snapshot = active.read_page()
        except chromium.Unavailable as exc:
            # Not a failure of the session, and not a dead end: the window is
            # perfectly readable the ordinary way. Saying which route still
            # works is the difference between a refusal and an obstacle.
            return _fail(
                f"{exc} Use read_window instead.",
                failures.VERIFICATION_UNAVAILABLE)

        body = [f"{snapshot.title} — the page itself, "
                f"{len(snapshot.elements)} elements.",
                _fenced(_tree_or_delta_page(
                            active, snapshot,
                            full=_truthy(args.get("full"))),
                        source=f"the web page in {snapshot.title}",
                        active=active),
                "\nThese are page elements, with 'p' refs. The browser's own "
                "controls — tabs, the address bar, back — are not here; "
                "read_window shows those."]
        return _ok(f"read {len(snapshot.elements)} page elements from "
                   f"{snapshot.title}",
                   _bounded("\n".join(body), "page.txt", ctx))

    return _guard(run)


def _tree_or_delta_page(active, snapshot, *, full: bool) -> str:
    whole = snapshot.render(only_actionable=False)
    previous = active.previous_page
    if full or previous is None:
        return whole
    changes = tree.diff(previous, snapshot)
    delta = tree.render_diff(changes, generation=snapshot.generation,
                             against=previous.generation)
    if not changes:
        return f"{delta} Refs from that read still work."
    if len(delta) >= len(whole):
        return whole
    return f"{delta}\n\nEverything else is as it was. Pass full=true for all of it."


register(ToolSpec(
    name="read_page",
    description=("Read the web page inside a controlled browser window, over "
                 "the browser's own protocol. Much smaller and more accurate "
                 "than read_window for page content. Only works if the "
                 "browser was started with --remote-debugging-port."),
    parameters={
        **_window_argument(),
        "full": {"type": "boolean", "required": False,
                 "description": "Return everything instead of only what "
                                "changed since the last page read."},
    },
    danger=LOW,
    handler=_read_page,
))


_WAIT_CONDITIONS = {
    "appears": lambda name, role: waiting.element_appears(name, role=role),
    "disappears": lambda name, role: waiting.element_disappears(name, role=role),
    "enabled": lambda name, role: waiting.element_enabled(name, role=role),
    "text": lambda name, role: waiting.value_contains(name),
    "settles": lambda name, role: waiting.settled(),
}


def _wait_for(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        condition = (args.get("condition") or "").strip().lower()
        builder = _WAIT_CONDITIONS.get(condition)
        if builder is None:
            return _fail(
                f"{condition!r} is not something this can wait for. Available: "
                + ", ".join(sorted(_WAIT_CONDITIONS)) + ".",
                failures.PRECONDITION_FAILED)

        what = (args.get("what") or "").strip()
        if not what and condition != "settles":
            return _fail(
                f"Waiting for something to {condition} needs to know what. "
                "Pass the name of the control, as read_window printed it.",
                failures.PRECONDITION_FAILED)

        predicate = builder(what, (args.get("role") or "").strip() or None)
        timeout = float(args.get("timeout_s") or waiting.DEFAULT_TIMEOUT_S)

        # Announced before it runs, like any other action, because a wait is
        # the one thing that occupies the session for a long time while
        # producing no visible effect. A timeline that goes quiet for twenty
        # seconds and then reports a result is exactly what the log exists to
        # prevent.
        started = active.record(
            "wait", f"waiting for {predicate.description}", status="running",
            provenance=active.provenance(None))
        outcome = waiting.wait_until(active.target, predicate,
                                     timeout_s=timeout)
        active._resolve(started, "done" if outcome.ok else "failed",
                        outcome.sentence(predicate), outcome.detail)

        if not outcome.ok:
            return _fail(outcome.sentence(predicate), outcome.code())

        # One stamped read at the end, and only one. The polling reads were
        # anonymous on purpose — routing them through the session would have
        # advanced the generation on every pass and invalidated every ref the
        # model is holding, so the runtime's own waiting would have broken the
        # model's plan.
        snapshot = active.read_tree()
        body = [outcome.sentence(predicate),
                _tree_or_delta(active, snapshot, only=True, full=False)]
        return _ok(outcome.sentence(predicate),
                   _bounded("\n".join(body), "after waiting.txt", ctx))

    return _guard(run)


register(ToolSpec(
    name="wait_for",
    description=("Wait for something to happen in a controlled window, "
                 "instead of reading it over and over. Returns as soon as it "
                 "happens, with what changed."),
    parameters={
        **_window_argument(),
        "condition": {"type": "string", "required": True,
                      "description": "One of: appears, disappears, enabled, "
                                     "text, settles."},
        "what": {"type": "string", "required": False,
                 "description": "The control's name, or the text to wait for. "
                                "Not needed for 'settles'."},
        "role": {"type": "string", "required": False,
                 "description": "Narrow to one control type, e.g. 'Button'."},
        "timeout_s": {"type": "number", "required": False,
                      "description": "How long to wait. Defaults to 15s, "
                                     "capped at 120s."},
    },
    danger=LOW,
    handler=_wait_for,
))


register(ToolSpec(
    name="type_into",
    description=("Set the text of a field in a controlled window. Replaces "
                 "what is there unless append is set. Undoable."),
    parameters={
        **_window_argument(),
        "text": {"type": "string", "required": True,
                 "description": "The text to put in the field."},
        "ref": {"type": "string", "required": False,
                "description": "Element ref. Defaults to the window's main "
                               "text area."},
        "append": {"type": "boolean", "required": False,
                   "description": "Add to the existing text instead of "
                                  "replacing it."},
    },
    danger=LOW,
    handler=_type_into,
))


def _click_at(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        x, y = int(args["x"]), int(args["y"])
        button = (args.get("button") or "left").lower()
        double = _truthy(args.get("double"))
        hwnd = active.target.hwnd
        step = workflows.step_for("click", None,
                                  {"x": x, "y": y, "button": button,
                                   "double": double})
        result = active.act(
            "click", f"click at ({x}, {y})",
            lambda: actions.click_point(hwnd, x, y, button=button, double=double),
            step=step, at=_client_to_screen(active.target, x, y),
            route=actions.ROUTE_MESSAGE)
        return _ok(result)
    return _guard(run, verb='click', ctx=ctx, args=args)


register(ToolSpec(
    name="click_at",
    description=("Click a point in a controlled window, in coordinates "
                 "relative to the window's top-left. Prefer click_element — "
                 "use this for windows with no accessibility tree."),
    parameters={
        **_window_argument(),
        "x": {"type": "integer", "required": True, "description": "Pixels from the left."},
        "y": {"type": "integer", "required": True, "description": "Pixels from the top."},
        "button": {"type": "string", "required": False,
                   "description": "left, right, or middle. Defaults to left."},
        "double": {"type": "boolean", "required": False, "description": "Double-click."},
    },
    danger=LOW,
    handler=_click_at,
))


def _client_to_screen(target, x: int, y: int) -> "tuple[int, int] | None":
    """Where a click_at coordinate actually is on the glass.

    click_at works in client space — the window's content, excluding its
    frame — and the pointer draws in screen space, so the two disagree by the
    border and title bar. Asking Windows is the only way to be right about
    that: the offset differs per window style, per DPI, and per theme.
    """
    try:
        screen_x, screen_y = win32gui.ClientToScreen(target.hwnd, (x, y))
        return (screen_x, screen_y)
    except Exception:
        # A window that closed between the call and here. The click is about
        # to fail with a sentence that says so; the pointer just stays put.
        return None


def _scroll_window(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        clicks = int(args.get("clicks") or -3)
        left, top, right, bottom = active.target.bounds
        x, y = (right - left) // 2, (bottom - top) // 2
        hwnd = active.target.hwnd
        step = workflows.step_for("scroll", None, {"clicks": clicks})
        result = active.act(
            "scroll", f"scroll {'up' if clicks > 0 else 'down'}",
            lambda: actions.scroll(hwnd, x, y, clicks=clicks), step=step,
            at=_centre(active.target.bounds), route=actions.ROUTE_MESSAGE)
        return _ok(result)
    return _guard(run, verb='scroll', ctx=ctx, args=args)


register(ToolSpec(
    name="scroll_window",
    description="Scroll a controlled window. Negative scrolls down.",
    parameters={
        **_window_argument(),
        "clicks": {"type": "integer", "required": False,
                   "description": "Wheel clicks; negative is down. Defaults to -3."},
    },
    danger=LOW,
    handler=_scroll_window,
))


def _press_keys(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        raw = args.get("keys") or ""
        keys = [k for k in (raw.replace("-", "+").split("+")) if k.strip()]
        take_focus = _truthy(args.get("take_focus"))
        target = active.target

        def press():
            return actions.press_keys(target, keys, take_focus=take_focus)

        # Only the background form is recorded. A replay that quietly seizes
        # focus is not something to build by accident.
        step = (workflows.step_for("keys", None, {"keys": raw})
                if not take_focus else None)
        try:
            result = active.act(
                "keys", f"press {'+'.join(keys)}", press, step=step,
                route=(actions.ROUTE_FOREGROUND if take_focus
                       else actions.ROUTE_ATTACHED))
        except actions.NeedsFocus as exc:
            # Not a failure of the session — a refusal with a route out of it.
            return _fail(str(exc))
        return _ok(result)
    return _guard(run, verb='keys', ctx=ctx, args=args)


register(ToolSpec(
    name="press_keys",
    description=("Press a key or key combination in a controlled window, in "
                 "the background. Confirm the effect with read_window "
                 "afterwards — the keys are delivered, but whether the "
                 "application acted on them cannot be seen from here."),
    parameters={
        **_window_argument(),
        "keys": {"type": "string", "required": True,
                 "description": "A key or combination, e.g. 'enter', 'tab', "
                                "'ctrl+s', 'ctrl+shift+end'."},
        "take_focus": {"type": "boolean", "required": False,
                       "description": "Permit bringing the window to the front "
                                      "if the background route is refused, "
                                      "which interrupts the user. Rarely needed."},
    },
    danger=LOW,
    handler=_press_keys,
))


# ── Undo ─────────────────────────────────────────────────────────────────────

# ── Running several steps in one call ───────────────────────────────────────
#
# The loop this replaces is `think -> act -> think -> act`, and most of the
# thinking in it is not thinking. Filling three fields and pressing Save is
# four model calls, three of which decide nothing: the plan was complete
# before the first one.
#
# What made batching unsafe until now was not the sequencing, it was that a
# step could report success without having worked. Multiply that by k steps
# and a batch does not fail, it drifts — the second step operates a window the
# first one did not actually change, and the result reads as a clean run. The
# Verifier is what makes this safe to build: a step whose effect is
# contradicted fails, and a failed step stops the batch.
#
# The executor deliberately does not reimplement any step. It calls the same
# handlers a single tool call would, so verification, undo journalling,
# recording, the pointer and provenance all behave identically whether an
# action arrives alone or as step three of five. A batch executor with its own
# copy of that logic is a batch executor that drifts away from it.

_BATCH_STEPS = {
    "read": ("_read_window", lambda s: {}),
    "click": ("_click_element", lambda s: {"ref": s.get("ref", "")}),
    "type": ("_type_into", lambda s: {"ref": s.get("ref", ""),
                                      "text": s.get("text", ""),
                                      "append": s.get("append")}),
    "scroll": ("_scroll_window", lambda s: {"clicks": s.get("clicks")}),
    "keys": ("_press_keys", lambda s: {"keys": s.get("keys", "")}),
    "wait": ("_wait_for", lambda s: {"condition": s.get("condition", "settles"),
                                     "what": s.get("what", ""),
                                     "role": s.get("role"),
                                     "timeout_s": s.get("timeout_s")}),
}

# The action budget. Not a technical limit — it is the structural answer to a
# small model that emits forty steps because it has lost track of what it is
# doing. Eight is more than any single UI interaction needs and few enough
# that a run which goes wrong goes wrong where somebody can still read it.
MAX_BATCH_STEPS = 8


def _run_steps(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        steps = args.get("steps")
        if not isinstance(steps, list) or not steps:
            return _fail("run_steps needs a list of steps.",
                         failures.PRECONDITION_FAILED)
        if len(steps) > MAX_BATCH_STEPS:
            return _fail(
                f"{len(steps)} steps is more than one batch may run "
                f"({MAX_BATCH_STEPS}). Run the first {MAX_BATCH_STEPS}, look "
                "at the result, then decide the rest — a plan this long is "
                "usually a plan that stopped tracking what the window is "
                "doing.", failures.PRECONDITION_FAILED)

        # Parsed and classified BEFORE anything runs. A batch that turns out
        # to contain an undeclared verb halfway through has already done the
        # first half, and there is no putting that back.
        parsed = []
        for index, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                return _fail(f"step {index} is not an object.",
                             failures.PRECONDITION_FAILED)
            verb = (step.get("verb") or step.get("kind") or "").strip().lower()
            if verb not in _BATCH_STEPS:
                return _fail(
                    f"step {index}: {verb!r} is not something a batch can run. "
                    f"Available: {', '.join(sorted(_BATCH_STEPS))}.",
                    failures.PRECONDITION_FAILED)
            parsed.append((verb, step))

        # The batch's class is the worst thing in it, never the average: nine
        # reads and one keystroke that sends a message is a send.
        severity = operations.batch_severity(
            [operations.Operation(verb) for verb, _ in parsed
             if verb in operations.VERBS])

        active = _session(ctx, args)
        window = args.get("window")

        # Announced on the timeline BEFORE the first step, not summarised
        # after the last. This package's safety argument is that the user
        # watches actions happen and can cut the session mid-run; a batch
        # breaks that argument unless the announcement covers the whole batch,
        # because by the time step one appears, steps two through five are
        # already committed to. Worst case rather than average, for the same
        # reason `batch_severity` takes a max: nine reads and one send is a
        # send, and that is the sentence somebody needs before it runs.
        active.record(
            "batch",
            f"about to run {len(parsed)} steps ({', '.join(v for v, _ in parsed)}) "
            f"— worst case {severity}",
            status="running", provenance=active.provenance(None))

        lines = [f"{len(parsed)} steps, worst case {severity}:"]
        for index, (verb, step) in enumerate(parsed, 1):
            name, arguments = _BATCH_STEPS[verb]
            payload = {k: v for k, v in arguments(step).items() if v is not None}
            if window:
                payload["window"] = window
            result = globals()[name](payload, ctx)
            if result.get("status") == "error":
                lines.append(f"  {index}. {verb}: STOPPED — {result['summary']}")
                lines.append(
                    f"\nStopped at step {index} of {len(parsed)}. Steps "
                    f"{index + 1}-{len(parsed)} did NOT run. The window is in "
                    "whatever state step " + str(index - 1 if index > 1 else 1)
                    + " left it, which is not the state the rest of the plan "
                    "assumed — read it before continuing.")
                return {"status": "error", "summary": "\n".join(lines),
                        "output": "\n".join(lines),
                        "code": result.get("code", failures.EXECUTION_FAILED),
                        "recovery": result.get("recovery", failures.STOP),
                        "completed_steps": index - 1}
            lines.append(f"  {index}. {verb}: {result['summary']}")

        lines.append(f"\nAll {len(parsed)} steps completed. Read the window to "
                     "see where it ended up.")
        return _ok(f"ran {len(parsed)} steps on {active.target.title}",
                   _bounded("\n".join(lines), "batch.txt", ctx))

    return _guard(run)


register(ToolSpec(
    name="run_steps",
    description=("Run several steps on a controlled window in one call, in "
                 "order. Stops at the first step that fails or cannot be "
                 "verified. Use this when the whole plan is already known."),
    parameters={
        **_window_argument(),
        "steps": {"type": "array", "required": True,
                  "description": "Steps in order. Each is an object with a "
                                 "'verb' (read, click, type, scroll, keys, "
                                 "wait) and that verb's arguments, e.g. "
                                 "{\"verb\": \"type\", \"ref\": \"e12@3\", "
                                 "\"text\": \"hello\"}."},
    },
    danger=LOW,
    handler=_run_steps,
))


def _undo_last(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        return _ok(active.undo())
    return _guard(run)


register(ToolSpec(
    name="undo_last",
    description=("Reverse the last change Primnox made to a controlled window "
                 "that can be reversed — text it set, a toggle it flipped. "
                 "Button presses cannot be undone; this says so rather than "
                 "guessing."),
    parameters=_window_argument(),
    danger=LOW,
    handler=_undo_last,
))


# ── Record and replay ────────────────────────────────────────────────────────

def _record_workflow(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        action = (args.get("action") or "start").strip().lower()

        if action == "start":
            active.start_recording()
            return _ok(f"recording actions on {active.grant.label}",
                       "Recording. Everything clicked, typed, scrolled or "
                       "pressed from now on becomes a step. Call this again "
                       "with action 'save' and a name to finish.")

        if action != "save":
            return _fail("action must be 'start' or 'save'")

        name = (args.get("name") or "").strip()
        if not name:
            return _fail("a workflow needs a name to be saved under")
        steps = active.stop_recording()
        if not steps:
            return _fail(
                "Nothing was recorded, so there is no workflow to save. Start "
                "recording BEFORE doing the actions that should be replayable.")

        doc = workflows.document(name, active.grant.handle,
                                 active.grant.label, steps)
        stored = assets.ingest_bytes(
            workflows.to_bytes(doc), f"{name}.workflow.json",
            source="tool_output", conversation_id=ctx.conversation_id,
            turn_id=ctx.turn_id)
        return _ok(f"saved workflow {name!r} ({len(steps)} steps)",
                   workflows.describe(doc) + f"\n\nAsset id: {stored['id']}. "
                   "Replay it with replay_workflow.",
                   result_ref=stored["id"])
    return _guard(run)


register(ToolSpec(
    name="record_workflow",
    description=("Start recording what you do to a controlled window, then "
                 "save it as a replayable workflow. Steps are recorded by "
                 "what they act on, so a replay works on a window that has "
                 "moved or been reopened."),
    parameters={
        **_window_argument(),
        "action": {"type": "string", "required": True,
                   "description": "'start' to begin recording, 'save' to finish."},
        "name": {"type": "string", "required": False,
                 "description": "What to call the workflow. Required to save."},
    },
    danger=LOW,
    persistent=True,
    handler=_record_workflow,
))


def _replay_workflow(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        active = _session(ctx, args)
        asset_id = (args.get("workflow") or "").strip()
        if not asset_id:
            return _fail("which workflow? Pass the asset id record_workflow returned.")

        doc = workflows.parse(_asset_bytes(asset_id))
        steps = doc.get("steps") or []
        if not steps:
            return _fail(f"workflow {doc.get('name')!r} has no steps in it")

        done: list[str] = []
        for index, step in enumerate(steps, 1):
            # Re-read between every step. A recording is not a macro played
            # into the void: each step resolves against what is on screen at
            # that moment, which is what lets it notice the thing it wanted is
            # gone rather than clicking where it used to be.
            snapshot = active.read_tree()
            outcome = _replay_step(active, snapshot, step)
            if outcome is None:
                selector = step.get("selector") or {}
                return _fail(
                    f"Replay stopped at step {index} of {len(steps)}: could "
                    f"not find {selector.get('role', 'the element')} "
                    f"{selector.get('name', '')!r} in "
                    f"{active.grant.label}.\n"
                    + (f"Completed first: {'; '.join(done)}.\n" if done else "")
                    + "The window is not in the state this workflow expects. "
                      "It stops here rather than running the rest against a "
                      "state its earlier steps never established.")
            done.append(outcome)

        return _ok(f"replayed {doc.get('name')!r} — {len(done)} steps",
                   "\n".join(f"{i}. {d}" for i, d in enumerate(done, 1)))
    return _guard(run)


def _replay_step(active: sessions.Session, snapshot: tree.Snapshot,
                 step: dict) -> "str | None":
    """Run one recorded step, or return None if it cannot be resolved."""
    kind = step.get("kind")
    arguments = step.get("arguments") or {}
    selector = step.get("selector")

    if selector:
        element = tree.resolve_selector(snapshot, selector)
        if element is None:
            return None
        if kind == "click":
            return active.act("click", f"replay: click {element.name or element.role}",
                              lambda: actions.invoke(element),
                              route=actions.ROUTE_PATTERN)
        if kind == "type":
            text = arguments.get("text", "")
            if arguments.get("append"):
                text = (element.value or "") + text
            return active.act("type", f"replay: type into {element.name or element.role}",
                              lambda: actions.set_value(element, text),
                              route=actions.ROUTE_PATTERN)
        return None

    hwnd = active.target.hwnd
    if kind == "click":
        x, y = int(arguments.get("x", 0)), int(arguments.get("y", 0))
        return active.act("click", f"replay: click at ({x}, {y})",
                          lambda: actions.click_point(
                              hwnd, x, y,
                              button=arguments.get("button", "left"),
                              double=_truthy(arguments.get("double"))),
                          route=actions.ROUTE_MESSAGE)
    if kind == "scroll":
        left, top, right, bottom = active.target.bounds
        x, y = (right - left) // 2, (bottom - top) // 2
        clicks = int(arguments.get("clicks", -3))
        return active.act("scroll", "replay: scroll",
                          lambda: actions.scroll(hwnd, x, y, clicks=clicks),
                          route=actions.ROUTE_MESSAGE)
    if kind == "keys":
        raw = arguments.get("keys", "")
        keys = [k for k in raw.replace("-", "+").split("+") if k.strip()]
        return active.act("keys", f"replay: press {raw}",
                          lambda: actions.press_keys(active.target, keys),
                          route=actions.ROUTE_ATTACHED)
    return None


register(ToolSpec(
    name="replay_workflow",
    description=("Run a saved workflow against a controlled window. It "
                 "re-reads the window between steps and stops at the first "
                 "step it cannot resolve."),
    parameters={
        **_window_argument(),
        "workflow": {"type": "string", "required": True,
                     "description": "The asset id of a saved workflow."},
    },
    danger=LOW,
    handler=_replay_workflow,
))


# ── Ending ───────────────────────────────────────────────────────────────────

def _end_control(args: dict, ctx: ToolContext) -> dict:
    def run() -> dict:
        handle = (args.get("window") or "").strip()
        # `all` arrives as a real bool from a native tool call and as a string
        # from the emulated protocol, where a model writes JSON by hand. The
        # first version called `.strip()` on whatever came in and raised
        # AttributeError on `True` — so releasing every window, the one call
        # that matters most when something has gone wrong, was the call that
        # crashed.
        if _truthy(args.get("all")):
            closed = sessions.close_all(args.get("reason") or "finished",
                                        conversation_id=ctx.conversation_id)
            return _ok(f"released {closed} window(s)")

        summary = sessions.close_session(
            ctx.conversation_id, handle or None, args.get("reason") or "finished")
        if summary is None:
            return _ok("no window was under control")
        return _ok(f"released {summary['window']} after "
                   f"{summary['actions']} actions")
    return _guard(run)


register(ToolSpec(
    name="end_control",
    description=("Release a controlled window. Do this as soon as the task is "
                 "done — a session the user forgot about is authority nobody "
                 "is watching."),
    parameters={
        **_window_argument(),
        "all": {"type": "boolean", "required": False,
                "description": "Release every controlled window."},
        "reason": {"type": "string", "required": False,
                   "description": "Why the session is ending."},
    },
    danger=LOW,
    handler=_end_control,
))
