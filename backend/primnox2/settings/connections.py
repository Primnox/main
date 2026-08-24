"""Does this provider actually work?

Everything in `models.py` up to now takes the user's word for it: a profile is
saved, a key goes into the keyring, and whether any of it is correct is
discovered on the next real turn — as a failed conversation, which is the most
expensive place to find out and the worst place to read an error.

This module answers the question before a turn depends on it. One probe, one
verdict, with the same classifier the routing chain uses so "your key is
rejected" reads identically here and mid-conversation.

WHAT A PASS ACTUALLY PROVES. That the endpoint resolved, TLS completed, the
credential was accepted, and the provider returned a model list. It does NOT
prove chat completions work — some endpoints serve `/models` to anyone and
reject `/chat/completions` without a paid plan. The wording in the UI says
"reachable", never "working", for that reason.

WHY A TEST CAN CLOSE A BREAKER. When someone pastes a corrected key and the
probe succeeds, the circuit that has been benching that provider is stale by
definition. Closing it here is what makes "fix it and carry on" work without
waiting out a cooldown that is measuring a problem that no longer exists. A
FAILED probe is recorded too, but only for a saved profile — a test of an
endpoint nobody committed to should not create health history for it.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

log = logging.getLogger("primnox2.routing.connections")

# Longer than discovery's: a test is something the user asked for and is
# watching, so waiting is better than a false negative on a cold CDN.
TIMEOUT_S = 20.0


def _candidate_urls(base_url: str) -> list[str]:
    """`/v1/models` first when the base carries no version of its own.

    Base URLs come in two shapes and the catalogue holds both — OpenAI-style
    entries carry the version, Anthropic-style ones do not. Asking the wrong
    one produced an HTTP 305 against a real proxy, which classifies as a
    failure and is really just the wrong path.
    """
    base = base_url.rstrip("/")
    urls = [f"{base}/models"]
    if not base.endswith("/v1"):
        urls.insert(0, f"{base}/v1/models")
    return urls


def _headers(api_key: str) -> dict:
    from ..models.gateway import USER_AGENT

    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if api_key:
        # Anthropic wants x-api-key, everyone else a bearer token. Sending both
        # is harmless and avoids branching on a guess about which this is.
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    return headers


def probe(base_url: str, api_key: str = "") -> dict:
    """One HTTP round trip. Never raises — the verdict IS the return value."""
    from ..models import failures

    if not base_url.strip():
        return {"ok": False, "reason": "no_endpoint", "error": "No base URL to test.",
                "latency_ms": 0, "models": [], "status": None}

    headers = _headers(api_key)
    last: dict | None = None

    for url in _candidate_urls(base_url):
        started = time.time()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace"))
            elapsed = round((time.time() - started) * 1000)
            rows = body.get("data") or body.get("models") or []
            names = [r.get("id") or r.get("name") for r in rows if isinstance(r, dict)]
            names = sorted(n for n in names if n)
            log.info("probe %s -> %d models in %dms", url, len(names), elapsed)
            return {"ok": True, "reason": "", "error": "", "status": 200,
                    "latency_ms": elapsed, "models": names, "url": url}
        except json.JSONDecodeError:
            # HTTP 200 with a body that is not JSON is a Cloudflare challenge
            # page often enough that it is worth naming rather than reporting
            # as a generic failure.
            elapsed = round((time.time() - started) * 1000)
            last = {"ok": False, "reason": "not_json", "status": 200,
                    "error": "The endpoint answered 200 with something that is not JSON — "
                             "usually a sign-in or bot-check page rather than an API.",
                    "latency_ms": elapsed, "models": [], "url": url}
        except Exception as exc:                                  # noqa: BLE001
            elapsed = round((time.time() - started) * 1000)
            failure = failures.from_exception(exc, base_url)
            last = {"ok": False, "reason": failure.type, "status": failure.status,
                    "error": failure.message[:300], "latency_ms": elapsed,
                    "models": [], "url": url}
            # A 404 on the first shape usually means the other shape is right;
            # anything else is the provider's real answer and trying a second
            # path only doubles the wait.
            if failure.status != 404:
                break

    log.warning("probe %s failed: %s", base_url, (last or {}).get("error"))
    return last or {"ok": False, "reason": "unknown", "error": "No response.",
                    "latency_ms": 0, "models": [], "status": None}


def test_profile(name: str) -> dict:
    """Test a saved profile, using its stored key, and record what happened.

    Recorded against the SAME circuit key the routing chain uses, so a probe
    that succeeds after a fix clears the breaker that was benching it, and one
    that fails counts toward opening it.
    """
    from . import models as store

    profile = next((p for p in store.profiles() if p["name"] == name), None)
    if profile is None:
        raise KeyError(name)

    result = probe(profile.get("base_url", ""), store.get_key(name))
    result["profile"] = name
    _record(profile, result)
    return result


def test_candidate(base_url: str, api_key: str = "") -> dict:
    """Test something not saved yet — a key being tried before it is committed.

    Deliberately records nothing: health history is about endpoints the user
    actually routes through, and a typo in an add form should not leave a
    circuit behind it.
    """
    result = probe(base_url, api_key)
    result["profile"] = None
    return result


def _record(profile: dict, result: dict) -> None:
    from ..models import failures, health

    model = (profile.get("model") or "").strip()
    if not model:
        return                      # no model chosen yet; no circuit to record against
    key = f"{profile['base_url'].rstrip('/')}|{model}"

    if result["ok"]:
        before = health.circuit(key).state
        health.record_success(key, result["latency_ms"])
        if before != health.CLOSED:
            log.info("probe closed the breaker on %s (was %s)", key, before)
        return

    health.record_failure(key, failures.classify(
        profile["name"], model, status=result.get("status"),
        message=result.get("error", "")))


def test_all() -> list[dict]:
    """Every saved profile, in order. Sequential on purpose: these are the
    user's own rate-limited accounts, and firing a dozen probes at once is a
    good way to get a 429 that means nothing about whether the key works."""
    from . import models as store

    out = []
    for profile in store.profiles():
        try:
            out.append(test_profile(profile["name"]))
        except Exception as exc:                                  # noqa: BLE001
            log.warning("probe of %s blew up: %s", profile["name"], exc)
            out.append({"profile": profile["name"], "ok": False, "reason": "unknown",
                        "error": str(exc)[:300], "latency_ms": 0, "models": []})
    return out
