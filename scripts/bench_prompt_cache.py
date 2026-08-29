"""Does prompt caching actually reach the provider, and what does it save?

The Anthropic path now marks the system block with `cache_control`, on the
reasoning that a tool-using turn re-sends an unchanged ~2,800-token prefix on
every iteration and pays for it each time. That reasoning is sound and it is
still a claim about a REMOTE service, made from reading its documentation.
Two things can falsify it and neither is visible locally:

  the proxy in front of the model may not forward `cache_control`, in which
  case nothing is cached and the marker is decoration;

  the prefix may not be byte-identical in practice, in which case every call
  writes a fresh cache entry and the second one costs MORE than no caching at
  all, because a cache write is billed above an ordinary input token.

So this sends the same prompt twice, with and without the marker, and reads
the provider's own accounting back. `cache_read_input_tokens` on the second
call is the whole question.

Costs real money — a handful of calls at a few thousand input tokens. The key
is read from `.env` and never printed.

Usage:
    python scripts/bench_prompt_cache.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def config() -> dict:
    """The CLOUD block from .env, whether or not it is the active one.

    Every value is collected rather than the first one taken. The active block
    points at Ollama and appears first in the file, so first-wins picked
    localhost and the benchmark reported nothing to test — the cloud settings
    were sitting three lines below, commented out.

    Reading the commented lines is deliberate: switching .env over to run one
    benchmark would leave somebody's editor in a state they did not choose.

    THE ENVIRONMENT WINS, AND LOOPBACK IS ALLOWED THERE. Both rules below
    encoded "a real provider is remote and carries a key", which stopped being
    true when OmniRoute became the primary provider: it is a LOCAL gateway
    fronting real cloud models, so it is reachable on 127.0.0.1 and needs no
    key of its own. Under the old rules every billing benchmark in this
    directory refused to run on the machine's actual setup — `config()` threw
    on a missing .env, and the loopback filter discarded the one endpoint
    there was. Reading the environment also keeps this the credential-free
    path: a gateway that needs no key needs no secret written to disk.
    """
    env_base = os.environ.get("PRIMNOX_BASE_URL", "").strip()
    if env_base:
        return {
            "PRIMNOX_BASE_URL": env_base,
            "PRIMNOX_API_KEY": os.environ.get("PRIMNOX_API_KEY", "").strip(),
            "PRIMNOX_MODEL": os.environ.get("PRIMNOX_MODEL", "").strip(),
        }

    env_file = ROOT / ".env"
    if not env_file.exists():
        return {"PRIMNOX_BASE_URL": "", "PRIMNOX_API_KEY": "", "PRIMNOX_MODEL": ""}

    found: dict[str, list[str]] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("#").strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key.startswith("PRIMNOX_") and value:
            found.setdefault(key, []).append(value)

    urls = found.get("PRIMNOX_BASE_URL", [])
    remote = next((u for u in urls if "127.0.0.1" not in u
                   and "localhost" not in u), "")
    models = found.get("PRIMNOX_MODEL", [])
    return {
        "PRIMNOX_BASE_URL": remote,
        "PRIMNOX_API_KEY": next(iter(found.get("PRIMNOX_API_KEY", [])), ""),
        # The cloud block's model, identified by not being one of the local
        # ones rather than by position.
        "PRIMNOX_MODEL": next((m for m in models
                               if ":" not in m), next(iter(models), "")),
    }


def ask(base_url: str, key: str, model: str, system, user: str) -> dict:
    """One non-streaming call. `system` is a string or a content-block list."""
    from primnox2.models.gateway import USER_AGENT

    body = json.dumps({
        "model": model,
        "max_tokens": 16,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    request = urllib.request.Request(
        f"{base_url}/v1/messages", data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "User-Agent": USER_AGENT,
        })
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def usage_of(payload: dict) -> dict:
    u = payload.get("usage") or {}
    return {
        "input": u.get("input_tokens", 0),
        "write": u.get("cache_creation_input_tokens", 0),
        "read": u.get("cache_read_input_tokens", 0),
    }


def main() -> int:
    settings = config()
    base = settings.get("PRIMNOX_BASE_URL", "")
    key = settings.get("PRIMNOX_API_KEY", "")
    model = settings.get("PRIMNOX_MODEL", "")
    if not key or "127.0.0.1" in base:
        # The cloud block is commented out and the fallback found the local
        # one. Nothing to measure against a model that has no cache to hit.
        print("no cloud key in .env — nothing to test against")
        return 2

    # A realistic prefix: the actual system prompt Primnox sends. Padded only
    # if it falls under Anthropic's 1024-token minimum, because a prefix below
    # that is not cacheable and the test would measure nothing.
    from primnox2 import paths
    from primnox2.storage import db
    import tempfile

    root = pathlib.Path(tempfile.mkdtemp(prefix="cachebench"))
    paths.configure(root)
    db.configure(root / "primnox.db")
    db.init()
    from primnox2.context import service as context
    from primnox2.tools import runtime

    system = runtime.system_prompt()
    tokens = context.estimate_tokens(system)
    print(f"provider : {base}")
    print(f"model    : {model}")
    print(f"prefix   : {tokens:,} estimated tokens\n")

    marked = [{"type": "text", "text": system,
               "cache_control": {"type": "ephemeral"}}]

    rows = []
    try:
        print("  without cache_control")
        for attempt in (1, 2):
            got = usage_of(ask(base, key, model, system, "say ok"))
            rows.append(("plain", attempt, got))
            print(f"    call {attempt}: input {got['input']:,}  "
                  f"write {got['write']:,}  read {got['read']:,}")
            time.sleep(1)

        print("\n  with cache_control")
        for attempt in (1, 2):
            got = usage_of(ask(base, key, model, marked, "say ok"))
            rows.append(("cached", attempt, got))
            print(f"    call {attempt}: input {got['input']:,}  "
                  f"write {got['write']:,}  read {got['read']:,}")
            time.sleep(1)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        print(f"\n  HTTP {exc.code}: {detail}")
        print("\n  A 400 mentioning cache_control means the proxy rejects the "
              "marker,\n  which is the outcome worth knowing — it would break "
              "every cloud turn.")
        return 1
    except Exception as exc:
        print(f"\n  request failed: {type(exc).__name__}: {exc}")
        return 1

    plain = [r for kind, _, r in rows if kind == "plain"]
    cached = [r for kind, _, r in rows if kind == "cached"]
    second = cached[1]

    print()
    print('VERDICT')

    # `input_tokens` is the UNCACHED REMAINDER, not the prompt size. Comparing
    # it against a total that adds the cache read back in compares two
    # different things - an earlier version did exactly that and reported a
    # saving of -3598%. What was SENT is the sum of all three fields; what it
    # COSTS applies Anthropic's multipliers, a cache read at about a tenth of
    # an input token and a cache write at about a quarter more than one.
    def sent(u):
        return u['input'] + u['write'] + u['read']

    def billed(u):
        return u['input'] + u['write'] * 1.25 + u['read'] * 0.10

    print(f"  {'':22s} {'sent':>8s} {'billed':>9s} {'from cache':>11s}")
    for label, row in (('without cache_control', plain[1]),
                       ('with cache_control', cached[1])):
        share = 100 * row['read'] / max(1, sent(row))
        print(f'  {label:22s} {sent(row):8,d} {billed(row):9,.0f} {share:10.0f}%')

    if plain[1]['read'] > 0:
        no_cache = sent(cached[1])
        with_cache = billed(cached[1])
        saving = 100 * (1 - with_cache / max(1, no_cache))
        print()
        print('  The proxy caches WITHOUT being asked. cache_control is a no-op')
        print('  here: both rows read the same prefix back, so the marker added')
        print('  nothing against this provider.')
        print()
        print(f'  What the caching is worth: a repeat call is {no_cache:,} tokens')
        print(f'  uncached and is billed {with_cache:,.0f} - a {saving:.0f}% saving on')
        print('  the prefix, already happening before this change.')
        print()
        print('  The marker still matters against Anthropic DIRECT, which caches')
        print('  only when asked. Kept for that, and it buys nothing on the')
        print('  provider actually configured here.')
    elif cached[1]['read'] > 0:
        print()
        print('  Caching engaged ONLY with the marker - the change is doing work.')
    else:
        print()
        print('  No caching either way. The marker is decoration here.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
