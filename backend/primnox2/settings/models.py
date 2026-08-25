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
import re
import shutil
import subprocess
import time
from pathlib import Path

from .. import paths
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

# OmniRoute's default port, overridable for an instance on the LAN or a VPS.
# It listens locally and forwards to the cloud, which is why its catalogue
# entry is `kind: gateway` and not `local` — see providers.json, and
# gateway.on_device_for(), which is what actually enforces the difference.
OMNIROUTE_HOST = os.getenv("OMNIROUTE_HOST", "http://127.0.0.1:20128").rstrip("/")

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
    for name, replacement in (("OLLAMA_HOST", OLLAMA_HOST),
                              ("OMNIROUTE_HOST", OMNIROUTE_HOST)):
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
        # Absent stays absent: an entry with `endpoint_required` is one whose
        # URL OmniRoute keeps in a package the clone does not carry, and "" is
        # the honest value for it — the UI asks rather than guessing.
        if entry.get("base_url"):
            entry["base_url"] = _expand(str(entry["base_url"]))
        entry.setdefault("api_type", "openai")
        entry.setdefault("kind", "cloud")
        merged[name] = entry
    return list(merged.values())


# The gateway is the point of the product now, so it is seeded and it is
# active. Ollama comes with it because the two answer different questions —
# "reach any hosted model" and "reach no network at all" — and a first run
# should be able to do both without configuring anything.
#
# The three remaining catalogue entries (LM Studio, llama.cpp, a direct
# endpoint) are added deliberately or not at all: each needs a running server
# or a key, and a seeded row that cannot answer is a row that looks broken.
PRIMARY_ID = "omniroute"
SEEDED_IDS = ("omniroute", "ollama-local")


def profile_from(entry: dict) -> dict:
    """One catalogue entry as a saved profile."""
    models = list(entry.get("fallback_models") or [])
    return {
        "name": entry["name"], "base_url": entry.get("base_url", ""),
        "api_type": entry.get("api_type", "openai"), "kind": entry.get("kind", "cloud"),
        "model": models[0] if models else "", "models": models,
    }


def _seed() -> list[dict]:
    by_id = {e.get("id"): e for e in catalogue()}
    return [profile_from(by_id[pid]) for pid in SEEDED_IDS if pid in by_id]


def primary_entry() -> dict | None:
    """The catalogue entry Primnox routes through unless told otherwise."""
    return next((e for e in catalogue() if e.get("primary")), None)


def primary_name() -> str:
    entry = primary_entry()
    return entry["name"] if entry else "OmniRoute"


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


# Catalogue entries that used to ship and no longer do. Each of these was one
# provider needing its own key; OmniRoute fronts all of them behind one
# endpoint, so the shipped list stopped carrying five ways to do part of it.
RETIRED_SEEDS = frozenset({"Anthropic", "OpenAI", "Groq", "OpenRouter", "Together"})

# Entries a migration introduces. Named explicitly rather than diffed against
# the catalogue: "add everything missing" resurrects entries the user deleted
# on purpose. OmniRoute is here because it is the primary provider now, and an
# existing install seeded before the pivot would otherwise never see it.
NEW_SEEDS = frozenset({"OmniRoute"})

# Bumped for the gateway pivot: v2 installs already ran the previous
# migration, so without a new key they would never be offered OmniRoute and
# the primary provider would be invisible to every existing user.
MIGRATION_KEY = "provider.catalogue_migration_v3"


def _migrate_catalogue(saved: list[dict]) -> list[dict]:
    """Bring an existing install's profile list in line with the shipped one.

    Runs ONCE, guarded by a stored flag, and does exactly two things:

      Drops a retired seed — but only if it is inert. A profile with a key
      saved, or one that is currently active, is the user's, not the
      catalogue's, and is never touched however it got there. Someone who
      pasted an OpenAI key keeps their OpenAI profile.

      Adds the entries in NEW_SEEDS if they are missing, which is the only
      way an existing install ever sees OmniRoute — `profiles()` seeds on
      first run and never again, so without this the new entry would appear
      only for someone who had never launched Primnox before. Only those:
      anything else absent from the list is absent because the user deleted
      it, and a migration that undoes deletions is a migration nobody trusts.

    Once-only matters in both directions: a user who deletes Ollama should not
    find it back tomorrow, and one who re-adds OpenAI by hand should not find
    it pruned.
    """
    if _read(MIGRATION_KEY, False):
        return saved

    active = active_name()
    kept, dropped = [], []
    for row in saved:
        name = row.get("name", "")
        if name in RETIRED_SEEDS and name != active and not has_key(name):
            dropped.append(name)
            continue
        kept.append(row)

    have = {r.get("name") for r in kept}
    added = [entry for entry in _seed()
             if entry["name"] in NEW_SEEDS and entry["name"] not in have]
    kept.extend(added)

    if dropped or added:
        import logging
        logging.getLogger("primnox2.routing").info(
            "catalogue migration: removed %s, added %s",
            ", ".join(dropped) or "nothing", ", ".join(a["name"] for a in added) or "nothing")
        _write(PROFILES_KEY, kept)
    _write(MIGRATION_KEY, True)
    return kept


