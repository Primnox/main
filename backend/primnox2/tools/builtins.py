"""The builtin tool set.

None of these execute anything themselves. Code-running tools hand a manifest
to the Sandbox Manager and receive a result — that separation is why the
sandbox is a kernel service rather than a helper living in here.

Permission is NOT requested in this module. `runtime.execute` gates every call
before a handler runs, so a tool cannot forget to ask.
"""
from __future__ import annotations

import json
import re

from ..assets import service as assets
from ..knowledge import graph as knowledge, live as live_graph
from ..sandbox import manager, permissions as sandbox_permissions
from ..workspaces import service as workspaces
from .registry import HIGH, LOW, MEDIUM, ToolContext, ToolSpec, register

# What the model is shown inline. The full output is stored as an asset and
# referenced (CRS §6.2.4) — a 200k-line log must not enter the context window.
def _inline_chars() -> int:
    from ..settings import tunables
    return tunables.get("tools.inline_output_chars")


INLINE_OUTPUT_CHARS = 2000   # default; the live value comes from _inline_chars()


def _store_output(text: str, name: str, ctx: ToolContext) -> str | None:
    """Promote large output to an asset and return its id."""
    if len(text) <= _inline_chars():
        return None
    try:
        asset = assets.ingest_bytes(
            text.encode("utf-8", "replace"), name,
            source="tool_output", conversation_id=ctx.conversation_id,
            turn_id=ctx.turn_id,
        )
        return asset["id"]
    except Exception:
        # Losing the archive copy must not fail a tool that already ran.
        return None


def _clip(text: str) -> str:
    cap = _inline_chars()
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n… {len(text) - cap} more characters, stored as an asset …"


def _execute_code(runtime: str, code: str, ctx: ToolContext, tier: str) -> dict:
    manifest = sandbox_permissions.manifest_for(runtime, tier)
    result = manager.execute(
        code=code, runtime=runtime, manifest=manifest,
        job_id=ctx.job_id, turn_id=ctx.turn_id, conversation_id=ctx.conversation_id,
        should_cancel=ctx.should_cancel,
    )

    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    combined = (stdout + ("\n" + stderr if stderr else "")).strip()
    ref = _store_output(combined, f"{runtime}-output.txt", ctx)
    changes = result.get("changes") or {}
    created = changes.get("created") or []

    if result["ok"]:
        summary = "ran successfully"
        if created:
            summary += f", created {', '.join(created[:5])}"
    else:
        summary = result.get("error") or f"exited with code {result.get('exit_code')}"

    # A clean exit with nothing on stdout is the most dangerous result this
    # tool can return: it reads as success, so a model fills the silence with a
    # number it made up. Measured on qwen2.5:7b — code written REPL-style
    # (`result = 137 * 449; result`) printed nothing, and the reply confidently
    # reported 61,013 for a value that is 61,513. Saying `(no output)` was not
    # enough; it has to say why, and what to do instead.
    output = _clip(combined) or "(no output)"
    if result["ok"] and not combined:
        summary = "ran, but printed nothing"
        output = (
            "The code ran and exited cleanly, but produced no output.\n"
            "This is a script, not a REPL: only what you pass to print() is "
            "captured, and a bare expression on the last line shows nothing.\n"
            "Run it again with print() around the value you want. Do not state "
            "a result you have not seen."
        )

    return {
        "status": "success" if result["ok"] else "error",
        "summary": summary,
        "output": output,
        "result_ref": ref,
        "execution_id": result.get("execution_id"),
        "changes": changes,
        "exit_code": result.get("exit_code"),
    }


# ── Code execution ───────────────────────────────────────────────────────────
register(ToolSpec(
    name="run_python",
    description="Execute Python code in an isolated sandbox and return its output.",
    parameters={"code": {"type": "string", "required": True,
                         "description": "The Python source to run."}},
    danger=MEDIUM,
    manifest=sandbox_permissions.manifest_for("python", sandbox_permissions.SAFE),
    persistent=True,
    handler=lambda args, ctx: _execute_code("python", args["code"], ctx, sandbox_permissions.SAFE),
))

