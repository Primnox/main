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
on an observation, a frontier model can. `qwen2.5:7b` is the default because
it is the smallest thing in the app's own supported set that reliably emits
the tool grammar at all — 0.5b does not, which is a measured property of that
model and not of this format.

Needs Ollama running. Nothing else, and no API key.

Usage:
    python scripts/bench_sufficiency.py [model] [trials]
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

OLLAMA = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:7b"
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


def ask(model: str, system: str, transcript: list[dict]) -> str:
    payload = json.dumps({
        "model": model, "messages": [{"role": "system", "content": system}] + transcript,
        "stream": False, "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.load(response)["message"]["content"]


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


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    trials = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_TRIALS

    conversation = setup()
    from primnox2.context.service import estimate_tokens
    from primnox2.tools import runtime

    observation, result_id = compacted(conversation)
    system = runtime.system_prompt()
    full = body()

    print(f"\nSUFFICIENCY — {model}, {trials} trials per case")
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
                reply = ask(model, system, transcript)
            except urllib.error.URLError as exc:
                print(f"\n  Ollama is not answering at {OLLAMA} ({exc}). "
                      f"Start it and re-run.")
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
