"""Saved model profiles.

Switching between a local Ollama and a cloud endpoint meant retyping a base
URL, an API type, a model name and a key every time — so in practice nobody
switches, they edit `.env` and restart, and the key ends up commented out in a
file with the live one three lines below it.

A profile is that whole set, named and saved. Activating one applies it.

WHERE THE KEY LIVES. Not in primnox.db and not in .env — in the OS keyring
(Windows Credential Manager here), one entry per profile. That is what
`schema.sql` meant by "secrets stay in keyring / the vault", and it is the only
storage that survives a database being copied for a backup or attached to a bug
report. If no keyring backend exists the profile still saves and simply has no
key: a machine without a credential store should lose the convenience, not the
feature.

WHY ACTIVATION WRITES THE ENVIRONMENT. `gateway.active_provider()` already
resolves from os.environ, and giving it a second source to consult would mean
two code paths that can disagree about which model is live. Activation exports
the profile instead, so there remains exactly one answer to "what am I talking
to".
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..storage import db

now_ms = lambda: int(time.time() * 1000)

PROFILES_KEY = "provider.profiles"
ACTIVE_KEY = "provider.active_profile"

KEYRING_SERVICE = "primnox2"

# Ollama, spoken to over HTTP rather than through its CLI. The binary is
# frequently not on PATH — it is not on this machine — and the daemon answers on
# a fixed port whether or not the shell can find the executable. HTTP is also
# the only way that works when Ollama runs in a container or on another host.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_OPENAI = f"{OLLAMA_HOST}/v1"

# Long enough for a cold TLS handshake through a CDN. At 3s discovery timed out
# against a Cloudflare-fronted proxy that answers in 2.4s once connected, and
# because `_fetch` swallows failures the picker just kept showing a stale list.
# Nothing on localhost pays for this: a daemon that is down refuses the
# connection immediately rather than hanging until the timeout.
def _discovery_timeout() -> float:
    from . import tunables
    return tunables.get("models.discovery_timeout_s")


DISCOVERY_TIMEOUT_S = 10.0   # default; the live value comes from _discovery_timeout()

# A profile is a PROVIDER, not a model: one endpoint, one key, many models.
# Modelling it the other way round meant re-entering an Anthropic key to move
# from Opus to Sonnet, which is the same friction that made people edit .env.
#
# The catalogue is DATA — providers.json beside this file — not a list in
# Python. Two reasons, and the second is the one that bit:
#
#   Adding a provider should not need a rebuild. A user with a private endpoint
#   edits a JSON file; nobody should have to fork the app to reach their own
#   gateway.
#
#   Model ids go stale faster than anything else in a codebase. A hardcoded
#   ["claude-opus-4-8", "gpt-4o"] is wrong within months and wrong SILENTLY —
#   the picker offers a model the provider retired and the failure surfaces as
#   a 404 from the API. So the shipped catalogue carries no model ids at all:
#   `discover()` asks the provider what it actually offers.
#
# A user file at <data root>/providers.json overrides and extends the shipped
# one by name, so a local edit survives an app update.

CATALOGUE_FILE = Path(__file__).with_name("providers.json")


def _expand(value: str) -> str:
    """Resolve ${VAR} in a catalogue entry against the environment.

    Lets the shipped file say ${OLLAMA_HOST} rather than a literal address,
    so pointing at a remote engine is an environment variable and not an edit.
    """
    out = value
    for name, replacement in (("OLLAMA_HOST", OLLAMA_HOST),):
        out = out.replace("${" + name + "}", replacement)
    return out


def _load_catalogue_file(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data.get("providers") if isinstance(data, dict) else data
    return rows if isinstance(rows, list) else []


def catalogue() -> list[dict]:
    """Shipped providers, overridden and extended by the user's own file."""
    shipped = _load_catalogue_file(CATALOGUE_FILE)

    user_rows: list[dict] = []
    try:
        from .. import paths
        user_file = Path(paths.root()) / "providers.json"
        if user_file.exists():
            user_rows = _load_catalogue_file(user_file)
    except Exception:
        pass

    merged: dict[str, dict] = {}
    for row in [*shipped, *user_rows]:          # user last, so it wins
        name = (row.get("name") or "").strip()
        if not name:
            continue
        entry = dict(row)
        entry["name"] = name
        entry["base_url"] = _expand(str(entry.get("base_url") or ""))
        entry.setdefault("api_type", "openai")
        entry.setdefault("kind", "cloud")
        merged[name] = entry
    return list(merged.values())


def _seed() -> list[dict]:
    """Catalogue entries as profiles. Model lists start from the hint, which is
    normally empty — discovery fills them."""
    out = []
    for entry in catalogue():
        models = list(entry.get("fallback_models") or [])
        out.append({
            "name": entry["name"], "base_url": entry["base_url"],
            "api_type": entry["api_type"], "kind": entry["kind"],
            "model": models[0] if models else "", "models": models,
        })
    return out


FIELDS = ("name", "base_url", "api_type", "model", "kind")


