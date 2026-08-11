# backend/settings_manager.py
from pathlib import Path
import json
import os
import threading
from logger import get_logger

log = get_logger("settings")

import os

def get_appdata_dir():
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "primnox_extension"
    else:
        base = Path.home() / ".primnox_extension"
    base.mkdir(parents=True, exist_ok=True)
    return base

SETTINGS_PATH = get_appdata_dir() / "settings.json"
_settings_lock = threading.Lock()
DEFAULT_SETTINGS = {
    "groq_api_key": "",
    "openai_api_key": "",
    "anthropic_api_key": "",
    "active_model": "Groq_Llama_3",
    "ollama_model": "llama3.2",
    "ollama_base_url": "http://localhost:11434",
    "llamacpp_base_url": "http://localhost:8080",
    "llamacpp_model": "",
    "gemini_api_key": "",
    # Which specific model to use within a preset provider. Empty string means
    # "use the built-in default" (see brain.py's hardcoded fallbacks) — lets
    # existing users who never touch this keep today's exact behavior.
    "openai_model": "",
    "anthropic_model": "",
    "groq_model": "",
    "gemini_model": "gemini-2.0-flash",
    # Voice-synthesis model preference per provider, picked in Knowledge Nexus's
    # Model Library. Saved for later — NOT yet wired to actual audio output,
    # which still goes through voice.py's hardcoded edge_tts call. This is
    # "remember the choice", not "change what you hear", until a follow-up
    # pass wires real cloud TTS playback.
    "groq_tts_model": "",
    "openai_tts_model": "",
    "anthropic_tts_model": "",
    "gemini_tts_model": "",
    # Custom providers — any number of named, saved OpenAI-compatible or
    # Anthropic-compatible endpoints (vLLM, LM Studio, OpenRouter, a
    # self-hosted proxy, etc.), each: {id, name, api_type, base_url, api_key,
    # model}. Whether a given profile counts as "local" (skip Privacy Mirror)
    # is auto-detected from its base_url being localhost/127.0.0.1 — see
    # brain.py's _is_local_provider(). "active_custom_provider_id" selects
    # which saved profile is in use when active_model == "Custom".
    "custom_providers": [],
    "active_custom_provider_id": "",
    # Sandboxed code execution (run_python/run_shell tools, see code_exec.py).
    # Default OFF — an extra gate beyond the mandatory per-call Allow/Deny
    # prompt; the tools aren't even offered to the model unless this is true.
    # "sandbox_account_ready" mirrors sandbox_account.sandbox_account_configured()
    # so the Settings UI doesn't need a live Windows API call on every load.
    "code_execution_enabled": False,
    "sandbox_account_ready": False,
    "nickname": "primnox",
    "operator_alias": "Operator",   # placeholder; onboarding asks for the real name
    "ai_codename": "PRIMNOX",
    "vad_sensitivity": 0.5,
    "theme": "dark",
    "dynamic_island_enabled": True,
    "wake_word": "hey primnox",
    "wake_word_enabled": True,
    "privacy_mirror_enabled": True,   # privacy-first: scrub PII on cloud calls by default
    "blocklist": [],
    "screenshot_retention": 10,
    "memory_auto_delete_days": 30,
    "response_length": "normal",
    "stt_language": "en",
    "startup_with_windows": False,
    "debug_mode": False,
    "voice_feedback": True,
    "onboarding_completed": False,
    "access_permissions": ["Documents", "Projects", "Notes"],
    "interaction_mode": "vad",
    "adaptive_communication": True,
    "memory_mode": "smart",
    "personalization_options": [
        "Vocabulary Learning", "Slang Learning", "Writing Style Matching",
        "Research Style Learning", "Productivity Pattern Learning", "Response Depth Adaptation"
    ],
    "workspaces": ["Personal Workspace", "Development Workspace", "Research Workspace"],
    # Calendar providers — each entry is a provider config dict.
    # Supported types: "ical" | "google" | "outlook" | "notion"
    # Example iCal entry:
    #   {"type": "ical", "name": "My Calendar", "url": "https://...", "color": "#6366f1"}
    "calendar_providers": [],
    "onboarding_profile": {
        "projects": [],
        "topics": [],
        "skills": [],
        "communication_style": [],
        "knowledge_areas": []
    }
}

# Keys stored in Windows Credential Manager / keyring as a backup layer
_KEYRING_KEYS = ["groq_api_key", "openai_api_key", "anthropic_api_key", "gemini_api_key"]
_KEYRING_SERVICE = "primnox"


def _keyring_set(key: str, value: str) -> bool:
    """Returns True if the keyring write/delete succeeded, False otherwise."""
    try:
        import keyring
        if value:
            keyring.set_password(_KEYRING_SERVICE, key, value)
            return True
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, key)
                return True
            except Exception as del_err:
                log.warning(f"keyring delete failed for {key}: {del_err}. Overwriting with empty string as fallback.")
                # delete_password failed — overwrite with "" so _keyring_get (which
                # returns `get_password(...) or ""`) treats it as absent. This prevents
                # a stale key from resurrecting after the user explicitly cleared it.
                try:
                    keyring.set_password(_KEYRING_SERVICE, key, "")
                    return True
                except Exception:
                    log.warning(f"keyring overwrite also failed for {key}. Old key may persist.")
                    return False
    except Exception as e:
        log.debug(f"keyring write skipped ({key}): {e}")
        return False