def profiles() -> list[dict]:
    saved = _read(PROFILES_KEY, None)
    if saved is not None:
        return _migrate_catalogue(saved)

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

    # A first run lands on the gateway rather than on the echo provider. The
    # seeding used to leave nothing active, so a fresh install answered every
    # message with "point Settings at a real provider" while a perfectly good
    # route sat configured beside it.
    if _read(ACTIVE_KEY, None) is None:
        primary = next((row for row in saved if row["name"] == primary_name()), None)
        if primary is not None:
            _write(ACTIVE_KEY, primary["name"])
    return saved


def active_name() -> str | None:
    return _read(ACTIVE_KEY, None)


def chain(exclude: str | None = None) -> list[dict]:
    """Profiles the gateway may fall back to, in saved order.

    Only the MEMBERSHIP question is answered here — a profile with no model
    chosen cannot serve a request, so it is not a candidate. Everything that
    decides which of these actually gets called (health, the breaker, the
    local/cloud trust boundary, whether a key exists) belongs to models/routing
    and models/gateway, which is where the one routing decision is made. This
    module knowing that a provider is unhealthy would be a second router.

    The key is deliberately NOT read here: `get_key` reaches the OS credential
    store, and paying for every profile to build a list that usually stops at
    the first entry turns a keyring round-trip into a per-turn cost.
    """
    skip = exclude or active_name()
    return [p for p in profiles()
            if p.get("name") != skip and (p.get("model") or "").strip()]


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


FAVOURITES_KEY = "provider.favourites"
NOTES_KEY = "provider.notes"

# OmniRoute's catalogue is filed by how a provider AUTHENTICATES, which is the
# right axis for them and the wrong one to show a person: "apikey/regional" and
# "apikey/inference-hosts" are the same decision to someone picking a provider.
# Regrouped by what you would actually be choosing between.
def favourites() -> list[str]:
    return list(_read(FAVOURITES_KEY, []))


def set_favourite(name: str, pinned: bool) -> list[str]:
    """Pin a provider to the top of the catalogue.

    Stored by NAME rather than catalogue id, because a user file can rename an
    entry and a pin should follow what the person sees, not the slug.
    """
    current = [n for n in favourites() if n != name]
    if pinned:
        current.insert(0, name)
    _write(FAVOURITES_KEY, current)
    return current


def notes() -> dict:
    return dict(_read(NOTES_KEY, {}))


def set_note(name: str, text: str) -> dict:
    """A line of the user's own about a provider — which account it bills to,
    why it was added, what broke last time. The catalogue's own `hint` is the
    vendor's words; this is theirs."""
    all_notes = notes()
    if text.strip():
        all_notes[name] = text.strip()[:500]
    else:
        all_notes.pop(name, None)
    _write(NOTES_KEY, all_notes)
    return all_notes


def export_profiles() -> dict:
    """Every saved profile as portable JSON, WITHOUT keys.

    Keys are excluded rather than obfuscated. An export is a file that gets
    mailed to someone, committed by accident, or attached to a bug report, and
    the only version of it that is safe to treat carelessly is one that never
    contained a credential.
    """
    return {
        "primnox_profiles": 1,
        "exported_at": now_ms(),
        "profiles": [
            {k: p.get(k) for k in ("name", "base_url", "api_type", "kind", "model", "models")}
            for p in profiles()
        ],
        "notes": notes(),
        "favourites": favourites(),
    }


def import_profiles(payload: dict) -> dict:
    """Merge an exported file back in. Additive, and never touches a key.

    A name that already exists is UPDATED in place rather than duplicated, and
    an import can never remove a profile or a credential — the worst a bad file
    can do is add rows the user then deletes.
    """
    rows = payload.get("profiles")
    if not isinstance(rows, list):
        raise ValueError("that file has no `profiles` list — is it a Primnox export?")

    added, updated, skipped = [], [], []
    existing = {p["name"] for p in profiles()}
    for row in rows:
        if not isinstance(row, dict):
            skipped.append("(not an object)")
            continue
        name = str(row.get("name") or "").strip()
        if not name or not str(row.get("base_url") or "").strip():
            skipped.append(name or "(unnamed)")
            continue
        save({k: row.get(k) for k in FIELDS if k in row} | {"name": name,
             "models": row.get("models") or []})
        (updated if name in existing else added).append(name)

    incoming_notes = payload.get("notes")
    if isinstance(incoming_notes, dict):
        merged = notes() | {str(k): str(v)[:500] for k, v in incoming_notes.items()}
        _write(NOTES_KEY, merged)

    return {"added": added, "updated": updated, "skipped": skipped}