register(ToolSpec(
    name="run_node",
    description="Execute JavaScript with Node in an isolated sandbox.",
    parameters={"code": {"type": "string", "required": True,
                         "description": "The JavaScript source to run."}},
    danger=MEDIUM,
    manifest=sandbox_permissions.manifest_for("node", sandbox_permissions.SAFE),
    persistent=True,
    handler=lambda args, ctx: _execute_code("node", args["code"], ctx, sandbox_permissions.SAFE),
))

register(ToolSpec(
    name="run_shell",
    description="Run a shell command. Use only when Python cannot do the job.",
    parameters={"command": {"type": "string", "required": True,
                            "description": "The command line to run."}},
    # Shell reaches the wider machine, so it sits in the limited tier and its
    # approval is never reusable — every invocation is asked separately.
    danger=HIGH,
    manifest=sandbox_permissions.manifest_for("shell", sandbox_permissions.LIMITED),
    persistent=True,
    handler=lambda args, ctx: _execute_code("shell", args["command"], ctx, sandbox_permissions.LIMITED),
))


# ── Assets ───────────────────────────────────────────────────────────────────
def _search_assets(args: dict, ctx: ToolContext) -> dict:
    hits = assets.search(args["query"], limit=int(args.get("limit") or 6))
    if not hits:
        return {"status": "success", "summary": "no matches", "output": "No documents matched."}
    lines = [f'[{h["original_name"]} #{h["ordinal"]}] {h["text"][:400]}' for h in hits]
    return {
        "status": "success",
        "summary": f"{len(hits)} match{'es' if len(hits) != 1 else ''}",
        "output": _clip("\n\n".join(lines)),
    }


register(ToolSpec(
    name="search_assets",
    # Five words was not enough for a small model to choose it: measured on
    # qwen2.5:0.5b, "find the invoice in my documents" called run_node.
    # Naming read_asset here was an over-correction: measured on
    # qwen2.5:0.5b, mentioning it made "find the invoice in my documents"
    # call read_asset instead. A sibling named inside a description
    # competes with the tool the description belongs to, so the boundary
    # is drawn by what the caller HAS — words, or an id — not by name.
    description=("Find documents by their words. Searches everything the "
                 "user has given you — PDFs, decks, spreadsheets. Use "
                 "this when you do not have a document id yet. It does "
                 "not search code — graph_query does."),
    parameters={
        "query": {"type": "string", "required": True, "description": "What to look for."},
        "limit": {"type": "integer", "required": False, "description": "Max results."},
    },
    danger=LOW,
    handler=_search_assets,
))


def _read_asset(args: dict, ctx: ToolContext) -> dict:
    asset = assets.get(args["asset_id"])
    if asset is None:
        return {"status": "error", "summary": "no such asset", "output": ""}
    if asset["status"] != "ready":
        # §2.6 — never proceed with empty content for an unready asset.
        return {"status": "error",
                "summary": f'asset is {asset["status"]}',
                "output": f'The document "{asset["original_name"]}" is not ready yet.'}
    text = asset.get("extracted_text") or ""
    if not text:
        why = "needs OCR" if asset["metadata"].get("ocr_required") else "no extractable text"
        return {"status": "error", "summary": why,
                "output": f'"{asset["original_name"]}" has no text ({why}).'}
    return {"status": "success", "summary": f'{len(text)} characters', "output": _clip(text)}


register(ToolSpec(
    name="read_asset",
    description="Read the extracted text of one document by its asset id.",
    parameters={"asset_id": {"type": "string", "required": True, "description": "The asset id."}},
    danger=LOW,
    handler=_read_asset,
))


