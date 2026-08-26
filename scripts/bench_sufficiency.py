"""Can a model still do the work once the result has been compacted?

`bench_compaction.py` measures what compaction saves and cannot measure what
it costs. Those are different questions, and only the second one decides
whether the saving is real: a mechanism that replaced every tool result with
the word "done" would score 99% on that benchmark and make the assistant
useless. The number is only earned if the observation still carries the turn.

So this puts a real model in front of a real compacted transcript and asks
for the two behaviours that have to both be true:

  ANSWERS FROM THE OBSERVATION when the observation is enough. If the model
  fetches the body every time, compaction has not saved anything — it has
  moved the cost one step later and added a round trip. This is the failure
  that looks like success on a token benchmark.

  FETCHES WHEN IT IS NOT. The observation is a head and a tail; a detail in
  the middle is genuinely absent, and the model has to notice that and call
  `read_result` rather than inventing an answer. This is the failure that
  looks like success on an eval — a confident, wrong reply.

Run against a LOCAL model on purpose. It is free, so this can be run on every
change to the observation format, and it is the harder case: if a 7B can act
on an observation, a frontier model can. `qwen2.5:7b` is the default when
Ollama is the transport because it is the smallest thing in the app's own
supported set that reliably emits the tool grammar at all — 0.5b does not,
which is a measured property of that model and not of this format.

Two transports, because "local" does not mean the same endpoint on every
machine. Ollama speaks its own `/api/chat`; everything else within reach —
OmniRoute, LM Studio, vLLM, llama.cpp's server — speaks the OpenAI chat
completions shape. Both are here, and they differ only in where temperature
goes on the way out and where the reply comes back. Not one scored thing is
computed differently, so a number from one transport means the same as a
number from the other.

The default is OmniRoute on 127.0.0.1:20128 rather than Ollama, on the
grounds that a benchmark nobody on this machine can run measures nothing.
Pass `--ollama` to go back to the local 7B this was originally written
against. No API key either way.

Usage:
    python scripts/bench_sufficiency.py [model] [trials]
    python scripts/bench_sufficiency.py --ollama qwen2.5:7b 5
    PRIMNOX_BENCH_URL=http://host:8000/v1/chat/completions python ...
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

OLLAMA = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:7b"

# OmniRoute, the local gateway. OpenAI-shaped, unauthenticated, and it fronts
# enough models that which one to use stops being a reason not to run this.
OPENAI = "http://127.0.0.1:20128/v1/chat/completions"

# Not every id behind that gateway can host this benchmark, and the ones that
# cannot fail silently rather than loudly. The `*-web` upstreams are scraped
# browser sessions: they forward only the final user message and discard the
# system prompt, the assistant turn and the observation itself. The model then
# answers, fluently, that it cannot see any search results — which scores as a
# model failure and is nothing of the kind. Measured on `deepseek-web`: a code
# planted in an earlier user message comes back ABSENT every time, and usage is
# reported as a fixed 2,000 prompt tokens regardless of what was sent, which is
# the tell. Anything named `*-web` is unusable here for that reason.
OPENAI_MODEL = "agy/gemini-2.5-flash"

DEFAULT_TRIALS = 5

RESULT_ID = re.compile(r"res_[0-9a-f]{16}")
TOOL_CALL = re.compile(r'<tool\s+name="([^"]+)"\s*>(.*?)</tool>', re.S)

# A body whose head and tail are unremarkable and whose middle carries the one
# fact worth asking about. Built this way deliberately: an excerpt-based
# observation shows the ends, so a question about the middle is exactly the
# case where the model must notice it is missing rather than guess.
NEEDLE_LINE = 148
NEEDLE = "TIMEOUT_SECONDS = 4711  # the retry ceiling nobody documented"


def setup():
    from primnox2 import paths
    from primnox2.chat import turns
    from primnox2.storage import db
    from v2 import store

    root = pathlib.Path(tempfile.mkdtemp(prefix="primnox-sufficiency"))
    paths.configure(root)
    db.configure(root / "primnox.db")
    db.init()
    store.configure(root / "primnox_v2.db")
    conversation = turns.create_conversation("sufficiency bench")
    return conversation["id"]


def body() -> str:
    lines = []
    for i in range(300):
        if i == NEEDLE_LINE:
            lines.append(f"config/settings.py:{i}: {NEEDLE}")
        else:
            lines.append(f"config/settings.py:{i}: OPTION_{i} = "
                         f"'value_{i}'  # ordinary setting")
    return "\n".join(lines)


def compacted(conversation: str) -> tuple[str, str]:
    """The observation the model will actually be shown, and its handle."""
    from primnox2.tools import observations, runtime

    ledger = observations.Ledger(threshold=0, session=conversation)
    result = {"type": "tool_result", "tool": "run_shell", "status": "success",
              "summary": "300 matching lines in config/settings.py",
              "output": body()}
    observation = ledger.record(runtime.format_result(result), result)
    return observation, result["result_id"]


class Unreachable(RuntimeError):
    """The endpoint declined to produce a completion, for its own reasons.

    Deliberately not the same thing as a wrong answer. A gateway whose free
    upstream has run out answers `service_unavailable`, which says nothing
    at all about whether the observation was sufficient. Counting that as a
    failed trial would put a fabricated number in the table.
    """


def is_ollama(endpoint: str) -> bool:
    """Whether the endpoint wants Ollama's JSON rather than OpenAI's.

    Decided from the path, not the host. The question is never which machine
    answers — both transports are usually on loopback — but which body shape
    it expects, and `/api/chat` is the only route in reach that expects
    Ollama's.
    """
    return endpoint.rstrip("/").endswith("/api/chat")


def detail(exc: Exception) -> str:
    """The endpoint's own words about why it failed.

    `HTTPError` stringifies to the status line and throws the body away, and
    the body is the only place a gateway distinguishes "I am down" from "that
    model does not exist" from "the free upstream is exhausted" — three
    situations that call for three different reactions from whoever ran this.
    """
    if isinstance(exc, urllib.error.HTTPError):
        try:
            return f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}"
        except OSError:
            return f"HTTP {exc.code}"
    return str(exc)


def ask(endpoint: str, model: str, system: str, transcript: list[dict]) -> str:
    """One deterministic completion, in whichever shape the endpoint speaks.

    The system message and the transcript cross unchanged; only the envelope
    around them differs. That is the point of doing it here rather than in
    two separate benchmarks — the thing being measured must not be able to
    drift between transports.
    """
    messages = [{"role": "system", "content": system}] + transcript
    if is_ollama(endpoint):
        payload = {"model": model, "messages": messages, "stream": False,
                   "options": {"temperature": 0}}
    else:
        payload = {"model": model, "messages": messages, "stream": False,
                   "temperature": 0}
    request = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        reply = json.load(response)

    # An OpenAI-compatible gateway will sometimes report an upstream failure
    # inside a 200, so the status code alone does not mean a completion
    # happened. Raising here keeps that out of the scored population.
    if isinstance(reply.get("error"), (dict, str)):
        raise Unreachable(json.dumps(reply["error"])[:500])

    if is_ollama(endpoint):
        return (reply.get("message") or {}).get("content") or ""

    choices = reply.get("choices") or []
    if not choices:
        raise Unreachable(json.dumps(reply)[:500])
    message = choices[0].get("message") or {}
    # `content` only, never a reasoning channel. A model that emits the tool
    # call while thinking has not called anything — that text is not part of
    # the reply the runtime parses, so crediting it would score a failure as
    # a pass for exactly the reason `fetched` refuses to credit prose.
    return message.get("content") or ""


def fetched(reply: str, result_id: str) -> bool:
    """Did the model call `read_result` on the right handle?

    Checked against the grammar the runtime actually parses rather than by
    looking for the word, because a model that writes "I would call
    read_result" in prose has not called anything — that reply reaches the
    user as text, which is the exact failure `format_result` warns about.
    """
    for name, arguments in TOOL_CALL.findall(reply):
        if name == "read_result" and result_id in arguments:
            return True
    return False


def options(argv: list[str]) -> tuple[str, str, int]:
    """Endpoint, model and trial count, from flag, environment and position.

    `[model] [trials]` stays positional and stays first, because that is the
    invocation the module docstring has always promised and the one anybody
    re-running this will type from memory. The endpoint had to go somewhere
    else for that reason: putting it in front would make an old command line
    quietly mean something new, which is worse than a slightly odd flag.
    """
    argv = list(argv)
    ollama = "--ollama" in argv
    if ollama:
        argv.remove("--ollama")
    endpoint = os.environ.get("PRIMNOX_BENCH_URL") or (OLLAMA if ollama
                                                       else OPENAI)
    fallback = OLLAMA_MODEL if is_ollama(endpoint) else OPENAI_MODEL
    model = (argv[0] if argv
             else os.environ.get("PRIMNOX_BENCH_MODEL") or fallback)
    trials = int(argv[1]) if len(argv) > 1 else DEFAULT_TRIALS
    return endpoint, model, trials


def main() -> int:
    endpoint, model, trials = options(sys.argv[1:])

    conversation = setup()
    from primnox2.context.service import estimate_tokens
    from primnox2.tools import runtime

    observation, result_id = compacted(conversation)
    system = runtime.system_prompt()
    full = body()

    print(f"\nSUFFICIENCY — {model}, {trials} trials per case")
    print(f"  via {endpoint}")
    print(f"  the body is {estimate_tokens(full):,} tokens; the observation "
          f"the model sees is {estimate_tokens(observation):,}")
    print(f"  handle {result_id}, needle planted at line {NEEDLE_LINE}")

    cases = [
        # Answerable from the observation: it names the file and the count.
        ("answerable", "Which file did the search match in? Answer in one "
                       "sentence. Do not call a tool if you already know.",
         False),
        # Not answerable: the value is in the middle, which the excerpt elides.
        ("needs the body", f"What is TIMEOUT_SECONDS set to in that file? "
                           f"If the value is not in front of you, fetch it.",
         True),
    ]

    rows = []
    for label, question, should_fetch in cases:
        correct = 0
        for _ in range(trials):
            transcript = [
                {"role": "user", "content": "search config/settings.py"},
                {"role": "assistant",
                 "content": '<tool name="run_shell">{"command": "grep -n .* '
                            'config/settings.py"}</tool>'},
                {"role": "user", "content": observation},
                {"role": "user", "content": question},
            ]
            try:
                reply = ask(endpoint, model, system, transcript)
            except (urllib.error.URLError, Unreachable) as exc:
                print(f"\n  No completion from {endpoint}.")
                print(f"  {detail(exc)}")
                # Abandoning the run rather than scoring the trials that did
                # land: a partial table looks like a result and is not one.
                print(f"  Nothing was measured. This is the endpoint's "
                      f"problem, not the model's.")
                return 2
            did = fetched(reply, result_id)
            # For the answerable case, correct means BOTH not fetching and
            # actually saying the answer — a model that stays silent has not
            # demonstrated the observation was enough.
            if should_fetch:
                correct += did
            else:
                correct += (not did) and "settings.py" in reply
        rows.append((label, correct, trials, should_fetch))

    print(f"\n  {'case':16s} {'expected':14s} {'correct':>9s}")
    for label, correct, total, should_fetch in rows:
        expected = "calls read_result" if should_fetch else "answers directly"
        print(f"  {label:16s} {expected:14s} {correct:5d}/{total}")

    answered, fetches = rows[0][1], rows[1][1]
    print(f"\n  An observation is only worth its saving if BOTH hold. "
          f"{answered}/{trials} answered\n  without fetching and "
          f"{fetches}/{trials} fetched when the detail was absent.")
    if answered < trials:
        print(f"  Fetching when it did not need to costs a round trip and "
              f"pays for the\n  result twice — `result_store.sufficiency()` "
              f"is where that shows up in\n  production.")
    if fetches < trials:
        print(f"  NOT fetching when the detail is absent is the dangerous "
              f"one: the model\n  answers from an excerpt that does not "
              f"contain the answer.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