def discover_all() -> dict:
    """Refresh every saved profile's model list in one pass.

    Sequential, like the connection tests and for the same reason: these are
    the user's own rate-limited accounts, and a dozen simultaneous requests is
    a good way to earn a 429 that says nothing about whether the key works.
    """
    found = {}
    for profile in profiles():
        name = profile["name"]
        try:
            found[name] = discover(name)
        except Exception as exc:                                  # noqa: BLE001
            import logging
            logging.getLogger("primnox2.routing").warning(
                "discovery for %s failed: %s", name, exc)
            found[name] = []
    return found


def omniroute_status() -> dict:
    """Is the gateway up, and what is behind it?

    This is the most consequential probe in the product now. OmniRoute is how
    Primnox reaches every hosted model, so "is it running" is the difference
    between the app working and the app being able to answer only from Ollama.

    Reported rather than inferred: `running` is whether it answered, `channels`
    are its auto/* routing modes, `model_count` is how much catalogue it has
    loaded — reachable with zero models means it started but has no providers
    configured, which is a completely different problem from being down and
    would otherwise present identically.
    """
    payload = _fetch(f"{OMNIROUTE_HOST}/v1/models")
    if not isinstance(payload, dict):
        return {
            "running": False, "host": OMNIROUTE_HOST, "model_count": 0,
            "channels": [], "configured": False,
            "install": "npm install -g omniroute && omniroute",
            "dashboard": f"{OMNIROUTE_HOST}/dashboard",
        }

    rows = payload.get("data") or payload.get("models") or []
    names = [r.get("id") or r.get("name") for r in rows if isinstance(r, dict)]
    names = sorted(n for n in names if n)
    # The auto/* channels are OmniRoute's routing modes rather than models, and
    # they are what someone should actually pick: a named model pins the turn
    # to one provider and gives up the fallback that is the point of running it.
    channels = sorted(n for n in names if n == "auto" or n.startswith("auto/"))
    return {
        "running": True, "host": OMNIROUTE_HOST, "model_count": len(names),
        "channels": channels, "models": names[:400],
        # Reachable but empty: started, no providers connected yet. Sending it
        # a turn in this state fails in a way that looks like Primnox's fault.
        "configured": len(names) > 0,
        "install": "npm install -g omniroute && omniroute",
        "dashboard": f"{OMNIROUTE_HOST}/dashboard",
    }


def _omniroute_is_local() -> bool:
    """Only a gateway on this machine is ours to start.

    OMNIROUTE_HOST is overridable to a LAN box or a VPS (see its definition),
    and spawning a local process because a remote one is unreachable would
    start a second, differently-configured gateway that then answers on a port
    the user never pointed at. Unreachable-and-remote is a thing to report,
    not a thing to fix from here.
    """
    return bool(re.match(r"https?://(127\.0\.0\.1|localhost|\[::1\])(:|/|$)",
                         OMNIROUTE_HOST))