# ── Memory ───────────────────────────────────────────────────────────────────
def _remember(args: dict, ctx: ToolContext) -> dict:
    """Save a durable fact about the user, from the conversation.

    This is where memory should be created. A settings screen with a textarea
    asks the user to leave the conversation, restate something they just said,
    and file it themselves — so nobody does it, and the store stays empty while
    the assistant keeps forgetting. The moment a fact is worth keeping is the
    moment it is said.

    `provenance` records who decided. A fact the user asked to be kept and a
    fact the model thought was worth keeping are different claims, and the
    Memory tab shows which is which so a wrong inference can be found and
    removed rather than quietly becoming true.
    """
    from ..memory import service as memory

    text = (args.get("text") or "").strip()
    if not text:
        return {"status": "error", "summary": "nothing to remember",
                "output": "A memory needs text."}

    # Incognito exists to leave no trace. Writing a permanent fact out of a
    # conversation that is never written to disk would be the one thing it
    # promises not to do.
    from ..chat import ephemeral
    if ephemeral.is_incognito(ctx.conversation_id):
        return {"status": "error", "summary": "incognito",
                "output": "This is an incognito chat — nothing here is saved, "
                          "including memories."}

    try:
        result = memory.remember(
            text,
            category=(args.get("category") or memory.DEFAULT_CATEGORY),
            provenance=(memory.EXPLICIT if args.get("asked_by_user")
                        else memory.INFERRED),
            conversation_id=ctx.conversation_id,
            turn_id=ctx.turn_id,
        )
    except memory.MemoryTooLong as exc:
        # Returned as a tool error, not raised: the loop feeds this back to the
        # model, which can shorten and call again. A raised exception would
        # fail the turn over a fact that only needed distilling.
        return {"status": "error", "summary": "too long to be one fact",
                "output": str(exc)}
    if not result["stored"]:
        return {"status": "success", "summary": "already known",
                "output": f"Already remembered something equivalent: {text}"}
    return {"status": "success", "summary": "saved to memory",
            "output": f"Remembered: {text}"}


register(ToolSpec(
    name="remember",
    description=("Save a lasting fact about the user — a preference, a name, a "
                 "recurring project, how they like to work. Use it when they "
                 "say to remember something, and when a durable fact about "
                 "THEM comes up. Not for facts about the task at hand."),
    parameters={
        "text": {"type": "string", "required": True,
                 "description": "ONE fact, as a single short standalone "
                                "sentence — 'Prefers concise answers.', not a "
                                "paragraph and not the message it came from. "
                                "Longer text is refused, not truncated."},
        "category": {"type": "string", "required": False,
                     "description": "personal, work, project or session."},
        "asked_by_user": {"type": "boolean", "required": False,
                          "description": "True when they explicitly asked."},
    },
    danger=LOW,
    handler=_remember,
))


def _recall_memory(args: dict, ctx: ToolContext) -> dict:
    """Search what is already known. Memory is injected into every prompt, but
    the injection is capped — this reaches past the cap for an older fact."""
    from ..memory import service as memory

    hits = memory.search(args.get("query") or "", limit=int(args.get("limit") or 10))
    if not hits:
        return {"status": "success", "summary": "nothing known",
                "output": "Nothing remembered about that."}
    return {"status": "success", "summary": f"{len(hits)} remembered",
            "output": "\n".join(f"- {h['text']}" for h in hits)}


register(ToolSpec(
    name="recall_memory",
    # Descriptions are how a model routes, and these two were described only by
    # what they hold, never by what they are FOR. Asked "what do I prefer",
    # a small model read `graph_query`'s "far cheaper than reading whole files"
    # as a recommendation and called it — getting back twenty-four lines of
    # Primnox's own source and answering the user's question from them, with
    # every appearance of having looked something up. Measured.
    #
    # Nothing was broken underneath: these are separate stores and separate
    # code paths, and `recall_memory` would have searched memories alone. The
    # model simply had no sentence telling it which question belongs where.
    # So each description now names its own subject AND points at the other
    # tool by name, because "this is for X" is weaker guidance than "this is
    # for X, that is for Y" when the choice is what's being got wrong.
    description=("THE tool for questions about the user — preferences, habits, "
                 "their setup, anything they told you before. Use it whenever "
                 "the question says 'I', 'my' or 'me'. It does not search code; "
                 "graph_query does, and cannot answer for the user."),
    parameters={
        "query": {"type": "string", "required": False,
                  "description": "What to look for. Omit for everything."},
        "limit": {"type": "integer", "required": False, "description": "Max results."},
    },
    danger=LOW,
    handler=_recall_memory,
))