# ── keyring ──────────────────────────────────────────────────────────────────
def _keyring():
    try:
        import keyring
        return keyring
    except Exception:
        return None


def keyring_available() -> bool:
    return _keyring() is not None


def set_key(profile: str, key: str) -> bool:
    kr = _keyring()
    if kr is None:
        return False
    try:
        if key.strip():
            kr.set_password(KEYRING_SERVICE, f"profile:{profile}", key.strip())
        else:
            try:
                kr.delete_password(KEYRING_SERVICE, f"profile:{profile}")
            except Exception:
                pass          # deleting one that was never set is not an error
        return True
    except Exception:
        return False


def get_key(profile: str) -> str:
    """Read a profile's key. Called on activation only — never by a read that
    reaches the UI, so the value has no path to a screen or a log."""
    kr = _keyring()
    if kr is None:
        return ""
    try:
        return kr.get_password(KEYRING_SERVICE, f"profile:{profile}") or ""
    except Exception:
        return ""


def has_key(profile: str) -> bool:
    return bool(get_key(profile))


# ── store ────────────────────────────────────────────────────────────────────
def _read(key: str, default):
    row = db.connect().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def _write(key: str, value) -> None:
    with db.tx() as c:
        c.execute(
            "INSERT INTO settings (key,value,updated_at) VALUES (?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
            "                                updated_at=excluded.updated_at",
            (key, json.dumps(value), now_ms()),
        )


def profiles() -> list[dict]:
    saved = _read(PROFILES_KEY, None)
    if saved is None:
        saved = _seed()
        # Ollama is on this machine and costs one local request, so the local
        # profile arrives with what is actually installed rather than empty or
        # — worse — with a model name someone guessed at build time.
        installed = [m["name"] for m in ollama_status()["models"]]
        if installed:
            for row in saved:
                if row.get("kind") == "ollama":
                    row["models"] = installed
                    row["model"] = installed[0]
        _write(PROFILES_KEY, saved)
    return saved


def active_name() -> str | None:
    return _read(ACTIVE_KEY, None)


# ── discovery ────────────────────────────────────────────────────────────────
def _fetch(url: str, headers: dict | None = None) -> dict | None:
    import urllib.error
    import urllib.request

    # The same User-Agent the gateway sends, for the same measured reason:
    # Cloudflare's browser-integrity check answers Python's default
    # `Python-urllib/3.11` with HTTP 403, including on a bare GET /v1/models.
    # The gateway learned this and this path did not, so discovery against a
    # Cloudflare-fronted provider failed every time — silently, because the
    # except below turns it into "the provider offered nothing" and the picker
    # keeps whatever stale list it had.
    from ..models.gateway import USER_AGENT

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        with urllib.request.urlopen(req, timeout=_discovery_timeout()) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        # Discovery is a convenience. An endpoint that is down, unauthenticated
        # or simply does not implement a model list must leave the saved list
        # alone rather than emptying the picker.
        return None


def ollama_status() -> dict:
    """Is the local engine up, and what has it got?

    Kept separate from generic discovery because Ollama's native `/api/tags`
    returns sizes and modified times that the OpenAI-compatible `/v1/models`
    shim drops, and knowing a model is 4.7GB is the difference between "pick
    one" and "pick one that will fit".
    """
    tags = _fetch(f"{OLLAMA_HOST}/api/tags")
    if tags is None:
        return {"running": False, "host": OLLAMA_HOST, "models": []}
    models_out = []
    for m in tags.get("models", []):
        models_out.append({
            "name": m.get("name", ""),
            "size_gb": round((m.get("size") or 0) / 1_000_000_000, 1),
            "family": (m.get("details") or {}).get("family", ""),
            "parameters": (m.get("details") or {}).get("parameter_size", ""),
            "quantization": (m.get("details") or {}).get("quantization_level", ""),
        })
    return {"running": True, "host": OLLAMA_HOST,
            "models": sorted(models_out, key=lambda m: m["name"])}


def discover(name: str) -> list[str]:
    """Ask a provider what models it offers, and remember the answer.

    Ollama is asked natively; everything else is asked through the
    OpenAI-compatible `/v1/models`, which Anthropic and most proxies implement.
    A provider that answers nothing keeps whatever was saved.
    """
    profile = next((p for p in profiles() if p["name"] == name), None)
    if profile is None:
        raise KeyError(name)

    found: list[str] = []
    if profile.get("kind") == "ollama" or profile["base_url"].startswith(OLLAMA_HOST):
        found = [m["name"] for m in ollama_status()["models"]]
    else:
        key = get_key(name)
        headers = {}
        if key:
            # Anthropic wants x-api-key; everyone else wants a bearer token.
            # Sending both is harmless and avoids branching on a guess.
            headers["Authorization"] = f"Bearer {key}"
            headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
        # Base URLs come in two shapes and the catalogue holds both: OpenAI-style
        # entries carry the version (`…/v1`), Anthropic-style ones do not. So
        # `<base>/models` is the right URL for one and wrong for the other —
        # against a proxy on an Anthropic-style URL it asked for `/models` and
        # got HTTP 305 while `/v1/models` answered 200. Try the versioned path
        # first when the base has no version of its own.
        base = profile["base_url"].rstrip("/")
        candidates = [f"{base}/models"]
        if not base.endswith("/v1"):
            candidates.insert(0, f"{base}/v1/models")

        for url in candidates:
            payload = _fetch(url, headers)
            if not isinstance(payload, dict):
                continue
            rows = payload.get("data") or payload.get("models") or []
            found = [r.get("id") or r.get("name") for r in rows if isinstance(r, dict)]
            found = [f for f in found if f]
            if found:
                break

    if found:
        profile["models"] = sorted(set(found))
        if profile.get("model") not in profile["models"]:
            profile["model"] = profile["models"][0]
        rows = [p for p in profiles() if p["name"] != name] + [profile]
        _write(PROFILES_KEY, rows)
    return profile.get("models", [])


