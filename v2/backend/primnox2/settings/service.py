"""Runtime settings.

Changing the model or the permission mode should not mean editing a dotfile and
restarting — that is the state this project spent an evening stuck in, and a
settings file you have to find is a settings file nobody finds.

Two rules shape everything here.

SECRETS DO NOT GO IN THE DATABASE. `schema.sql` says so on the settings table
and it is not decoration: primnox.db is copied for backups, opened in DB
browsers, and attached to bug reports. The API key is written to `v2/.env`,
which is gitignored, and is never returned by any read — only whether one is
present. A settings screen that shows you your own key is a settings screen
that shows it to whoever is behind you.

ENVIRONMENT VARIABLES STILL WIN. `gateway.active_provider()` reads os.environ,
and a real environment variable set on the command line must keep beating a
stored value — otherwise a saved setting silently overrides the thing an
operator did deliberately, and there is no way to tell. Stored settings are
applied by exporting them into the environment at boot, BEFORE the process
reads anything, and only where the variable is not already set.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from ..storage import db

now_ms = lambda: int(time.time() * 1000)

# Where a non-secret setting lands in the environment. Only keys in this map are
# settable: an open key/value store reachable over HTTP is a way to set
# arbitrary environment variables on the host, which is a much larger thing than
# a settings screen.
ENV_KEYS = {
    "provider.base_url": "PRIMNOX_BASE_URL",
    "provider.api_type": "PRIMNOX_API_TYPE",
    "provider.model": "PRIMNOX_MODEL",
    "provider.force_echo": "PRIMNOX_PROVIDER",
    "sandbox.auto_approve": "PRIMNOX2_AUTO_APPROVE",
    "diagnostics.trace": "PRIMNOX2_TRACE",
    "privacy.mirror_enabled": "PRIMNOX2_PRIVACY_MIRROR",
    "model.thinking_enabled": "PRIMNOX2_THINKING",
}

# Values a setting is allowed to take, where the set is closed. Free text would
# let a typo ("saf") silently become "prompt for everything", which looks like
# the app is broken rather than like a typo.
ALLOWED = {
    "provider.api_type": {"anthropic", "openai"},
    "sandbox.auto_approve": {"all", "safe", "off"},
    # Defaults to "on" — see gateway._scrub_outbound()'s settings_service.get()
    # call, whose default is "on" for the same reason: an absent setting must
    # fail toward privacy, not away from it.
    "privacy.mirror_enabled": {"on", "off"},
    # Off by default, unlike privacy.mirror_enabled: enabling this changes the
    # request itself (Anthropic's `thinking` parameter), not just what happens
    # to it afterward, and a model that does not support it answers with a 400
    # rather than ignoring the field. There is no safe universal default here —
    # only the user knows whether the model they picked actually supports it.
    "model.thinking_enabled": {"on", "off"},
}

SECRET_KEYS = {"provider.api_key"}

# In dev, v2/.env. In a frozen build there is no dev tree to be relative to —
# __file__ resolves inside PyInstaller's per-launch extraction temp dir, which
# is both wrong (nothing three parents up from there) and wiped on every
# restart, which matters here specifically because set_api_key() WRITES this
# file — losing it on the next launch would mean the key silently vanishes.
# Next to the installed executable instead, mirroring models/gateway.py's
# _load_env_file() and privacy/mirror.py's _resolve_model_source().
ENV_FILE = (Path(sys.executable).resolve().parent / ".env" if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[3] / ".env")


# ── Store ────────────────────────────────────────────────────────────────────
def all_settings() -> dict:
    rows = db.connect().execute("SELECT key, value FROM settings")
    out: dict = {}
    for r in rows:
        try:
            out[r["key"]] = json.loads(r["value"])
        except Exception:
            out[r["key"]] = r["value"]
    return out


def get(key: str, default=None):
    return all_settings().get(key, default)


def set_many(values: dict) -> dict:
    """Store non-secret settings and apply them to the live process.

    Applied immediately as well as stored, because `active_provider()` reads the
    environment on every call — so a model change takes effect on the next turn
    rather than on the next restart.
    """
    stored, rejected = {}, {}
    for key, value in values.items():
        if key in SECRET_KEYS:
            rejected[key] = "secrets are not stored in the database"
            continue
        if key not in ENV_KEYS:
            rejected[key] = "unknown setting"
            continue
        text = "" if value is None else str(value).strip()
        allowed = ALLOWED.get(key)
        if allowed and text and text not in allowed:
            rejected[key] = f"must be one of {sorted(allowed)}"
            continue
        stored[key] = text

    if stored:
        ts = now_ms()
        with db.tx() as c:
            for key, text in stored.items():
                c.execute(
                    "INSERT INTO settings (key,value,updated_at) VALUES (?,?,?)"
                    " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                    "                                updated_at=excluded.updated_at",
                    (key, json.dumps(text), ts),
                )
        for key, text in stored.items():
            env = ENV_KEYS[key]
            if text:
                os.environ[env] = text
            else:
                os.environ.pop(env, None)

    return {"stored": stored, "rejected": rejected}


def apply_to_environment() -> list[str]:
    """Export stored settings into os.environ. Called once, at boot.

    Does not overwrite a variable that is already set: a real environment
    variable is something an operator did on purpose, and it must outrank a
    value saved in the UI months ago.
    """
    applied = []
    for key, value in all_settings().items():
        env = ENV_KEYS.get(key)
        if not env or not value:
            continue
        if os.environ.get(env):
            continue
        os.environ[env] = str(value)
        applied.append(env)
    return applied


# ── The key ──────────────────────────────────────────────────────────────────
def has_api_key() -> bool:
    return bool(os.getenv("PRIMNOX_API_KEY", "").strip())


def set_api_key(key: str) -> bool:
    """Write the key to v2/.env and apply it to the running process.

    Written atomically — a new file alongside, then swapped in — so a crash
    mid-write cannot leave a truncated .env and an app that will not start.
    """
    key = (key or "").strip()
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = [ln for ln in ENV_FILE.read_text(encoding="utf-8").splitlines()
                 if not ln.strip().startswith("PRIMNOX_API_KEY=")]
    if key:
        lines.append(f"PRIMNOX_API_KEY={key}")

    tmp = ENV_FILE.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(ENV_FILE)

    if key:
        os.environ["PRIMNOX_API_KEY"] = key
    else:
        os.environ.pop("PRIMNOX_API_KEY", None)
    return True


# ── What the UI shows ────────────────────────────────────────────────────────
def describe() -> dict:
    """Current settings plus enough status to answer "why is it doing that".

    The key is reported as present/absent and never returned.
    """
    from ..models import gateway
    from ..sandbox import supervisor
    from ..storage import db as storage

    stored = all_settings()
    effective = {key: os.getenv(env, "") for key, env in ENV_KEYS.items()}

    try:
        _, model = gateway.active_provider()
    except Exception:
        model = "unavailable"
    try:
        backend = supervisor.available_backend() or "none — execution refused"
    except Exception:
        backend = "unknown"
    try:
        from ..privacy import mirror
        privacy_model = mirror.model_status()
    except Exception:
        privacy_model = "unavailable"

    return {
        "stored": stored,
        "effective": effective,
        "allowed": {k: sorted(v) for k, v in ALLOWED.items()},
        "api_key_present": has_api_key(),
        "env_file": str(ENV_FILE),
        "status": {
            "model": model,
            "sandbox": backend,
            "database": str(getattr(storage, "_db_path", "") or ""),
            "schema_version": storage.SCHEMA_VERSION,
            "privacy_model": privacy_model,
        },
    }