# ── Knowledge graph ──────────────────────────────────────────────────────────
def _graph_query(args: dict, ctx: ToolContext) -> dict:
    """Answer from the graph rather than from the corpus.

    Returns citation lines, not source. `NODE ingest_bytes() [function
    src=primnox2/assets/service.py loc=L58]` costs a handful of tokens and tells
    the model exactly which file to read next if it needs the body — which is
    cheaper than inlining a body it may not need.
    """
    question = args["question"]
    budget = int(args.get("token_budget") or 2000)
    text = knowledge.query(
        question,
        scope=args.get("scope") or None,
        depth=min(int(args.get("depth") or 2), 4),
        token_budget=budget,
        relation=args.get("relation") or None,
    )
    if not text:
        return {"status": "success", "summary": "no matches",
                "output": "Nothing in the knowledge graph matched. "
                          "The corpus may not be indexed yet."}

    # A wrong tool that returns nothing corrects itself; the model tries again.
    # A wrong tool that returns something plausible does not — and this one
    # always returns something, because a codebase contains a line about
    # roughly any word you can put to it. Asked what the user prefers, it
    # answered out of Primnox's own source and the reply read like recall.
    #
    # The result is still handed over rather than withheld: the guess is
    # keyword-shaped and will misfire on a legitimate question ("why did I
    # write this?"), where suppressing a real answer would be the worse error.
    # It is prepended, not appended, because the note has to be read before the
    # citations it is a warning about — after two thousand tokens of graph, the
    # answer is already forming.
    if _about_the_user(question):
        text = ("NOTE: this reads indexed code and documents, and the question "
                "looks like it is about the user. Nothing below is evidence of "
                "what they said, prefer, or decided — call recall_memory for "
                "that. Use these lines only if the question really was about "
                "the code.\n\n") + text
    return {"status": "success",
            "summary": f"{len(text.splitlines())} graph lines",
            "output": text}


# Whole words only: "my" must not fire on "mypy", and "i" not on every
# identifier containing the letter. Deliberately a small, boring list — the
# note it triggers is a caveat, so a false positive costs one sentence, while
# a clever matcher that fired on prose would cost trust in the caveat itself.
_FIRST_PERSON = re.compile(
    r"\b(i|me|my|mine|myself|we|us|our|ours)\b", re.IGNORECASE)


def _about_the_user(question: str) -> bool:
    return bool(_FIRST_PERSON.search(question or ""))


register(ToolSpec(
    name="graph_query",
    description=("Search indexed CODE AND DOCUMENTS — files, symbols, how a "
                 "system works. Returns nodes and relationships with file:line "
                 "citations, far cheaper than reading whole files. It holds "
                 "nothing about the user: for what they prefer or told you "
                 "earlier, use recall_memory instead."),
    parameters={
        "question": {"type": "string", "required": True,
                     "description": "A symbol, concept, or natural-language question."},
        "depth": {"type": "integer", "required": False,
                  "description": "Hops to traverse, 1-4. Default 2."},
        "relation": {"type": "string", "required": False,
                     "description": "Filter to one relation, e.g. calls, imports, rationale_for."},
        "scope": {"type": "string", "required": False,
                  "description": "Restrict to one indexed scope."},
        "token_budget": {"type": "integer", "required": False,
                         "description": "Max tokens of output. Default 2000."},
    },
    danger=LOW,
    handler=_graph_query,
))