def _keyring_get(key: str) -> str:
    try:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, key) or ""
    except Exception:
        return ""


def delete_custom_provider_key(profile_id: str) -> None:
    """Wipes a deleted custom-provider profile's mirrored keyring entry so it
    doesn't linger forever once the profile itself is removed from settings."""
    _keyring_set(f"custom_provider_{profile_id}", "")


def load_settings():
    with _settings_lock:
        data = {}
        # Track whether settings.json exists BEFORE we read it.
        # A missing file means a fresh or fully-wiped install — we should NOT
        # auto-complete onboarding just because a stale keyring key exists.
        settings_file_existed = SETTINGS_PATH.exists()

        if not settings_file_existed:
            log.info("Settings file not found in APPDATA — checking keyring for API keys.")
        else:
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                log.debug("Settings loaded from APPDATA.")
            except Exception as e:
                log.error(f"Failed to load settings from APPDATA: {e}")

        merged = {**DEFAULT_SETTINGS, **data}

        # Fill in any missing API keys from keyring (survives app updates / reinstalls)
        for k in _KEYRING_KEYS:
            if not merged.get(k):
                val = _keyring_get(k)
                if val:
                    log.info(f"Restored {k} from keyring.")
                    merged[k] = val

        # One-time migration: older versions stored a single anonymous custom
        # endpoint as flat custom_base_url/custom_api_type/custom_api_key/
        # custom_model fields. Fold it into the new named-profile list so
        # existing configs carry over instead of silently vanishing.
        if not merged.get("custom_providers") and data.get("custom_base_url"):
            import uuid
            profile_id = uuid.uuid4().hex[:8]
            merged["custom_providers"] = [{
                "id": profile_id,
                "name": "Custom",
                "api_type": data.get("custom_api_type", "openai"),
                "base_url": data.get("custom_base_url", ""),
                "api_key": data.get("custom_api_key", ""),
                "model": data.get("custom_model", ""),
            }]
            merged["active_custom_provider_id"] = profile_id
            log.info("Migrated legacy custom_base_url settings into custom_providers[0].")

        # Restore any per-profile API keys mirrored to keyring (same reasoning
        # as the flat _KEYRING_KEYS loop above — survives app updates/reinstalls).
        for profile in merged.get("custom_providers", []):
            if not profile.get("api_key") and profile.get("id"):
                val = _keyring_get(f"custom_provider_{profile['id']}")
                if val:
                    profile["api_key"] = val

        # Only auto-complete onboarding when settings.json existed on disk (partial key loss
        # after a minor update). Do NOT fire on a fully-wiped reinstall — that should show
        # onboarding fresh even if the keyring still has an old API key.
        # Only recover when the flag is ABSENT from the file. Testing `not
        # merged.get(...)` also matched an explicit `false`, so once any API key
        # existed the flag was forced back to True on every load and onboarding
        # could never be re-run — there was no way to reset it at all.
        any_api_key = any(merged.get(k) for k in _KEYRING_KEYS)
        if settings_file_existed and any_api_key and "onboarding_completed" not in data:
            log.info("API key present but onboarding_completed missing — marking complete (post-update recovery).")
            merged["onboarding_completed"] = True

        return merged


def save_settings(settings: dict):
    with _settings_lock:
        log.info("Saving settings to APPDATA...")
        merged = {**DEFAULT_SETTINGS, **settings}

        # Mirror API keys to keyring — these survive NSIS reinstalls and APPDATA resets.
        # Only scrub a key from the on-disk JSON if the keyring write actually
        # succeeded; otherwise keep it in the file as a fallback so the key
        # isn't lost on platforms without a working keyring backend (e.g.
        # some Linux setups with no secret service running).
        to_write = dict(merged)
        for k in _KEYRING_KEYS:
            if _keyring_set(k, merged.get(k, "")):
                to_write[k] = ""

        # Mirror each custom-provider's API key to keyring individually (they're
        # dynamic, per-profile secrets — not fixed top-level keys, so they can't
        # go through the _KEYRING_KEYS loop above).
        if merged.get("custom_providers"):
            written_profiles = []
            for profile in merged["custom_providers"]:
                profile = dict(profile)
                pid = profile.get("id")
                if pid and _keyring_set(f"custom_provider_{pid}", profile.get("api_key", "")):
                    profile["api_key"] = ""
                written_profiles.append(profile)
            to_write["custom_providers"] = written_profiles

        try:
            tmp_path = str(SETTINGS_PATH) + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(to_write, f, indent=2)
            os.replace(tmp_path, SETTINGS_PATH)
            log.info("Settings saved to APPDATA.")
        except Exception as e:
            log.error(f"Failed to save settings to APPDATA: {e}")

if __name__ == "__main__":
    s = load_settings()
    print("Loaded settings:", s)
    s["nickname"] = "primnox"
    save_settings(s)
    print("Settings saved.")
