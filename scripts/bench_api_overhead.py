"""What Primnox costs on top of just calling the API yourself.

The question this answers is the one somebody actually asks before installing
an assistant: if I sent this message to the model directly, versus sending it
through Primnox, what is the difference on my bill?

Everything else in this directory measures Primnox against itself. This
measures it against the alternative, using the same provider, the same model
and the same question, with the provider's own usage accounting as the
referee.

Three shapes, because they cost very differently and people mean different
ones by "a message":

  BARE          one user message, nothing else. What a script does.
  PRIMNOX       the same question behind the full preamble — grammar, tool
                catalogue, memory, skills index.
  TOOL TURN     what a question that actually uses a tool costs, where the
                preamble is re-sent on every iteration.

Costs real money — a handful of calls. The key is read from `.env` and never
printed.

Usage:
    python scripts/bench_api_overhead.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

QUESTION = "What is the capital of France, and why did it end up there?"


def call(base, key, model, system, messages) -> dict:
    from primnox2.models.gateway import USER_AGENT

    body = {"model": model, "max_tokens": 64, "messages": messages}
    if system:
        body["system"] = system
    request = urllib.request.Request(
        f"{base}/v1/messages", data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read())
    u = payload.get("usage") or {}
    return {"input": u.get("input_tokens", 0),
            "write": u.get("cache_creation_input_tokens", 0),
            "read": u.get("cache_read_input_tokens", 0),
            "output": u.get("output_tokens", 0)}


def sent(u):
    return u["input"] + u["write"] + u["read"]


def billed(u):
    """Input-side cost in token-equivalents.

    A cache read is billed at roughly a tenth of an input token and a cache
    write at roughly a quarter more than one, so a prompt that is mostly
    cached costs far less than its size. Output is reported separately because
    it is priced differently again and is not what this comparison is about.
    """
    return u["input"] + u["write"] * 1.25 + u["read"] * 0.10


def main() -> int:
    from bench_prompt_cache import config

    settings = config()
    base, key, model = (settings["PRIMNOX_BASE_URL"],
                        settings["PRIMNOX_API_KEY"],
                        settings["PRIMNOX_MODEL"])
    if not key or not base:
        print("no cloud key in .env")
        return 2

    from primnox2 import paths
    from primnox2.storage import db

    root = pathlib.Path(tempfile.mkdtemp(prefix="overhead"))
    paths.configure(root)
    db.configure(root / "primnox.db")
    db.init()

    from primnox2.memory import service as memory
    from primnox2.tools import runtime

    for i in range(25):
        memory.remember(f"The user prefers approach {i} for their project {i}")

    preamble = runtime.system_prompt()
    print(f"provider {base}  model {model}\n")

    rows = []

    # 1. What a script pays.
    bare = call(base, key, model, None, [{"role": "user", "content": QUESTION}])
    rows.append(("bare API call", bare, 1))
    time.sleep(1)

    # 2. The same question through Primnox's preamble. Twice — the first call
    #    writes the cache, the second reads it, and the second is what a user
    #    on their second message actually pays.
    call(base, key, model, preamble, [{"role": "user", "content": QUESTION}])
    time.sleep(1)
    warm = call(base, key, model, preamble,
                [{"role": "user", "content": QUESTION}])
    rows.append(("Primnox, one step", warm, 1))
    time.sleep(1)

    # 3. A tool turn. Four steps, each carrying the calls and results the ones
    #    before it left behind — which is what makes a tool turn expensive.
    messages = [{"role": "user", "content": QUESTION}]
    result = runtime.format_result({
        "tool": "graph_query", "status": "success",
        "summary": "4 matches", "output": "x" * 2000})
    loop_sent = loop_billed = 0
    for step in range(4):
        got = call(base, key, model, preamble, messages)
        loop_sent += sent(got)
        loop_billed += billed(got)
        messages = messages + [
            {"role": "assistant",
             "content": '<tool name="graph_query">{"query": "paris"}</tool>'},
            {"role": "user", "content": result},
        ]
        time.sleep(1)
    rows.append(("Primnox, 4-step tool turn",
                 {"input": 0, "write": 0, "read": 0, "output": 0}, 4))
    time.sleep(1)

    # 4. The same tool turn, but with a cache breakpoint on the CONVERSATION
    #    as well as the system block.
    #
    #    One breakpoint caches the preamble and nothing after it, so every
    #    tool result is re-sent uncached in every later step - result one is
    #    billed three times over four steps. Anthropic allows up to four
    #    breakpoints, and moving one onto the last message each round means
    #    the growing conversation is cached too, so a step pays full price
    #    only for what it just added.
    messages = [{"role": "user", "content": QUESTION}]
    marked_loop_sent = marked_loop_billed = 0
    for step in range(4):
        convo = [dict(m) for m in messages]
        convo[-1] = {"role": convo[-1]["role"],
                     "content": [{"type": "text", "text": convo[-1]["content"],
                                  "cache_control": {"type": "ephemeral"}}]}
        got = call(base, key, model, preamble, convo)
        marked_loop_sent += sent(got)
        marked_loop_billed += billed(got)
        messages = messages + [
            {"role": "assistant",
             "content": '<tool name="graph_query">{"query": "paris"}</tool>'},
            {"role": "user", "content": result},
        ]
        time.sleep(1)
    rows.append(("  + conversation cached",
                 {"input": 0, "write": 0, "read": 0, "output": 0}, 4))

    base_billed = billed(bare)
    print(f"  {'shape':28s} {'sent':>9s} {'billed':>9s} {'vs bare':>9s}")
    for label, usage, steps in rows:
        if label.startswith("Primnox, 4"):
            s, b = loop_sent, loop_billed
        elif label.strip().startswith("+ conversation"):
            s, b = marked_loop_sent, marked_loop_billed
        else:
            s, b = sent(usage), billed(usage)
        print(f"  {label:28s} {s:9,d} {b:9,.0f} "
              f"{b / max(1, base_billed):8.1f}x")

    print(f"\n  A bare call is {sent(bare):,} tokens because the question is "
          f"short.\n  Primnox adds a {sent(warm) - sent(bare):,}-token "
          f"preamble to it — but {100 * warm['read'] / max(1, sent(warm)):.0f}% "
          f"of that\n  comes back from cache, so the BILLED difference is "
          f"{billed(warm) - base_billed:,.0f} tokens,\n  not "
          f"{sent(warm) - sent(bare):,}.")
    print(f"\n  The tool turn is where it costs: {loop_billed:,.0f} "
          f"token-equivalents,\n  {loop_billed / max(1, base_billed):.0f}x a "
          f"bare call, for one question.")
    delta = loop_billed - marked_loop_billed
    verb = "saving" if delta > 0 else "COSTING an extra"
    print(f"\n  Caching the conversation as well as the preamble: "
          f"{marked_loop_billed:,.0f}\n  token-equivalents — {verb} "
          f"{abs(delta):,.0f} ({abs(100 * delta / max(1, loop_billed)):.0f}%).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