# ── Asking ───────────────────────────────────────────────────────────────────
def _ask_user(args: dict, ctx: ToolContext) -> dict:
    """Put a question to the user and wait for the answer.

    The alternative to asking is guessing, and a guess from a small model does
    not arrive labelled as one — it arrives as a confident sentence. Asked which
    of two databases to migrate, a 7B picks one and writes the migration.
    Nothing downstream can tell that choice apart from an instruction.

    So this is as much a correctness feature as a courtesy: it converts the most
    expensive kind of hallucination — an invented premise the whole rest of the
    answer is built on — into a question that costs one click.

    Bounded to a short list of concrete options rather than open text. A model
    that is already unsure writes vague open questions ("what would you like me
    to do?"), which move the work back to the user without narrowing anything.
    Being made to enumerate the actual alternatives is what forces the
    ambiguity to become explicit.
    """
    from ..ids import new_id
    from .permissions import (ANSWER_CANCELLED, ANSWER_TIMEOUT, ANSWER_UNCLEAR,
                              broker)

    question = (args.get("question") or "").strip()
    if not question:
        return {"status": "error", "summary": "no question",
                "output": "A question needs text."}

    raw = args.get("options") or []
    if isinstance(raw, str):                       # a model may send "a, b, c"
        raw = [p.strip() for p in raw.split(",")]
    labels = [str(o).strip() for o in raw if str(o).strip()][:4]
    if len(labels) < 2:
        return {"status": "error", "summary": "needs options",
                "output": "Give 2-4 concrete options the user can choose "
                          "between. If you cannot name the alternatives, you "
                          "do not yet know what you are asking."}

    options = [{"id": f"opt{i}", "label": l} for i, l in enumerate(labels)]
    # Always available: the user may reject the framing itself, and a question
    # with no way to say "none of these" forces a wrong answer into the record.
    options.append({"id": ANSWER_UNCLEAR, "label": "None of these"})

    choice = broker.ask(
        request_id=new_id("ask"), question=question, options=options,
        turn_id=ctx.turn_id, conversation_id=ctx.conversation_id,
        should_cancel=ctx.should_cancel,
    )

    if choice == ANSWER_CANCELLED:
        return {"status": "error", "summary": "cancelled",
                "output": "The turn was cancelled while waiting."}
    if choice == ANSWER_TIMEOUT:
        return {"status": "success", "summary": "no answer",
                "output": "Nobody answered. Proceed with your best judgement "
                          "and SAY which assumption you made."}
    if choice == ANSWER_UNCLEAR:
        return {"status": "success", "summary": "none of these",
                "output": "The user rejected all the options. Do not pick one "
                          "anyway — ask a different question or say what is "
                          "unclear."}

    picked = next((o["label"] for o in options if o["id"] == choice), None)
    if picked is None:
        return {"status": "success", "summary": "no usable answer",
                "output": "No recognisable answer came back. Proceed with your "
                          "best judgement and say what you assumed."}
    return {"status": "success", "summary": f"answered: {picked}",
            "output": f"The user chose: {picked}"}


register(ToolSpec(
    name="ask_user",
    description=("Ask the user a question when you genuinely do not know "
                 "something you need — which file they meant, which of two "
                 "readings of the request is right, whether to overwrite. "
                 "Prefer this over guessing: a guess you write down is "
                 "indistinguishable from an instruction they gave you. Do NOT "
                 "use it for things you can find out with another tool."),
    parameters={
        "question": {"type": "string", "required": True,
                     "description": "One specific question, in plain words."},
        "options": {"type": "array", "required": True,
                    "description": "2-4 concrete choices. Name the real "
                                   "alternatives, not 'yes'/'no' unless the "
                                   "question is genuinely binary."},
    },
    danger=LOW,
    handler=_ask_user,
))


def _recall_conversation(args: dict, ctx: ToolContext) -> dict:
    """Query the live conversation graph — what THIS chat has established.

    Separate from graph_query because the two answer different questions:
    graph_query knows the codebase, this knows what we decided ten turns ago.
    """
    if not ctx.conversation_id:
        return {"status": "error", "summary": "no conversation",
                "output": "There is no active conversation to recall from."}
    g = live_graph.for_conversation(ctx.conversation_id)
    query = (args.get("query") or "").strip()

    if not query:
        text = g.render()
        return {"status": "success", "summary": f"{len(g.nodes)} tracked",
                "output": text or "Nothing tracked in this conversation yet."}

    hits = g.recall(query)
    if not hits:
        return {"status": "success", "summary": "no matches",
                "output": f"Nothing matching {query!r} has come up in this conversation."}
    lines = [f"{h['label']} ({h['kind']}, mentioned {h['mentions']}x, "
             f"turns {h['first_turn']}-{h['last_turn']})" for h in hits]
    return {"status": "success", "summary": f"{len(hits)} match(es)",
            "output": "\n".join(lines)}


register(ToolSpec(
    name="recall_conversation",
    # Its sibling `recall_memory` already says "use it whenever the question
    # says 'I', 'my' or 'me'", and that rule was still losing: measured on
    # qwen2.5:0.5b, "what do you already know about me?" called this one. A
    # rule stated on only one side of a confusable pair is a rule the model
    # reads after it has already chosen, so the exclusion is stated here too.
    description=("Recall what THIS CONVERSATION has established — decisions "
                 "taken, entities and files discussed. Not for facts about "
                 "the user themselves; recall_memory holds those. Use for "
                 "'the option we picked earlier' or 'that file from before'."),
    parameters={
        "query": {"type": "string", "required": False,
                  "description": "What to look for. Omit for the full working set."},
    },
    danger=LOW,
    handler=_recall_conversation,
))


