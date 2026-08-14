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
MAX_TOOL_STEPS = 8


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


def system_prompt(*, incognito: bool = False) -> str:
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
        "Writing files:\n"
        "- Write to the CURRENT directory with a plain relative filename, e.g. "
        '`open("report.pdf", "wb")`.\n'
        "- The sandbox is Windows. `/tmp` does not exist — do not use it, and do "
        "not use absolute paths.\n"
        "- Anything you write is captured automatically and shown to the user as a "
        "downloadable file. Do not tell them a filesystem path; just name the file.\n\n"
        "Available tools:\n" + describe_for_prompt(exclude_persistent=incognito)
    )

    # One line per skill instead of the whole instruction. Everything in this
    # string is charged to every turn forever, so a capability that matters to
    # one question in twenty does not belong in it (§5 token economics).
    catalogue = skills.index()
    if catalogue:
        prompt += "\n\n" + catalogue
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
    value = tail[:end]
    for encoded, decoded in (("\\n", "\n"), ("\\t", "\t"), ('\\"', '"'),
                             ("\\'", "'"), ("\\\\", "\\")):
        value = value.replace(encoded, decoded)
    return value.strip() or None


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
        return _error(name, "unknown_tool", f"There is no tool called {name!r}.")

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
        detail = spec.manifest.describe() if spec.manifest else spec.description
        choice = broker.request(
            # `id(arguments)` was a memory address, and CPython reuses one as
            # soon as the previous dict is collected — so two questions in one
            # turn could share an id, and answering one would answer the other.
            request_id=new_id("perm"),
            action=name,
            detail=f"{spec.description}\n\n{detail}\n\n{_preview(arguments)}",
            turn_id=ctx.turn_id, conversation_id=ctx.conversation_id,
            reusable=_reusable(spec), should_cancel=ctx.should_cancel,
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
    if result.get("result_ref"):
        lines.append(f'Full output stored as asset {result["result_ref"]}.')
    output = (result.get("output") or "").strip()
    if output:
        lines.append("Output:\n" + output)
    return "\n".join(lines)
