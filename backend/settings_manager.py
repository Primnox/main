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
    "nickname": "primnox",
    "operator_alias": "ANIKETH_P_01",
    "ai_codename": "PRIMNOX",
    "vad_sensitivity": 0.5,
    "theme": "dark",
    "dynamic_island_enabled": True,
    "wake_word": "hey primnox",
    "wake_word_enabled": True,
    "privacy_mirror_enabled": True,
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
_KEYRING_KEYS = ["groq_api_key", "openai_api_key", "anthropic_api_key"]
_KEYRING_SERVICE = "primnox"


def _keyring_set(key: str, value: str):
    try:
        import keyring
        if value:
            keyring.set_password(_KEYRING_SERVICE, key, value)
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, key)
            except Exception as del_err:
                log.warning(f"keyring delete failed for {key}: {del_err}. Overwriting with empty string as fallback.")
                # delete_password failed — overwrite with "" so _keyring_get (which
                # returns `get_password(...) or ""`) treats it as absent. This prevents
                # a stale key from resurrecting after the user explicitly cleared it.
                try:
                    keyring.set_password(_KEYRING_SERVICE, key, "")
                except Exception:
                    log.warning(f"keyring overwrite also failed for {key}. Old key may persist.")
    except Exception as e:
        log.debug(f"keyring write skipped ({key}): {e}")


def _keyring_get(key: str) -> str:
    try:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, key) or ""
    except Exception:
        return ""


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

        # Only auto-complete onboarding when settings.json existed on disk (partial key loss
        # after a minor update). Do NOT fire on a fully-wiped reinstall — that should show
        # onboarding fresh even if the keyring still has an old API key.
        any_api_key = any(merged.get(k) for k in _KEYRING_KEYS)
        if settings_file_existed and any_api_key and not merged.get("onboarding_completed"):
            log.info("API key present but onboarding_completed=False — marking complete (post-update recovery).")
            merged["onboarding_completed"] = True

        return merged


def save_settings(settings: dict):
    with _settings_lock:
        log.info("Saving settings to APPDATA...")
        merged = {**DEFAULT_SETTINGS, **settings}
        try:
            tmp_path = str(SETTINGS_PATH) + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
            os.replace(tmp_path, SETTINGS_PATH)
            log.info("Settings saved to APPDATA.")
        except Exception as e:
            log.error(f"Failed to save settings to APPDATA: {e}")

        # Mirror API keys to keyring — these survive NSIS reinstalls and APPDATA resets
        for k in _KEYRING_KEYS:
            _keyring_set(k, merged.get(k, ""))

if __name__ == "__main__":
    s = load_settings()
    print("Loaded settings:", s)
    s["nickname"] = "primnox"
    save_settings(s)
    print("Settings saved.")