# ── Workspaces ───────────────────────────────────────────────────────────────
def _create_workspace(args: dict, ctx: ToolContext) -> dict:
    files = args["files"]
    if isinstance(files, str):
        try:
            files = json.loads(files)
        except json.JSONDecodeError:
            return {"status": "error", "summary": "files must be a JSON object of path → content",
                    "output": ""}
    if not isinstance(files, dict) or not files:
        return {"status": "error", "summary": "files must be a non-empty object", "output": ""}

    try:
        ws = workspaces.create(
            args["kind"], args["title"], files,
            origin_turn_id=ctx.turn_id, conversation_id=ctx.conversation_id,
        )
    except ValueError as exc:
        return {"status": "error", "summary": str(exc), "output": ""}
    return {"status": "success",
            "summary": f'created workspace "{args["title"]}" with {len(files)} file(s)',
            "output": f'workspace {ws["workspace_id"]} v1: {", ".join(ws["paths"])}\n'
                      + _saved_not_run(files),
            "workspace_id": ws["workspace_id"]}


def _saved_not_run(files: dict) -> str:
    """Saving a script reads as finishing the job, and it is not.

    Measured: asked for a slide deck, the model wrote correct code and filed it
    in a workspace, then told the user the deck had been created successfully.
    Nothing had run and no file existed. A success message that does not
    mention this is how that happens.
    """
    note = ("The files are stored. NOTHING WAS EXECUTED — a workspace holds "
            "text. If this code was meant to produce something, run it with "
            "run_python.")
    binaries = [p for p in files
                if p.lower().endswith((".pdf", ".pptx", ".docx", ".xlsx", ".png",
                                       ".jpg", ".zip"))]
    if binaries:
        note += (f" Note that {', '.join(binaries)} cannot be produced this way "
                 "at all: a workspace stores text, so a file saved under that "
                 "name is not a real document.")
    return note


register(ToolSpec(
    name="create_workspace",
    # The pair create/update is the one a small model inverts most often —
    # measured on qwen2.5:0.5b, "build me a todo app" called update_workspace
    # and "add dark mode to that app" called create_workspace, exactly the
    # wrong way round. What distinguishes them is not the verb, it is whether
    # a workspace already exists, so that is what the description leads with.
    description=("Make a NEW versioned workspace for generated work — code, "
                 "docs, apps. Use this when nothing exists yet and you have "
                 "no workspace id. To change something you already made, use "
                 "update_workspace."),
    parameters={
        "kind": {"type": "string", "required": True,
                 "description": "react | python | markdown | html | notebook | doc | shell"},
        "title": {"type": "string", "required": True, "description": "A short name."},
        "files": {"type": "object", "required": True,
                  "description": 'JSON object mapping path to file content.'},
    },
    danger=LOW,
    persistent=True,
    handler=_create_workspace,
))


def _update_workspace(args: dict, ctx: ToolContext) -> dict:
    files = args["files"]
    if isinstance(files, str):
        try:
            files = json.loads(files)
        except json.JSONDecodeError:
            return {"status": "error", "summary": "files must be a JSON object", "output": ""}
    try:
        res = workspaces.update(
            args["workspace_id"], files, turn_id=ctx.turn_id,
            conversation_id=ctx.conversation_id, summary=args.get("summary"),
        )
    except KeyError as exc:
        return {"status": "error", "summary": str(exc), "output": ""}
    if res.get("unchanged"):
        return {"status": "success", "summary": "no changes", "output": "Content was identical."}
    return {"status": "success",
            "summary": f'v{res["version"]}: {", ".join(res["changed_paths"])}',
            "output": f'workspace {args["workspace_id"]} is now v{res["version"]}',
            "workspace_id": args["workspace_id"]}