def _await_omniroute(timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if isinstance(_fetch(f"{OMNIROUTE_HOST}/v1/models"), dict):
            return True
        time.sleep(1.0)
    return False


# A cold OmniRoute start loads its provider catalogue, SQLite and proxy logs
# before it binds, and measured on this machine that ran past 45s while a warm
# restart was ready in 4. The first number is the one that matters: too small a
# budget does not just report wrongly, it lets the NEXT start think nothing is
# coming and spawn a second gateway.
OMNIROUTE_BOOT_SECONDS = 180.0


def _omniroute_argv() -> list[str] | None:
    """What to actually execute, preferring node over npm's shim.

    On Windows `shutil.which` resolves to `omniroute.CMD`, and launching that
    detached does not work: the shim runs `title %COMSPEC%` before handing off
    to node, `title` needs a console, and DETACHED_PROCESS is precisely the
    absence of one. Measured — the spawned tree stayed alive for eight minutes,
    allocating memory and writing its SQLite WAL, and never bound the port.
    Nothing in the log said so either, because the shim swallowed the output
    that was supposed to explain it.

    Running node against the package's own entry point removes cmd.exe from the
    picture, which is the only reason any of that was happening. The shim stays
    as the fallback for a layout where the entry point is not where npm usually
    puts it.
    """
    exe = shutil.which("omniroute")
    node = shutil.which("node")
    if exe and node:
        entry = Path(exe).parent / "node_modules" / "omniroute" / "bin" / "omniroute.mjs"
        if entry.is_file():
            return [node, str(entry)]
    return [exe] if exe else None


def _state_dir() -> Path:
    """Where the gateway's lock and log live.

    Falls back to the same directory `app.py` derives APPDATA from, because
    `paths.root()` raises until `configure()` has run and neither of these
    files is worth coupling to that ordering — bringing the gateway up is a
    convenience, and it must not be able to crash startup by being early.
    """
    try:
        return paths.root()
    except RuntimeError:
        base = Path(os.getenv("PRIMNOX2_HOME", Path.home() / "Documents" / "Primnox2"))
        base.mkdir(parents=True, exist_ok=True)
        return base


def _boot_lock_path():
    return _state_dir() / "omniroute.boot"


def _boot_in_flight() -> bool:
    """Is another start already waiting for the gateway to bind?

    Checked because "not answering yet" and "not running" are identical over
    the port during a cold boot, and treating the first as the second is what
    produced two gateways racing for 20128 — the loser sat there holding half
    a gigabyte and serving nothing. A timestamp file is enough: liveness by
    pid needs OS-specific process checks, and the only question here is
    whether a start is recent enough to still be plausibly booting.
    """
    try:
        age = time.time() - _boot_lock_path().stat().st_mtime
    except OSError:
        return False
    return age < OMNIROUTE_BOOT_SECONDS


def ensure_omniroute_running(*, wait: float = OMNIROUTE_BOOT_SECONDS) -> dict:
    """Start the gateway if it is not already up. Returns what happened.

    BLOCKING — subprocess spawn plus a readiness poll. Call it on a thread,
    never from a request handler or the event loop.

    Detached on purpose, and never killed on Primnox's shutdown. OmniRoute is
    a shared gateway: its own documentation has Claude Code, Cursor and Cline
    pointed at the same endpoint, so treating it as Primnox's child process
    would mean quitting Primnox silently breaks whatever else is mid-request
    against it. It outlives us in both directions — we adopt a running one
    rather than starting a second, and we leave ours behind when we go.

    This exists because the failure it prevents is invisible. With no gateway
    the app looks fine, right up until a turn fails — and the error the user
    actually gets blames the model rather than a missing process.
    """
    if not _omniroute_is_local():
        return {"started": False, "reason": "remote host — not ours to start",
                "host": OMNIROUTE_HOST}

    if isinstance(_fetch(f"{OMNIROUTE_HOST}/v1/models"), dict):
        return {"started": False, "reason": "already running", "running": True,
                "host": OMNIROUTE_HOST}

    if _boot_in_flight():
        # Someone else is already bringing it up. Wait on theirs rather than
        # adding a second contender for the port.
        ready = _await_omniroute(wait)
        return {"started": False, "running": ready, "host": OMNIROUTE_HOST,
                "reason": "another start already in flight — waited for it"
                          if ready else "another start in flight, still not answering"}

    argv = _omniroute_argv()
    if not argv:
        return {"started": False, "running": False,
                "reason": "not installed — `npm install -g omniroute`"}

    # stdout to a log rather than DEVNULL: when the gateway refuses to come up
    # the reason is in its own output, and discarding it leaves nothing to look
    # at but "still not listening".
    log_path = _state_dir() / "omniroute.log"
    try:
        handle = open(log_path, "ab", buffering=0)
    except OSError:
        handle = subprocess.DEVNULL

    kwargs: dict = {"stdout": handle, "stderr": subprocess.STDOUT,
                    "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        # DETACHED_PROCESS so it does not share our console, and its own
        # process group so a Ctrl-C in Primnox's terminal is not delivered to
        # it as well — that was the whole point of not owning its lifetime.
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
    else:
        kwargs["start_new_session"] = True

    # Claim the boot BEFORE spawning: a lock written afterwards leaves the
    # whole slow startup unguarded, which is precisely the window the race
    # happens in.
    try:
        _boot_lock_path().write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass

    try:
        proc = subprocess.Popen(argv, **kwargs)
    except OSError as exc:
        return {"started": False, "running": False, "reason": f"spawn failed: {exc}"}

    ready = _await_omniroute(wait)
    return {"started": True, "running": ready, "pid": proc.pid,
            "host": OMNIROUTE_HOST, "log": str(log_path),
            "reason": "ready" if ready else f"spawned but not answering within {wait:.0f}s"}


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
    # The URL cannot say whether 127.0.0.1:20128 is a model on this machine or
    # a gateway to somebody else's. `kind` can, and the gate reads it to decide
    # whether the Privacy Mirror applies — so it travels with the rest.
    os.environ["PRIMNOX_PROVIDER_KIND"] = profile.get("kind", "")
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
        # Carried here now that the catalogue payload that used to supply them
        # is gone. Both are small, per-profile, and read on the same screen —
        # a second round trip for two dictionaries was never worth it.
        "notes": notes(),
        "favourites": favourites(),
        "primary": primary_name(),
    }
