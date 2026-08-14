"""Set the API key for the active provider, without hand-editing JSON.

Run it, paste the key, done:

    backend\\venv\\Scripts\\python.exe v2\\backend\\set_key.py

The key is read straight from the terminal into the settings file. It is not
echoed, not logged, and not passed as a command-line argument — an argument
would end up in shell history and in the process list, which is exactly how
keys leak on a shared machine.

Writes are atomic: the new file is written alongside and then swapped in, so a
crash mid-write cannot leave you with a truncated settings.json and a broken
app.
"""
from __future__ import annotations

import getpass
import json
import os
import shutil
import sys
from pathlib import Path


def settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "primnox_extension" if appdata else Path.home() / ".primnox_extension"
    return base / "settings.json"


def describe_target(s: dict) -> tuple[str, str]:
    """Which provider entry the key belongs to, and a human label for it."""
    active = s.get("active_model", "")
    if active == "Custom":
        wanted = s.get("active_custom_provider_id", "")
        for p in s.get("custom_providers", []):
            if p.get("id") == wanted:
                return "custom", f'{p.get("name") or p.get("id")} → {p.get("base_url")} ({p.get("model")})'
        return "custom_missing", wanted
    mapping = {
        "Anthropic": "anthropic_api_key",
        "OpenAI_GPT_4o": "openai_api_key",
        "Groq_Llama_3": "groq_api_key",
    }
    field = mapping.get(active)
    return (field, active) if field else ("unknown", active)


def main() -> int:
    path = settings_path()
    if not path.is_file():
        print(f"No settings file at {path}", file=sys.stderr)
        return 1

    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"settings.json is not valid JSON ({exc}). Fix it before running this.",
              file=sys.stderr)
        return 1

    target, label = describe_target(settings)
    if target == "custom_missing":
        print(f"active_custom_provider_id is {label!r} but no such profile exists.",
              file=sys.stderr)
        return 1
    if target == "unknown":
        print(f"Don't know where the key goes for active_model={label!r}.", file=sys.stderr)
        return 1

    print(f"Settings file : {path}")
    print(f"Active provider: {label}")
    print()

    key = getpass.getpass("Paste the API key (input hidden, then press Enter): ").strip()
    if not key:
        print("Nothing entered — no changes made.")
        return 1
    if len(key) < 8:
        print("That looks too short to be a key — no changes made.", file=sys.stderr)
        return 1

    if target == "custom":
        wanted = settings.get("active_custom_provider_id")
        for p in settings.get("custom_providers", []):
            if p.get("id") == wanted:
                p["api_key"] = key
    else:
        settings[target] = key

    # Back up, then write atomically via a temp file + replace.
    backup = path.with_suffix(".json.bak")
    shutil.copy2(path, backup)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    tmp.replace(path)

    print(f"\nSaved. {len(key)} characters written, ending ...{key[-4:]}")
    print(f"Previous file backed up to {backup.name}")
    print("\nRestart the V2 backend, then send a message.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
