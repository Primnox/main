"""Tool runtime — the Capability Layer's execution half (ARCH §5.3–§5.6).

The model never executes anything. It *proposes* an action; this module
validates it, obtains permission, runs it through the owning service, and feeds
back a typed record.

Emulation is the universal path. A model with native tool calling gains nothing
in behaviour from using it — only a slightly shorter prompt — so every model
goes through the same delimited grammar and the conversation's structure is
identical regardless of provider. That is what makes model hot-swap real rather
than aspirational.

The grammar is delimited rather than bare JSON because weak models prefix
prose, and prose-prefixing breaks any contract that expects the whole reply to
be a JSON document.
"""
from __future__ import annotations

import json
import re

from ..chat import turns
from ..ids import new_id
from ..kernel.events import bus
from ..skills import loader as skills
from ..sandbox import permissions as sandbox_permissions
from . import builtins  # noqa: F401  — registers the builtin tools on import

# Computer Use registers its tools the same way, but conditionally: it is the
# one subsystem with hard third-party dependencies (pywin32, uiautomation,
# Pillow) and no meaning off Windows. A missing dependency must cost the
# desktop tools and nothing else — importing this at module scope would take
# the entire tool registry down with it, so a machine without pywin32 would
# lose run_python too.
try:
    from . import computer  # noqa: F401
    COMPUTER_USE = True
    COMPUTER_USE_UNAVAILABLE = ""
except Exception as _exc:                       # pragma: no cover - platform
    COMPUTER_USE = False
    COMPUTER_USE_UNAVAILABLE = f"{type(_exc).__name__}: {_exc}"
from .permissions import ALLOW_ONCE, ALLOW_TURN, DENY, broker
from .registry import HIGH, LOW, ToolContext, describe_for_prompt, get, tool_names

_TOOL_BLOCK = re.compile(r'<tool\s+name="([^"]+)"\s*>(.*?)</tool>', re.S)
_PLAN_BLOCK = re.compile(r"<plan>\s*(.*?)\s*</plan>", re.S)
_FENCE = re.compile(r"^```[a-zA-Z0-9_+-]*\s*\n?(.*?)\n?```$", re.S)


# Two shapes a model reaches for instead of the canonical block, measured
# rather than guessed. Against qwen2.5:7b the canonical grammar scored 0/5 —
# and every one of those five failures named the right tool and carried
# perfectly valid JSON. The model was calling the tool correctly and being
# refused over its punctuation.
#
# Both alternatives are anchored to a *registered* tool name. That is what
# keeps this from turning into "any bracketed thing is a tool call": prose
# cannot accidentally match, because the name has to be one the runtime
# actually has.
def _variant_patterns() -> list[re.Pattern]:
    global _VARIANTS
    names = tool_names()
    if _VARIANTS is None or names != _VARIANT_NAMES:
        alternation = "|".join(re.escape(n) for n in names)
        _VARIANTS = [
            # <run_python>{…}</run_python> — the tag named after the tool.
            re.compile(rf"<({alternation})\s*>\s*(\{{.*?\}})\s*</\1\s*>", re.S),
            # run_python({…}) — function-call syntax.
            re.compile(rf"\b({alternation})\s*\(\s*(\{{.*?\}})\s*\)", re.S),
        ]
        _VARIANT_NAMES[:] = names
    return _VARIANTS


_VARIANTS: list[re.Pattern] | None = None
_VARIANT_NAMES: list[str] = []

# A model that emits tool blocks forever is a loop, not a conversation.
def max_tool_steps() -> int:
    from ..settings import tunables
    return tunables.get("tools.max_steps")


MAX_TOOL_STEPS = 8   # default; the live value comes from max_tool_steps()


