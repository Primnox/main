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
    "nickname": "primnox",
    "operator_alias": "ANIKETH_P_01",
    "ai_codename": "PRIMNOX",
    "vad_sensitivity": 0.5,
    "theme": "dark",
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
    "onboarding_profile": {
        "projects": [],
        "topics": [],
        "skills": [],
        "communication_style": [],
        "knowledge_areas": []
    }
}

def load_settings():
    with _settings_lock:
        if not SETTINGS_PATH.exists():
            log.info("Settings file not found, using defaults.")
            return DEFAULT_SETTINGS.copy()
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            log.debug("Settings loaded from disk.")
            return {**DEFAULT_SETTINGS, **data}
        except Exception as e:
            log.error(f"Failed to load settings: {e}")
            return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict):
    with _settings_lock:
        log.info("Saving settings to disk...")
        merged = {**DEFAULT_SETTINGS, **settings}
        try:
            # Atomic write: write to temp file first, then replace
            tmp_path = str(SETTINGS_PATH) + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
            os.replace(tmp_path, SETTINGS_PATH)
            log.info("Settings saved successfully.")
        except Exception as e:
            log.error(f"Failed to save settings: {e}")

if __name__ == "__main__":
    s = load_settings()
    print("Loaded settings:", s)
    s["nickname"] = "primnox"
    save_settings(s)
    print("Settings saved.")
