import json
import os
from pathlib import Path
from logger import get_logger
from brain import think
from memory import list_memories

log = get_logger("profiler")

SETTINGS_DIR = Path(os.getenv("APPDATA", "")) / "primnox_extension"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_settings(settings):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=4), encoding="utf-8")

def run_background_profiler():
    """
    Scans recent memories and chats to deduce the user's occupation, projects, and learning style.
    Updates the onboarding_profile in settings.json.
    """
    log.info("Running background Automated Notes Learning Profiler...")
    try:
        memories = list_memories()
        recent_texts = [m["text"][:200] for m in memories[-10:]]  # Look at the last 10 memories (truncated)
        
        if not recent_texts:
            log.info("Not enough data to profile user yet.")
            return

        memory_dump = "\n".join([f"- {text}" for text in recent_texts])
        
        prompt = f'''
You are a Learning Style Profiler. Based on the user's recent thoughts and notes below, deduce their exact user profile.
Return a valid JSON object with EXACTLY these keys:
{{
  "occupation": "e.g. Computer Science Student, Software Engineer, Designer",
  "learning_style": "e.g. Visual Learner, Hands-on, Prefers dense text",
  "current_projects": ["List of 2-3 current things they are working on"],
  "recommended_notes_style": "A brief sentence on how notes should be structured for this user (e.g. 'Use bullet points and code blocks')"
}}

User Memories:
{memory_dump}

Respond with ONLY raw JSON. No markdown fences.
'''
        
        result = think(prompt, system_override="You are a JSON data extractor. Output only valid JSON matching the requested schema. No conversation.")
        if "error" in result:
            log.error(f"Profiler brain error: {result['error']}")
            return None
            
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            log.error("Profiler failed: No content returned from brain.")
            return None
        
        # Strip markdown fences if AI included them anyway
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        profile_data = json.loads(content.strip())
        
        settings = load_settings()
        
        # Merge with existing onboarding_profile
        existing_profile = settings.get("onboarding_profile", {})
        existing_profile["dynamic_profiling"] = profile_data
        
        settings["onboarding_profile"] = existing_profile
        save_settings(settings)
        
        log.info(f"Profiler updated successfully: {profile_data.get('occupation')}")
        return profile_data
        
    except Exception as e:
        log.error(f"Profiler failed: {e}")
        return None

if __name__ == "__main__":
    run_background_profiler()