def use_model(name: str, model: str) -> dict:
    """Switch model within a provider, without re-entering anything.

    The common case by far — Opus to Sonnet, or 7B to 14B — and the one the
    previous shape made as expensive as changing provider entirely.
    """
    profile = next((p for p in profiles() if p["name"] == name), None)
    if profile is None:
        raise KeyError(name)
    profile["model"] = model
    if model not in profile.get("models", []):
        profile["models"] = sorted(set(profile.get("models", []) + [model]))
    rows = [p for p in profiles() if p["name"] != name] + [profile]
    _write(PROFILES_KEY, rows)
    if active_name() == name:
        activate(name)              # live immediately, not on next restart
    return profile


def save(profile: dict) -> dict:
    """Create or update a profile by name. Returns the stored record.

    The key travels in the same call for convenience but is split out here and
    never written to `settings` — a caller cannot accidentally persist it by
    passing the whole form object through.
    """
    name = (profile.get("name") or "").strip()
    if not name:
        raise ValueError("a profile needs a name")

    existing = next((p for p in profiles() if p["name"] == name), {})
    record = {f: str(profile.get(f) or existing.get(f) or "").strip() for f in FIELDS}
    record["name"] = name
    if record["api_type"] not in ("anthropic", "openai"):
        record["api_type"] = "openai"
    # The model list survives an edit that does not mention it, so renaming a
    # profile or fixing a typo in its URL does not silently empty the picker.
    incoming = profile.get("models")
    record["models"] = sorted(set(incoming)) if incoming else existing.get("models", [])
    if record["model"] and record["model"] not in record["models"]:
        record["models"] = sorted(set(record["models"] + [record["model"]]))
    if not record["model"] and record["models"]:
        record["model"] = record["models"][0]

    rows = [p for p in profiles() if p["name"] != name]
    rows.append(record)
    _write(PROFILES_KEY, rows)

    if profile.get("api_key") is not None:
        set_key(name, str(profile["api_key"]))
    return record


def delete(name: str) -> bool:
    rows = profiles()
    remaining = [p for p in rows if p["name"] != name]
    if len(remaining) == len(rows):
        return False
    _write(PROFILES_KEY, remaining)
    set_key(name, "")                       # forget the credential too
    if active_name() == name:
        _write(ACTIVE_KEY, None)
    return True


def activate(name: str) -> dict:
    """Make a profile live, immediately and for the next boot.

    Applied to os.environ rather than handed to the gateway, so there is one
    resolution path and "what model am I on" has one answer.
    """
    profile = next((p for p in profiles() if p["name"] == name), None)
    if profile is None:
        raise KeyError(name)

    os.environ["PRIMNOX_BASE_URL"] = profile["base_url"]
    os.environ["PRIMNOX_API_TYPE"] = profile["api_type"]
    os.environ["PRIMNOX_MODEL"] = profile["model"]
    key = get_key(name)
    if key:
        os.environ["PRIMNOX_API_KEY"] = key
    else:
        # Cleared, not left behind: a stale key from the previous profile would
        # be sent to the new endpoint, which is both wrong and a credential
        # leak to a host the user did not choose to send it to.
        os.environ.pop("PRIMNOX_API_KEY", None)

    _write(ACTIVE_KEY, name)
    return profile


def apply_active() -> str | None:
    """Re-apply the active profile at boot. Returns its name, or None."""
    name = active_name()
    if not name:
        return None
    try:
        activate(name)
        return name
    except KeyError:
        return None


def describe() -> dict:
    """The profile list for the UI. Keys are reported as present, never returned."""
    active = active_name()
    return {
        "profiles": [
            {**p, "has_key": has_key(p["name"]), "active": p["name"] == active}
            for p in profiles()
        ],
        "active": active,
        "keyring": keyring_available(),
        # Surfaced whether or not an Ollama profile is active: "is the engine
        # even running" is the first question when a local model does not answer,
        # and the answer used to require a terminal.
        "ollama": ollama_status(),
    }