class StreamFilter:
    """Keeps protocol markup out of the user-visible token stream.

    Tokens arrive a few characters at a time, so a block's opening tag can be
    split across chunks. This holds back any tail that might still turn into
    `<tool` or `<plan` and releases it once it provably cannot — which is why
    the user never sees a half-written `<to` flash by before it is suppressed.

    The raw text is accumulated separately by the caller; this only decides
    what is *shown*.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._closing: str | None = None

        # The variant call shapes have to be suppressed here too, or the user
        # watches `run_python({"code": …})` type itself out before the runtime
        # quietly runs it. `})` closes the function form rather than `)`,
        # because the JSON argument routinely contains a `)` of its own —
        # `print(137 * 449)` would otherwise close the block early and leak the
        # tail.
        # The opener includes the `({` rather than just `(`, so a reply that
        # merely *mentions* `run_python(...)` in prose is not swallowed up to
        # the next `})` that may never arrive — which would eat the rest of
        # the answer.
        self._CLOSE = {"<tool": "</tool>", "<plan": "</plan>"}
        for name in tool_names():
            self._CLOSE[f"<{name}>"] = f"</{name}>"
            self._CLOSE[f"{name}({{"] = "})"
        self._OPEN = tuple(self._CLOSE)
        self._MAX_PARTIAL = max(len(o) for o in self._OPEN) - 1

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        out: list[str] = []
        while self._buf:
            if self._closing:
                i = self._buf.find(self._closing)
                if i == -1:
                    return "".join(out)
                self._buf = self._buf[i + len(self._closing):]
                self._closing = None
                continue

            hits = [(self._buf.find(o), o) for o in self._OPEN]
            hits = [(i, o) for i, o in hits if i != -1]
            if hits:
                i, opener = min(hits)
                out.append(self._buf[:i])
                self._buf = self._buf[i + len(opener):]
                self._closing = self._CLOSE[opener]
                continue

            keep = self._partial_tail()
            if keep:
                out.append(self._buf[:-keep])
                self._buf = self._buf[-keep:]
            else:
                out.append(self._buf)
                self._buf = ""
            return "".join(out)
        return "".join(out)

    def _partial_tail(self) -> int:
        """Length of the trailing text that could still become an opener."""
        for n in range(min(self._MAX_PARTIAL, len(self._buf)), 0, -1):
            if any(o.startswith(self._buf[-n:]) for o in self._OPEN):
                return n
        return 0

    def flush(self) -> str:
        """Whatever is left, unless it is inside an unterminated block.

        An unterminated block is protocol junk rather than prose, and showing
        it would leak markup at the exact moment the model misbehaved.
        """
        out = "" if self._closing else self._buf
        self._buf = ""
        return out


def _focus(conversation_id: "str | None") -> "str | None":
    """What this turn is about, insofar as the runtime can tell.

    One signal, and it is a strong one: a control session is open, which means
    the user has already approved driving a specific window and the work in
    front of the model is that window. Nothing else in this codebase is that
    unambiguous about intent, which is why this narrows on a live session
    rather than on guessing from the user's words.

    Deliberately conservative in the other direction too. With no session
    open, nothing is narrowed — a request that is ABOUT the desktop but has
    not opened a session yet still needs to see `list_windows` alongside
    everything else, because that is exactly the turn where the model is
    deciding which family of work it is in.
    """
    if not conversation_id or not COMPUTER_USE:
        return None
    try:
        from ..computer import session as sessions
        return "desktop" if sessions.live(conversation_id) else None
    except Exception:                                    # pragma: no cover
        return None


def system_prompt(*, incognito: bool = False,
                  conversation_id: "str | None" = None) -> str:
    """The grammar injected for every model (ARCH §5.3).

    The sandbox's library list is included because a model that does not know
    `reportlab` is installed will tell the user it cannot make a PDF and hand
    back HTML instead — a capability gap caused entirely by missing
    information. Probing is cached, so this costs nothing per turn.
    """
    prompt = (
        "You can use tools. To call one, reply with exactly this block and nothing else:\n\n"
        '<tool name="TOOL_NAME">\n{"argument": "value"}\n</tool>\n\n'
        "For run_python and run_shell, put the code straight in the block with "
        "NO JSON and no escaping — this is the reliable form for anything "
        "longer than one line:\n\n"
        '<tool name="run_python">\n```python\n'
        'print("quotes, \'apostrophes\' and newlines are all fine here")\n'
        "```\n</tool>\n\n"
        "Other tools take a JSON object:\n\n"
        '<tool name="create_workspace">\n'
        '{"kind": "python", "title": "Demo", "files": {"main.py": "print(1)"}}\n'
        "</tool>\n\n"
        "The wrapper is literally `<tool name=\"...\">`. These do NOT work and "
        "will be ignored: `run_python({...})`, `<run_python>...</run_python>`, "
        "`run_python{...}`.\n\n"
        "Rules:\n"
        "- One tool call per reply. Wait for the result before calling another.\n"
        "- The JSON must be valid and on its own lines.\n"
        "- Always close the block with </tool>. An unclosed block is discarded.\n"
        "- Code is a script, not a REPL. Nothing is shown unless you print() it.\n"
        "- Never state a computed result you have not seen in the output.\n"
        "- If you do not need a tool, just answer normally.\n"
        "- You may plan first with a <plan>…</plan> block before a tool call.\n"
        "\n"
        # Aimed at the specific ways a small model goes wrong here, and kept to
        # four lines because every one is charged to every turn forever. Each is
        # a failure that has an observable signature — a fabricated id, a claim
        # with no tool call behind it — rather than general advice to be careful.
        "Do not invent:\n"
        "- Tool names, file names, asset ids, or paths. Use only ones that "
        "appeared in a result you were given. If you need one and do not have "
        "it, call a tool to find it.\n"
        "- Facts about the user. What you know about them is in the context "
        "above; anything else you must ask or leave out.\n"
        "- Work you did not do. Only say you ran, saved, read or created "
        "something if a tool result above shows it. If a tool failed, say so.\n"
        "- An answer to something ambiguous. Call `ask_user` with the real "
        "alternatives instead of picking one — a guess you write down is "
        "indistinguishable from an instruction, and cannot be checked later.\n"
        "\n"
        "Writing files:\n"
        "- Write to the CURRENT directory with a plain relative filename, e.g. "
        '`open("report.pdf", "wb")`.\n'
        "- The sandbox is Windows. `/tmp` does not exist — do not use it, and do "
        "not use absolute paths.\n"
        "- Anything you write is captured automatically and shown to the user as a "
        "downloadable file. Do not tell them a filesystem path; just name the file.\n\n"
        "Available tools:\n" + describe_for_prompt(
            exclude_persistent=incognito, focus=_focus(conversation_id))
    )

    # The desktop tools get a shape as well as a description, and only they do.
    # Everything else here is one call: run this, remember that. Driving a
    # window is three calls in a fixed order, and the order is not guessable
    # from the descriptions \u2014 measured on qwen2.5:0.5b, which without this
    # produced a tool call for 2 of 5 plain desktop requests, named the right
    # tool in prose instead of calling it, filled `list_windows` with a junk
    # query, and answered "take control of window X" with a code workspace.
    # With these lines: 5 of 5, correct tool, no invented arguments.
    #
    # Written as calls with no results, which is the part that took two
    # attempts. A version showing a worked exchange WITH plausible results
    # taught the sequence and was worse overall: the 0.5B recited the
    # example's window back as a real answer. A fabricated window reported
    # confidently is precisely what the four "Do not invent" lines above exist
    # to prevent, so an example that manufactures one pays for the form it
    # teaches with the failure it causes.
    def observed_rule() -> str:
        from ..computer import observed as _observed
        return _observed.SYSTEM_RULE

    if COMPUTER_USE:
        prompt += (
            "\n\nUsing the desktop takes three calls, always in this order:\n"
            '  <tool name="list_windows">{}</tool>\n'
            '  <tool name="control_window">'
            '{"window": "<a handle from list_windows>", "reason": "<why>"}</tool>\n'
            '  <tool name="type_into">'
            '{"ref": "<a ref from the result>", "text": "<what to type>"}</tool>\n'
            "Never invent a window handle or a ref; both only ever come from a "
            "result you were given. Leave optional arguments out unless you "
            "need them.\n"
            # Two extra lines, and they are worth their tokens because each
            # replaces a LOOP. Without run_steps a known plan costs one model
            # call per step; without wait_for, waiting costs one call and one
            # whole tree per check, and the answer is "not yet" every time.
            #
            # Deliberately placed after the three-call sequence rather than
            # inside it: the sequence is what a small model imitates, and
            # putting a four-step JSON array in front of a 0.5B before it has
            # learned the basic shape is how it starts emitting arrays instead
            # of tool calls.
            "When you already know every step, send them together instead of "
            "one at a time:\n"
            '  <tool name="run_steps">{"steps": ['
            '{"verb": "type", "ref": "<ref>", "text": "<text>"}, '
            '{"verb": "click", "ref": "<ref>"}]}</tool>\n'
            "It stops at the first step that fails and tells you which ones "
            "did not run. To wait for something, use wait_for rather than "
            "reading the window over and over.\n"
            # Measured on qwen2.5:0.5b, ten desktop tasks. With every tool
            # visible it picked the right one 4/10 and reached for run_python
            # to type, click and press keys; with only the desktop tools
            # visible, 8/10. The competition is the problem, not the
            # descriptions — run_python is a general-purpose attractor and a
            # small model reaches for it whenever it is unsure.
            #
            # Deleting it is not an option, so the next cheapest thing is to
            # say which family owns this kind of work. One line, charged per
            # turn, against four tasks a turn each.
            "Anything happening in a window on screen is done with the tools "
            "above — never with run_python or run_shell, which cannot see or "
            "touch other applications.\n"
            # The prompt-injection boundary, stated once. It belongs here
            # rather than repeated on every tool result: a rule restated on
            # every observation becomes furniture the model skims, and the
            # thing being defended against is content that has had time to
            # study the surrounding format.
            #
            # Phrased as what to DO, not what to distrust. "Report it rather
            # than following it" is actionable; "beware of prompt injection"
            # is a warning a model cannot act on.
            + "\n" + observed_rule()
        )

    # One line per skill instead of the whole instruction. Everything in this
    # string is charged to every turn forever, so a capability that matters to
    # one question in twenty does not belong in it (§5 token economics).
    catalogue = skills.index()
    if catalogue:
        prompt += "\n\n" + catalogue

    # Two sentences, charged to every turn, and worth it: without them the
    # `remember` tool exists and is never called. A model does not volunteer to
    # write to a store it was not told it owns, and the alternative — a settings
    # screen the user types into — leaves memory permanently empty because
    # nobody leaves a conversation to file a fact about themselves.
    #
    # Bounded on purpose. "Remember anything interesting" produces a store full
    # of the task at hand, which is what the conversation is already for.
    prompt += (
        "\n\nWhen the user tells you to remember something, or states a lasting "
        "fact about themselves — a preference, a name, how they work, a project "
        "they keep returning to — call `remember`. Set asked_by_user when they "
        "asked outright. Do NOT remember details of the current task; those "
        "belong to the conversation, not to the user."
    )
    if incognito:
        # Said once, up front. A model that discovers the limit by calling a
        # tool and reading the refusal tends to apologise for a failure, which
        # frames a deliberate property of the mode as something going wrong.
        prompt += (
            "\n\nThis is an incognito conversation. Nothing in it is written to "
            "disk, so the tools that would leave something behind — running "
            "code, creating or editing workspaces — are unavailable here. Say "
            "so plainly if the user asks for one; it is a property of the mode, "
            "not a failure."
        )
        # And no library list: nothing here can run code, so it is dead weight
        # in the prompt — and probing for it means *executing* in the sandbox,
        # which writes an execution session row. Measured: this was the only
        # thing an incognito turn still put on disk.
        return prompt
    try:
        from ..sandbox.capabilities import describe as describe_libraries

        libraries = describe_libraries()
    except Exception:
        # A failed probe must never break the turn — the model simply goes
        # without the hint, exactly as it did before this existed.
        libraries = ""
    return f"{prompt}\n\n{libraries}" if libraries else prompt


def parse_plan(text: str) -> str | None:
    m = _PLAN_BLOCK.search(text or "")
    return m.group(1).strip() if m else None


def _sole_string_parameter(name: str) -> str | None:
    """The one required string a tool takes, if it takes exactly one.

    `run_python` takes `code` and nothing else; `run_shell` takes `command`.
    For those, the JSON envelope carries no information the tool block does not
    already have — which is what makes a raw body safe to accept.
    """
    spec = get(name)
    if spec is None:
        return None
    required = spec.required()
    if len(required) != 1 or len(spec.parameters) != 1:
        return None
    key = required[0]
    return key if spec.parameters[key].get("type", "string") == "string" else None


def _parse_body(name: str, body: str) -> dict:
    """Turn a tool block's contents into arguments.

    JSON first. Then — for a single-string tool — the body as-is.

    This exists because JSON is a hostile envelope for source code, and source
    code is the main thing this protocol carries. Measured: asked for a PDF,
    qwen2.5:7b emitted a flawless `<tool name="run_python">` block whose payload
    was invalid JSON purely because the Python inside contained
    `strftime("%Y-%m-%d")`. The double quotes closed the JSON string. Every
    document task failed this way while `print(137*449)` — which has no quotes
    — succeeded 19 times out of 20. The grammar was not the problem; the
    escaping was.
    """
    body = body.strip()
    # An empty body means "no arguments", which is a correct call for every
    # tool whose parameters are all optional — and it is what models actually
    # write. Measured: qwen2.5:7b opens a desktop task with
    # `<tool name="list_windows"></tool>`, omitting the braces the grammar
    # shows, and that was being reported as "not a JSON object" and spent as a
    # malformed-call correction. The turn could then end having executed
    # nothing at all.
    #
    # Treating it as `{}` does not weaken anything: a tool that genuinely needs
    # an argument still fails validation downstream, and fails with a sentence
    # naming the argument rather than a complaint about punctuation.
    if not body:
        return {"name": name, "arguments": {}}
    if body.startswith("{"):
        try:
            return {"name": name, "arguments": json.loads(body)}
        except json.JSONDecodeError as exc:
            malformed = f"{exc}"
        else:  # pragma: no cover - unreachable, json either raises or returns
            malformed = ""
    else:
        malformed = "not a JSON object"

    key = _sole_string_parameter(name)
    if key:
        fenced = _FENCE.match(body)
        raw = (fenced.group(1) if fenced else body).strip()
        # A body that is a broken JSON wrapper around the real payload is worth
        # unwrapping rather than running: `{"code": "print(1)"` is not code.
        if raw and not raw.startswith("{"):
            return {"name": name, "arguments": {key: raw}}
        salvaged = _salvage_single_value(raw, key)
        if salvaged is not None:
            return {"name": name, "arguments": {key: salvaged}}

    return {"name": name, "arguments": {}, "malformed": malformed}


def _salvage_single_value(body: str, key: str) -> str | None:
    """Recover the value from `{"code": "…"}` whose quoting is broken.

    Only attempted for a tool with one string argument, and only when the shape
    is unambiguous: everything between the opening quote of the value and the
    last quote before the closing brace. Escapes are decoded the way JSON would
    have, so the code arrives as the model meant to write it.
    """
    opener = re.search(rf'"{re.escape(key)}"\s*:\s*"', body)
    if not opener:
        return None
    tail = body[opener.end():]
    end = tail.rfind('"')
    if end <= 0:
        return None
    return _decode_escapes(tail[:end]).strip() or None


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}


def _decode_escapes(value: str) -> str:
    """Decode JSON-style escapes in ONE left-to-right pass.

    Sequential `str.replace` calls cannot do this correctly, because each pass
    reads the output of the last. The old loop decoded `\\n` first and `\\\\`
    last, so a Windows path — the single most likely thing to carry backslashes
    in generated code — came out mangled:

        open("C:\\\\temp\\\\x.txt")

    contains the substring `\\t`, so the tab pass fired inside what was really
    an escaped backslash followed by a `t`, and the code reached the sandbox
    with a literal TAB where a path separator belonged. Scanning once and
    consuming both characters of each escape together makes the order
    irrelevant, which is the only way this is order-independent.

    An unknown escape is left verbatim rather than dropped: `\\d` in a regex is
    `\\d`, and silently eating the backslash would turn a working pattern into
    one that matches the letter d.
    """
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            out.append(ch)          # unknown escape — keep the backslash
            out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_call(text: str) -> dict | None:
    """Find the first tool call. Malformed JSON is reported, not swallowed.

    Canonical form first, then the shapes models actually produce. Being strict
    about what we emit and liberal about what we accept costs nothing here: the
    tool name and its arguments are the whole content of a call, and both are
    unambiguous in every form matched.
    """
    text = text or ""
    matches = [m for m in (_TOOL_BLOCK.search(text),) if m]
    if not matches:
        matches = [m for m in (p.search(text) for p in _variant_patterns()) if m]
    if not matches:
        return None

    m = min(matches, key=lambda m: m.start())
    return _parse_body(m.group(1), m.group(2))


def visible_text(text: str) -> str:
    """Strip machinery so the user sees prose, not protocol."""
    without = _TOOL_BLOCK.sub("", text or "")
    for pattern in _variant_patterns():
        without = pattern.sub("", without)
    without = _PLAN_BLOCK.sub("", without)
    return without.strip()


def needs_permission(spec) -> bool:
    """Anything that runs code or reaches beyond the database asks first."""
    return spec.danger != LOW or spec.manifest is not None


def _reusable(spec) -> bool:
    if spec.danger == HIGH or spec.manifest is None:
        return False
    return sandbox_permissions.is_reusable(spec.manifest)


def execute(name: str, arguments: dict, ctx: ToolContext) -> dict:
    """Validate → ask → run → report. Returns a structured tool_result."""
    spec = get(name)
    if spec is None:
        # Name the real tools, and the nearest miss first.
        #
        # "There is no tool called 'search_web'" tells a small model that it was
        # wrong and nothing about what would be right, so it invents a second
        # name, and a third — each retry burning a step from `tools.max_steps`
        # until the turn ends with no work done. A 7B does not reliably hold the
        # tool list across a long context; restating it at the exact moment it
        # is needed costs a few tokens and converts a loop into one correction.
        import difflib
        real = sorted(tool_names())
        near = difflib.get_close_matches(name, real, n=3, cutoff=0.6)
        hint = f" Did you mean {', '.join(repr(n) for n in near)}?" if near else ""
        return _error(name, "unknown_tool",
                      f"There is no tool called {name!r}.{hint} "
                      f"The tools that exist are: {', '.join(real)}. "
                      f"Use one of these or answer without a tool — do not "
                      f"invent another name.")

    errors = spec.validate(arguments)
    if errors:
        # Reported back to the model as a correctable result rather than a
        # failure, so it can fix the call instead of the turn dying.
        return _error(name, "invalid_arguments", "; ".join(errors))

    if ctx.should_cancel():
        return _error(name, "cancelled", "Cancelled before the tool ran.")

    # CRS §11.2.4 — anything an incognito turn creates must be ephemeral or
    # explicitly promoted. Executions write a session row and their logs;
    # workspaces write rows and versions; all of them hold a foreign key to a
    # turn that has no row. Refusing is the honest position until they can be
    # made genuinely ephemeral — quietly persisting them would break the one
    # promise the mode makes.
    if spec.persistent and turns.is_incognito(ctx.conversation_id):
        return _error(
            name, "unavailable_in_incognito",
            f"{name} is unavailable in an incognito chat, because it would "
            "write to disk and an incognito conversation writes nothing. Tell "
            "the user that plainly — this is a deliberate limit of the mode, "
            "not a fault — and answer without it if you can.",
        )

    if needs_permission(spec):
        if spec.prompt is not None:
            try:
                detail = spec.prompt(arguments)
            except Exception as exc:
                # A prompt that cannot be rendered must not become an
                # unexplained approval. Falling back to the generic text is
                # worse than saying why it is generic.
                detail = (f"{spec.description}\n\n(Could not describe this "
                          f"request in detail: {type(exc).__name__}.)")
        else:
            detail = spec.manifest.describe() if spec.manifest else spec.description
        choice = broker.request(
            # `id(arguments)` was a memory address, and CPython reuses one as
            # soon as the previous dict is collected — so two questions in one
            # turn could share an id, and answering one would answer the other.
            request_id=new_id("perm"),
            action=name,
            # A bespoke prompt stands alone. Appending the description and the
            # raw arguments to it would bury the sentence that was written to
            # be read under the boilerplate it was written to replace.
            detail=(detail if spec.prompt is not None else
                    f"{spec.description}\n\n{detail}\n\n{_preview(arguments)}"),
            turn_id=ctx.turn_id, conversation_id=ctx.conversation_id,
            reusable=_reusable(spec), should_cancel=ctx.should_cancel,
            always_ask=spec.always_ask,
        )
        if choice == DENY:
            # Worded for the model, which is the only reader of this string.
            # "You declined this action." was read as the tool being broken,
            # and the reply told the user the sandbox was unavailable — which
            # was false, and blamed the machine for the user's own choice.
            return _error(
                name, "permission_denied",
                f"The user declined permission to run {name}. The tool works "
                "and is available; they chose not to allow this particular "
                "call. Do not retry it. Continue without it, and do not tell "
                "the user the tool is unavailable.",
            )

    if ctx.conversation_id:
        bus.emit("tool.call", {"job_id": ctx.job_id, "name": name, "arguments": arguments},
                 conversation_id=ctx.conversation_id, turn_id=ctx.turn_id)

    try:
        result = spec.handler(arguments, ctx)
    except Exception as exc:
        result = {"status": "error", "summary": f"{type(exc).__name__}: {exc}", "output": ""}

    payload = {
        "job_id": ctx.job_id, "name": name,
        "status": result.get("status", "success"),
        "summary": result.get("summary", ""),
    }
    for key in ("result_ref", "workspace_id", "execution_id", "changes"):
        if result.get(key):
            payload[key] = result[key]
    if ctx.conversation_id:
        bus.emit("tool.result", payload, conversation_id=ctx.conversation_id, turn_id=ctx.turn_id)

    return {"type": "tool_result", "tool": name, **result}


def _preview(arguments: dict) -> str:
    """What the user actually reads before approving."""
    for key in ("code", "command"):
        if key in arguments:
            body = str(arguments[key])
            return body if len(body) <= 1500 else body[:1500] + "\n…"
    return json.dumps(arguments)[:800]


def _error(name: str, code: str, message: str) -> dict:
    return {"type": "tool_result", "tool": name, "status": "error",
            "code": code, "summary": message, "output": ""}


def format_result(result: dict) -> str:
    """Structured continuation (ARCH §5.5) — a typed record, not a log dump.

    The model is told what happened in one line, then given the output. Dumping
    a raw terminal transcript is what makes weaker models start narrating shell
    prompts back at the user.
    """
    status = result.get("status", "success")
    lines = [
        f'Tool {result.get("tool")} {"completed successfully" if status == "success" else "failed"}.',
        f'Summary: {result.get("summary", "")}',
    ]
    if status != "success":
        # Measured: after a failing run the model wrote "let's correct this and
        # try again" followed by a fenced code block in ordinary prose. Prose
        # is not executed — deliberately, since a model showing the user a
        # snippet must not have it run — so the turn ended having produced
        # nothing. It has to be told how to actually retry.
        lines.append(
            f'To retry, send another <tool name="{result.get("tool")}"> block. '
            "A code fence written in your reply is shown to the user, not run.")
    else:
        # The success path used to say nothing about what happens next, and
        # the asymmetry was doing real damage: a model got told how to
        # continue only when something went WRONG.
        #
        # Measured on qwen2.5:0.5b across ten desktop tasks, one tool result
        # already in the conversation: it emitted a tool call for 1 of 10, and
        # the other nine were fabricated outcomes — "I have successfully
        # controlled the Notepad window", "The user typed hello into the text
        # field". None of it had happened. The model was not failing to choose
        # a tool; it had pattern-matched the previous message (a success
        # report) and concluded its own job was to write another one.
        #
        # Both sentences are load-bearing. The first says a turn can continue,
        # which is the part the shape of the conversation was arguing against.
        # The second names the specific failure, because "be accurate" is not
        # something a 0.5B can act on and "do not report a result you were not
        # given" is.
        lines.append(
            "If the task needs another step, send the next <tool ...> block "
            "now. Do not write a result you were not given: only the Summary "
            "above actually happened.")
    if result.get("result_ref"):
        lines.append(f'Full output stored as asset {result["result_ref"]}.')
    output = (result.get("output") or "").strip()
    if output:
        lines.append("Output:\n" + output)
    return "\n".join(lines)
