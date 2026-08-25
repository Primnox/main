"""What an eight-step turn actually costs, billed by the provider.

`bench_compaction.py` counts tokens locally and applies cache multipliers to
them. That is a MODEL of billing, and a model of billing is exactly the kind
of thing that is wrong in ways nobody notices — it agreed with itself no
matter what the provider did, because the provider was never asked.

`bench_prompt_cache.py` then measured the thing the model had assumed and
found it false in an interesting direction: the configured proxy caches
WITHOUT being asked, so `cache_control` is a no-op against it. Which raises
the question that one cannot answer — if the prefix is cached automatically,
was the growing conversation ALSO already cached? If it was, then the
"compaction plus a cache marker" story is wrong twice over: the marker buys
nothing, and the baseline it was measured against was never real.

So this replays the same eight-step turn against the live provider, in both
regimes, and reads the provider's own accounting back per step. No
multipliers, no assumptions about what is cached. The numbers it prints are
what the account was charged.

COSTS REAL MONEY. Verbatim sends its whole history every step, so the
uncompacted arm is around 120k input tokens across nine calls; the compacted
arm is a few thousand. `max_tokens` is 16 throughout because the reply is not
what is being measured. The key is read from `.env` and never printed.

Usage:
    python scripts/bench_live_turn.py [steps]
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

CALL = '<tool name="graph_query">{"question": "where does the cost go"}</tool>'


def send(base_url: str, key: str, model: str, system, messages: list[dict]) -> dict:
    from primnox2.models.gateway import USER_AGENT

    body = json.dumps({
        "model": model, "max_tokens": 16,
        "system": system, "messages": messages,
    }).encode()
    request = urllib.request.Request(
        f"{base_url}/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def usage_of(payload: dict) -> dict:
    u = payload.get("usage") or {}
    return {"input": u.get("input_tokens", 0),
            "write": u.get("cache_creation_input_tokens", 0),
            "read": u.get("cache_read_input_tokens", 0)}


def billed(u: dict) -> float:
    """Input-side cost in token-equivalents, the same weights as the rest."""
    return u["input"] + u["write"] * 1.25 + u["read"] * 0.10


def run_turn(base_url: str, key: str, model: str, system,
             contents: list[str], *, mark: bool, label: str) -> tuple[float, int]:
    """One whole turn, step by step, billed as the provider bills it.

    `mark` puts a `cache_control` breakpoint on the last message each step —
    the change under test. Run both ways against the same provider so the
    marker's contribution is isolated from whatever the provider does on its
    own.
    """
    messages: list[dict] = []
    total_billed = 0.0
    total_sent = 0
    print(f"\n  {label}")
    print(f"    {'step':>4s} {'input':>8s} {'write':>8s} {'read':>8s} "
          f"{'billed':>9s}")

    for step in range(len(contents) + 1):
        payload_messages = [dict(m) for m in messages]
        if not payload_messages:
            payload_messages = [{"role": "user", "content":
                                 "trace where an eight-step turn spends its tokens"}]
        elif mark and len(payload_messages) >= 2:
            last = payload_messages[-1]
            last["content"] = [{"type": "text", "text": last["content"],
                                "cache_control": {"type": "ephemeral"}}]

        try:
            got = send(base_url, key, model, system, payload_messages)
        except urllib.error.HTTPError as exc:
            print(f"    step {step + 1}: HTTP {exc.code} — {exc.read()[:200]!r}")
            return total_billed, total_sent
        except urllib.error.URLError as exc:
            print(f"    step {step + 1}: unreachable — {exc}")
            return total_billed, total_sent

        u = usage_of(got)
        cost = billed(u)
        total_billed += cost
        total_sent += u["input"] + u["write"] + u["read"]
        print(f"    {step + 1:4d} {u['input']:8,d} {u['write']:8,d} "
              f"{u['read']:8,d} {cost:9,.0f}")

        if step < len(contents):
            if not messages:
                messages.append({"role": "user", "content":
                                 "trace where an eight-step turn spends its tokens"})
            messages.append({"role": "assistant", "content": CALL})
            messages.append({"role": "user", "content": contents[step]})

    return total_billed, total_sent


def main() -> int:
    from bench_prompt_cache import config

    settings = config()
    base = settings.get("PRIMNOX_BASE_URL", "")
    key = settings.get("PRIMNOX_API_KEY", "")
    model = settings.get("PRIMNOX_MODEL", "")
    if not key or not base or "127.0.0.1" in base:
        print("no cloud provider in .env — nothing to bill against")
        return 2

    import bench_compaction as bench

    conversation_id, turn_id = bench.setup()
    rows = bench.prepared(bench._Ctx(conversation_id, turn_id))
    built = bench.regimes(rows)
    from primnox2.tools import runtime

    system = runtime.system_prompt()
    verbatim = built["verbatim"][0]
    eager = built["eager"][0]

    print(f"\nLIVE TURN — {base}, {model}")
    print(f"  {len(verbatim)} tool steps, {len(verbatim) + 1} calls per arm")

    arms = [
        ("verbatim, no marker", verbatim, False),
        ("compacted, no marker", eager, False),
        ("compacted, marker on the last message", eager, True),
    ]
    if "--reverse" in sys.argv:
        # The two compacted arms send IDENTICAL content, so whichever runs
        # second could be reading the first one's cache rather than its own.
        # Swapping them is the cheapest way to tell a real effect from an
        # ordering artefact: if the marker still wins when it goes first, the
        # win is the marker's.
        arms = [arms[0], arms[2], arms[1]]
    results = []
    for label, contents, mark in arms:
        results.append((label, *run_turn(base, key, model, system, contents,
                                         mark=mark, label=label)))

    base_billed = results[0][1] or 1
    by_label = {r[0]: r[1] for r in results}
    print(f"\n  {'arm':40s} {'sent':>10s} {'billed':>10s} {'saved':>8s}")
    for label, total, sent in results:
        print(f"  {label:40s} {sent:10,d} {total:10,.0f} "
              f"{100 * (base_billed - total) / base_billed:7.1f}%")

    marker_delta = (by_label["compacted, no marker"]
                    - by_label["compacted, marker on the last message"])
    unmarked = by_label["compacted, no marker"] or 1
    print(f"\n  The marker's own contribution: {marker_delta:,.0f} "
          f"token-equivalents\n  ({100 * marker_delta / unmarked:.1f}% of the "
          f"unmarked compacted arm). Anything near zero means\n  the provider "
          f"was already caching what the marker asks it to cache.")
    print(f"\n  Run again with --reverse. The two compacted arms send identical "
          f"content,\n  so a marker that only wins when it goes second is "
          f"reading the other arm's\n  cache rather than its own.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
