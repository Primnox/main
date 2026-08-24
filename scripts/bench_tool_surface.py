"""Can a small model actually pick the right desktop tool?

The plan says shrink the model-facing surface to `observe / act / wait /
verify / ask`. That is a plausible-sounding change with a real cost — a tool
NAME may be a stronger signal for a weak model than a verb nested inside an
enum, and collapsing fifteen names into five trades one kind of difficulty for
another. This codebase decides that sort of question by measuring it.

So: the same tasks, the same model, two surfaces, and a number.

What is measured, per task, from the model's FIRST reply:

    call        did it emit a tool call at all, in any of the accepted shapes
    right       was it the tool the task needs
    args        did the arguments survive the real validator

Those are three separate failures with three different fixes, and reporting
them as one score hides which one is happening. A model that names the right
tool in prose without calling it needs the grammar taught; one that calls the
wrong tool needs better descriptions; one that calls the right tool with junk
arguments needs the parameter docs it was not being given.

Everything goes through the REAL parser and the REAL registry. A harness that
reimplements either measures the harness.

Usage:
    python scripts/bench_tool_surface.py [--model qwen2.5:0.5b] [--runs 1]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from primnox2.tools import runtime                       # noqa: E402
from primnox2.tools.registry import get, tool_names      # noqa: E402

OLLAMA = "http://127.0.0.1:11434/api/chat"
NATIVE = [False]
DISCRETE = [False]
TOPK = [0]
RETRIEVE = [False, None]

# Each task is a plain request plus the state the conversation is already in,
# because "type hello into it" is only answerable when something has been
# read. The accepted set is deliberately more than one where more than one
# answer is genuinely correct — counting a defensible choice as a failure
# makes the benchmark measure agreement with me rather than capability.
# `prior` is (the tool the model already called, the result it got back), and
# it is replayed through the REAL formatter into the REAL message shape the
# scheduler uses — assistant turn carrying the call, user turn carrying
# `format_result`. Describing the state in prose instead measures whether the
# model can follow a narration, which is not a situation it will ever be in.
TASKS = [
    ("what do you already know about me?", None, {"recall_memory"}),
    ("remember that I prefer dark mode", None, {"remember"}),
    ("what did we decide earlier in this conversation?", None,
     {"recall_conversation"}),
    ("work out 137 * 449 for me", None, {"run_python"}),
    ("what version of node is installed?", None, {"run_shell", "run_python"}),
    ("build me a small todo app I can edit", None, {"create_workspace"}),
    ("how does the scheduler work in this codebase?", None, {"graph_query"}),
    ("find the invoice in my documents", None, {"search_assets"}),
    ("read that document back to me",
     ("search_assets", "1 match: asset_a41f 'Invoice-2026-03.pdf'"),
     {"read_asset"}),
    ("add a dark mode toggle to that app",
     ("create_workspace", "Created workspace ws_7c21 'Todo app' v1 "
                          "(index.html, app.js)"),
     {"update_workspace"}),
]


def ask(model: str, system: str, user: str, context: "str | None") -> str:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    if context:
        # Exactly the shape `kernel/scheduler.py` builds: the assistant's own
        # tool call, then the result as a USER message through the real
        # formatter. Anything else measures a conversation the model will
        # never actually be in.
        tool, summary = context
        messages.append({"role": "assistant",
                         "content": f'<tool name="{tool}">{{}}</tool>'})
        messages.append({"role": "user", "content": runtime.format_result(
            {"tool": tool, "status": "success", "summary": summary})})
    payload = json.dumps({
        "model": model, "messages": messages, "stream": False,
        "options": {"temperature": 0.0},
    }).encode()
    request = urllib.request.Request(
        OLLAMA, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())["message"]["content"]


def ask_native(model: str, system: str, user: str, context) -> dict:
    """Ask via Ollama's NATIVE tool calling instead of the tagged-text protocol.

    The emulated grammar asks a model to do two things at once: choose a tool
    and hand-render a `<tool name="x">{...}</tool>` wrapper around valid JSON.
    A 7B does both. A 0.5B has to spend capacity on the punctuation, and the
    codebase already has evidence of that shape of failure — qwen2.5:7b once
    scored 0/5 on the canonical grammar while naming the right tool every
    time.

    Native calling removes the wrapper from the model's job entirely: the
    runtime hands over JSON schemas, the server constrains decoding to them,
    and the model emits a structured call. Primnox already generates those
    schemas in `registry.json_schemas()` and has never sent them anywhere.
    """
    from primnox2.tools.registry import json_schemas

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    if context:
        tool, summary = context
        messages.append({"role": "assistant", "content": "",
                         "tool_calls": [{"function": {"name": tool,
                                                      "arguments": {}}}]})
        # Through the SAME formatter the text path uses. Without it the
        # native path loses the success-path continuation — the line that
        # says a turn may carry on and forbids inventing an outcome — and a
        # 0.5B seeing a bare tool result narrates a conclusion instead of
        # calling again. That fix took the text protocol from 1/10 to 4/10;
        # there is no reason the native path should go without it.
        messages.append({"role": "tool", "content": runtime.format_result(
            {"tool": tool, "status": "success", "summary": summary})})

    payload = json.dumps({
        "model": model, "messages": messages, "stream": False,
        "tools": json_schemas(),
        "options": {"temperature": 0.0},
    }).encode()
    request = urllib.request.Request(
        OLLAMA, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        message = json.loads(response.read())["message"]

    calls = message.get("tool_calls") or []
    if not calls:
        return {"text": message.get("content", ""), "call": None}
    fn = calls[0]["function"]
    arguments = fn.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = {}
    return {"text": "", "call": {"name": fn["name"], "arguments": arguments}}


LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def menu():
    """The tool set as a lettered multiple-choice question.

    The plan calls for benchmarking this and nothing had. The reasoning is
    that the emulated protocol asks a 0.5B to do two hard things in one
    breath: pick one of fourteen tools, and hand-render a JSON object inside
    a tag. Picking a letter is only the first of those, and a letter is one
    token.

    First sentence of each description only. The rest is disambiguation
    written for a model that is weighing options in prose, and this format
    does not let it weigh anything — it is a menu, and a menu with a
    paragraph per line stops being one.
    """
    from primnox2.tools.registry import all_specs

    specs = all_specs()
    lines = []
    for letter, spec in zip(LETTERS, specs):
        # The WHOLE description. Truncating to the first sentence was tried
        # and scored 1/10: the model produced a clean single letter every
        # time and picked almost entirely wrong, because the sentences that
        # tell a confusable pair apart are the second and third ones — the
        # exact text that took tool choice from 3/10 to 5/10. The format is
        # what discrete mode makes easier; the content still has to be there.
        lines.append(f"  {letter}. {spec.name} — {spec.description}")
    return specs, "\n".join(lines)


def ask_discrete(model: str, user: str, context) -> dict:
    """One letter, nothing else."""
    specs, options = menu()
    system = (
        "Choose the single best tool for what the user wants.\n\n"
        + options
        + "\n\nAnswer with ONE letter and nothing else. No explanation, no "
          "JSON, no punctuation."
    )
    messages = [{"role": "system", "content": system}]
    if context:
        tool, summary = context
        messages.append({"role": "user", "content":
                         f"(already done: {tool} — {summary})"})
    messages.append({"role": "user", "content": user})

    payload = json.dumps({
        "model": model, "messages": messages, "stream": False,
        "options": {"temperature": 0.0, "num_predict": 4},
    }).encode()
    request = urllib.request.Request(
        OLLAMA, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        reply = json.loads(response.read())["message"]["content"].strip()

    for character in reply:
        index = LETTERS.find(character.upper())
        if 0 <= index < len(specs):
            return {"text": reply, "call": {"name": specs[index].name,
                                            "arguments": None}}
    return {"text": reply, "call": None}


STOPWORDS = frozenset("""a an and are as at be by do for from has have how i in
is it me my of on or that the them they this to us we what when where which who
you your""".split())


def relevant(user: str, k: int):
    """The k tools whose text best overlaps the request.

    The strongest measured result in this whole exercise was making the menu
    SHORTER: 29 tools down to 15 took desktop tool choice from 4/10 to 8/10.
    Nothing had tried taking 14 down to five, and the 0.5B's dominant failure
    is the shape you would expect from too many options — it latches onto one
    (`recall_memory` in prose, a fixed letter in discrete mode) rather than
    weighing them.

    Lexical overlap, deliberately. A embedding model would choose better and
    would be a second model in the path of every turn, which is precisely the
    cost this is trying to avoid for someone running a 0.5B.
    """
    from primnox2.tools.registry import all_specs

    words = {w.strip(".,?'\"").lower() for w in user.split()} - STOPWORDS
    scored = []
    for spec in all_specs():
        text = (spec.name.replace("_", " ") + " " + spec.description).lower()
        hits = sum(1 for w in words if w and w in text)
        # The name is worth more than the body: a request saying "remember"
        # should reach `remember` before anything whose description happens
        # to mention remembering.
        hits += 2 * sum(1 for w in words if w and w in spec.name.replace("_", " "))
        scored.append((hits, spec))
    scored.sort(key=lambda pair: -pair[0])
    return [spec for _, spec in scored[:k]]


def ask_topk(model: str, user: str, context, k: int) -> dict:
    """The ordinary protocol, shown only the k most relevant tools."""
    chosen = relevant(user, k)
    catalogue = "\n".join(spec.to_grammar_line() for spec in chosen)
    system = (
        "You can use tools. To call one, reply with exactly this block and "
        "nothing else:\n\n"
        '<tool name="TOOL_NAME">\n{"argument": "value"}\n</tool>\n\n'
        "Available tools:\n" + catalogue
    )
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    if context:
        tool, summary = context
        messages.append({"role": "assistant",
                         "content": f'<tool name="{tool}">{{}}</tool>'})
        messages.append({"role": "user", "content": runtime.format_result(
            {"tool": tool, "status": "success", "summary": summary})})
    payload = json.dumps({"model": model, "messages": messages,
                          "stream": False,
                          "options": {"temperature": 0.0}}).encode()
    request = urllib.request.Request(
        OLLAMA, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        reply = json.loads(response.read())["message"]["content"]
    return {"text": reply, "call": runtime.parse_call(reply)}


def candidate_set(accepted, k, seed):
    """`k` tools to show, with the right answer GUARANTEED to be among them.

    An oracle on purpose. The question this sweep asks is whether a tiny
    model gets better as the candidate set shrinks, and that is a different
    question from whether a retriever can find the right candidates. Mixing
    them is what made the earlier top-5 run score 1/10: lexical overlap left
    the correct tool off the menu, so the number measured the retriever and
    said nothing about the premise.

    So the correct tools are always present and the remainder are distractors
    drawn deterministically. What varies is only how many wrong answers sit
    beside the right one.
    """
    import random

    from primnox2.tools.registry import all_specs

    everything = all_specs()
    correct = [spec for spec in everything if spec.name in accepted]
    others = [spec for spec in everything if spec.name not in accepted]
    random.Random(seed).shuffle(others)
    chosen = correct + others[: max(0, k - len(correct))]
    # Back into registry order, so position carries no information about
    # which one is the answer.
    order = {spec.name: i for i, spec in enumerate(everything)}
    return sorted(chosen, key=lambda spec: order[spec.name])


def ask_candidates(model, user, context, accepted, k, seed):
    """The REAL system prompt, with only `k` tools in the catalogue.

    Building a minimal prompt here was tried first and made the whole sweep
    uncomparable: at the full 14 tools it scored 10% where production scores
    50%, so every number was measuring a stripped prompt rather than the
    effect of candidate-set size. The only thing that may vary between rows
    is how many tools are listed.

    Narrowing is done by hiding the others from the registry, which is how
    `describe_for_prompt` is narrowed in production too — so the catalogue
    text, the grammar lines, and the parser's variant patterns all narrow
    together, exactly as they would if a retriever had chosen these five.
    """
    from primnox2.tools import registry

    chosen = {spec.name for spec in candidate_set(accepted, k, seed)}
    hidden = {name: spec for name, spec in registry._REGISTRY.items()
              if name not in chosen}
    for name in hidden:
        del registry._REGISTRY[name]
    try:
        system = runtime.system_prompt()
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        if context:
            tool, summary = context
            messages.append({"role": "assistant",
                             "content": f'<tool name="{tool}">{{}}</tool>'})
            messages.append({"role": "user", "content": runtime.format_result(
                {"tool": tool, "status": "success", "summary": summary})})
        payload = json.dumps({"model": model, "messages": messages,
                              "stream": False,
                              "options": {"temperature": 0.0}}).encode()
        request = urllib.request.Request(
            OLLAMA, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=180) as response:
            reply = json.loads(response.read())["message"]["content"]
        return {"text": reply, "call": runtime.parse_call(reply)}
    finally:
        registry._REGISTRY.update(hidden)


def sweep(model, sizes, shuffles):
    """Accuracy against candidate-set size, everything else held identical."""
    print(f"\nEntropy sweep — {model}, {shuffles} distractor draws per size")
    print(f"  {'candidates':>10s} {'right':>8s} {'args':>8s}   of {len(TASKS) * shuffles}")
    results = []
    for k in sizes:
        right = args_ok = total = 0
        for seed in range(shuffles):
            for user, context, accepted in TASKS:
                total += 1
                try:
                    answered = ask_candidates(model, user, context, accepted,
                                              k, seed)
                except Exception:
                    continue
                call = answered["call"]
                if call and call["name"] in accepted:
                    right += 1
                    if validate(call) is None:
                        args_ok += 1
        print(f"  {k:>10d} {right:>5d}/{total:<3d} {args_ok:>5d}/{total:<3d}")
        results.append((k, right, args_ok, total))
    return results


def validate(call: dict) -> "str | None":
    """Run the arguments past the real registry. None means they are fine."""
    spec = get(call["name"])
    if spec is None:
        return f"no such tool {call['name']!r}"
    missing = [name for name, meta in (spec.parameters or {}).items()
               if meta.get("required") and name not in call["arguments"]]
    if missing:
        return "missing required: " + ", ".join(missing)
    unknown = [k for k in call["arguments"] if k not in (spec.parameters or {})]
    if unknown:
        return "invented arguments: " + ", ".join(unknown)
    return None


from primnox2.tools.registry import DESKTOP_TOOLS as DESKTOP


def only_desktop():
    """Temporarily hide every non-desktop tool from the prompt.

    The cheap version of the experiment. If tool choice improves when
    `run_python` and friends are not competing, the problem is surface size
    and the Phase 2 shrink is justified. If it does not, the problem is the
    descriptions, and collapsing fifteen tools into five would be a large
    refactor aimed at the wrong thing.
    """
    from primnox2.tools import registry

    hidden = {name: spec for name, spec in registry._REGISTRY.items()
              if name not in DESKTOP}
    for name in hidden:
        del registry._REGISTRY[name]
    return hidden


def restore(hidden: dict):
    from primnox2.tools import registry
    registry._REGISTRY.update(hidden)


def prompt_for(context, narrow: bool) -> str:
    """The system prompt this task would really be given.

    Focus is derived in production from whether a control session is live, so
    the harness reproduces that rather than using one prompt throughout —
    tasks 2 onwards all have a session open, and measuring them against the
    unfocused prompt would measure a turn that never happens.
    """
    if RETRIEVE[0]:
        # Exactly what the scheduler now does: the user's text goes in, the
        # catalogue narrows to what the encoder ranks highest.
        return runtime.system_prompt(request=RETRIEVE[1])
    if not narrow or context is None:
        return runtime.system_prompt()
    original = runtime._focus
    runtime._focus = lambda _cid: "desktop"
    try:
        return runtime.system_prompt(conversation_id="bench")
    finally:
        runtime._focus = original


def run(model: str, runs: int, label: str, narrow: bool = False) -> dict:
    shown = prompt_for(TASKS[1][1], narrow)
    print(f"\n{label}  —  {len(tool_names())} tools registered, "
          f"{len(shown)} char prompt (~{len(shown) // 4} tokens) once focused")
    print(f"  {'task':46s} {'called':>7s} {'right':>6s} {'args':>6s}   note")

    totals = {"called": 0, "right": 0, "args": 0, "n": 0}
    for user, context, accepted in TASKS:
        for _ in range(runs):
            totals["n"] += 1
            RETRIEVE[1] = user
            system = prompt_for(context, narrow)
            try:
                if TOPK[0]:
                    answered = ask_topk(model, user, context, TOPK[0])
                    reply, call = answered["text"], answered["call"]
                elif DISCRETE[0]:
                    answered = ask_discrete(model, user, context)
                    reply, call = answered["text"], answered["call"]
                elif NATIVE[0]:
                    answered = ask_native(model, system, user, context)
                    reply, call = answered["text"], answered["call"]
                else:
                    reply = ask(model, system, user, context)
                    call = runtime.parse_call(reply)
            except Exception as exc:
                print(f"  {user[:46]:46s} {'ERR':>7s}          {exc}")
                continue
            note = ""
            if call is None:
                note = "no tool call: " + reply.strip().replace("\n", " ")[:52]
            else:
                totals["called"] += 1
                if call["name"] in accepted:
                    totals["right"] += 1
                    if call.get("arguments") is None:
                        note = "(letter only)"
                    else:
                        problem = validate(call)
                        if problem is None:
                            totals["args"] += 1
                        else:
                            note = problem
                else:
                    note = f"called {call['name']}"
            print(f"  {user[:46]:46s} "
                  f"{'yes' if call else 'no':>7s} "
                  f"{'yes' if call and call['name'] in accepted else 'no':>6s} "
                  f"{'yes' if not note and call else 'no':>6s}   {note}")
    return totals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:0.5b")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--label", default="current surface")
    parser.add_argument("--only-desktop", action="store_true")
    parser.add_argument("--retrieve", action="store_true",
                        help="narrow the catalogue with the encoder")
    parser.add_argument("--sweep", action="store_true",
                        help="accuracy against candidate-set size")
    parser.add_argument("--shuffles", type=int, default=3)
    parser.add_argument("--topk", type=int, default=0,
                        help="show only the N most relevant tools")
    parser.add_argument("--discrete", action="store_true",
                        help="lettered multiple choice instead of a "
                             "rendered tool call")
    parser.add_argument("--native", action="store_true",
                        help="use the provider's own tool calling "
                             "instead of the tagged-text protocol")
    parser.add_argument("--focused", action="store_true",
                        help="narrow the catalogue when a session is live, "
                             "as production does")
    args = parser.parse_args()

    if args.sweep:
        sweep(args.model, [14, 10, 7, 5, 3], args.shuffles)
        return 0
    NATIVE[0] = args.native
    DISCRETE[0] = args.discrete
    RETRIEVE[0] = args.retrieve
    if args.retrieve:
        # Wait for the encoder before timing anything. It loads on a
        # background thread and a benchmark that finishes in two seconds
        # outruns it entirely — every call returns None and the run measures
        # the unnarrowed prompt while claiming to measure retrieval.
        from primnox2.tools import retrieval
        retrieval.warm()
        for _ in range(120):
            if retrieval.ready():
                break
            time.sleep(1)
        if not retrieval.ready():
            print("  encoder never became ready - aborting")
            return 2
        print("  encoder ready")
    TOPK[0] = args.topk
    hidden = only_desktop() if args.only_desktop else {}
    started = time.time()
    try:
        totals = run(args.model, args.runs, args.label, narrow=args.focused)
    finally:
        restore(hidden)
    n = totals["n"] or 1
    print(f"\n  {args.model}: called {totals['called']}/{n}, "
          f"right tool {totals['right']}/{n}, "
          f"valid arguments {totals['args']}/{n}  "
          f"({time.time() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