register(ToolSpec(
    name="update_workspace",
    description=("Change a workspace that ALREADY exists, by the id you were "
                 "given. Send only the files you are changing — the rest "
                 "carry forward. If you have no workspace id, there is "
                 "nothing to update: use create_workspace."),
    parameters={
        "workspace_id": {"type": "string", "required": True, "description": "Workspace to edit."},
        "files": {"type": "object", "required": True,
                  "description": "JSON object of path → new content, for changed files only."},
        "summary": {"type": "string", "required": False, "description": "What changed."},
    },
    danger=LOW,
    persistent=True,
    handler=_update_workspace,
))


# ── Skills ───────────────────────────────────────────────────────────────────
def _read_skill(args: dict, ctx: ToolContext) -> dict:
    from ..skills import loader as skills

    skill = skills.get(args["name"])
    if skill is None:
        known = ", ".join(skills.all_skills()) or "none"
        return {"status": "error",
                "summary": f'no skill called {args["name"]!r}',
                "output": f"Available skills: {known}."}

    # A skill is a directory, not one file. `frontend-slides` instructs the
    # model to include the whole of viewport-base.css in every deck and to read
    # a template's design.md before using it — so without this the skill's own
    # instructions name files nothing can open, and it quietly produces decks
    # missing the stylesheet that makes them work.
    wanted = (args.get("file") or "").strip()
    if wanted:
        content = skill.read_asset(wanted)
        if content is None:
            available = skill.assets()
            return {"status": "error",
                    "summary": f"no file {wanted!r} in {skill.name}",
                    "output": ("Files in this skill:\n"
                               + "\n".join(available[:80]) if available
                               else "This skill has no supporting files.")}
        return {"status": "success",
                "summary": f"{skill.name}/{wanted} ({len(content)} chars)",
                "output": content}

    assets = skill.assets()
    listing = ""
    if assets:
        shown = assets[:40]
        listing = ("\n\n---\nSupporting files — read one with "
                   '<tool name="read_skill">{"name": "%s", "file": "…"}</tool>:\n'
                   % skill.name) + "\n".join(shown)
        if len(assets) > len(shown):
            listing += f"\n… and {len(assets) - len(shown)} more"
    return {"status": "success", "summary": f"loaded {skill.name}",
            "output": skill.body + listing}


register(ToolSpec(
    name="read_skill",
    description="Read a skill's instructions, or one of its supporting files.",
    parameters={
        "name": {"type": "string", "required": True,
                 "description": "The skill's name."},
        "file": {"type": "string", "required": False,
                 "description": "Optional supporting file, e.g. 'viewport-base.css'."},
    },
    # Reads a file that ships with the app. Nothing to sandbox, nothing to ask
    # about — prompting here would train the user to click through prompts.
    danger=LOW,
    handler=_read_skill,
))


# ── Design system ────────────────────────────────────────────────────────────
def _render_slide_json(args: dict, ctx: ToolContext) -> dict:
    """Render a layout request JSON to PPTX via the design system."""
    import json
    from ..ppt_design.renderer import render_layout_json

    try:
        spec = args.get("spec")
        if isinstance(spec, str):
            spec = json.loads(spec)
        if not isinstance(spec, dict):
            return {"status": "error", "summary": "spec must be a JSON object",
                    "output": ""}

        filename = args.get("filename") or "deck.pptx"
        theme = args.get("theme") or "light"

        ok, msg = render_layout_json(spec, filename, theme=theme)
        if ok:
            return {"status": "success", "summary": f"created {filename}",
                    "output": msg}
        else:
            return {"status": "error", "summary": "layout error",
                    "output": msg}
    except Exception as e:
        return {"status": "error", "summary": "render failed",
                "output": str(e)}


register(ToolSpec(
    name="render_slide_json",
    description=("Render a layout request JSON to a PPTX file. The JSON "
                 "routes through the design system: no code generation, just "
                 "layout selection and deterministic rendering."),
    parameters={
        "spec": {"type": "object", "required": True,
                 "description": "Layout request: {slide_type, title, bullets, ...}"},
        "filename": {"type": "string", "required": False,
                     "description": "Output filename, default 'deck.pptx'."},
        "theme": {"type": "string", "required": False,
                  "description": "light | dark | brand"},
    },
    danger=LOW,
    persistent=True,
    handler=_render_slide_json,
))
