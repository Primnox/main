# backend/settings_manager.py
from database import db_load_settings, db_save_settings
from logger import get_logger

log = get_logger("settings")

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
    try:
        saved_settings = db_load_settings()
        if not saved_settings:
            log.info("Settings not found in database, using defaults.")
            return DEFAULT_SETTINGS.copy()
        
        log.debug("Settings loaded from database.")
        return {**DEFAULT_SETTINGS, **saved_settings}
    except Exception as e:
        log.error(f"Failed to load settings: {e}")
        return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict):
    log.info("Saving settings to database...")
    try:
        merged = {**DEFAULT_SETTINGS, **settings}
        db_save_settings(merged)
        log.info("Settings saved successfully.")
    except Exception as e:
        log.error(f"Failed to save settings: {e}")

if __name__ == "__main__":
    s = load_settings()
    print("Loaded settings:", s)
    s["nickname"] = "primnox"
    save_settings(s)
    print("Settings saved.")
