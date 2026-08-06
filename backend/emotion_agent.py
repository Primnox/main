import json
import os
from pathlib import Path
from logger import get_logger
from brain import think
from chat_manager import get_all_sessions, get_session_messages

log = get_logger("emotion_agent")

# Use the shared resolver rather than reading APPDATA directly: off Windows
# APPDATA is unset, and Path("") / "primnox_extension" yields a *relative* path
# resolved against the cwd, so settings written by settings_manager were never
# found here.
from settings_manager import get_appdata_dir

SETTINGS_DIR = get_appdata_dir()
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

def run_emotion_analysis():
    """
    Analyzes the user's most recent chat behavior to determine their emotional state.
    Requires >70% confidence to update the system mood.
    """
    log.info("Running Emotion & Behavior Synthesizer...")
    try:
        sessions = get_all_sessions()
        if not sessions:
            return
            
        recent_session = sessions[0]
        msgs = get_session_messages(recent_session["id"])[-20:]
        
        # Only analyze if user has spoken recently
        user_msgs = [m for m in msgs if m["speaker"] != "Primnox"]
        if not user_msgs:
            return
            
        chat_dump = "\n".join([f"{m['speaker']}: {m['text']}" for m in msgs])
        
        prompt = f'''
You are the Primnox Emotion & Behavior Synthesizer.
Analyze the user's recent chat behavior below.
Determine the probability (0-100) of the user experiencing each of the following 6 core emotions:
- Happiness (Joy, contentment)
- Sadness (Grief, disappointment)
- Fear (Anxiety, panic)
- Anger (Frustration, rage)
- Disgust (Revulsion, aversion)
- Surprise (Astonishment, shock)

If the user is just casually chatting with no strong emotion, the highest probability should be low (<50).

Return ONLY raw JSON in this exact format:
{{
  "probabilities": {{
    "Happiness": 10,
    "Sadness": 5,
    "Fear": 0,
    "Anger": 85,
    "Disgust": 20,
    "Surprise": 0,
    "Neutral": 5
  }},
  "dominant_emotion": "Anger",
  "confidence": 85,
  "reasoning": "User is using short, blunt commands and expressing frustration over code."
}}

Chat History:
{chat_dump}
'''
        
        result = think(prompt, system_override="You are an emotion analysis engine. Analyze the conversation tone and output a single emotion label as JSON. No conversation.")
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        
        if content.startswith("`json"): content = content[7:]
        if content.startswith("`"): content = content[3:]
        if content.endswith("`"): content = content[:-3]
            
        data = json.loads(content.strip())
        confidence = data.get("confidence", 0)
        dominant = data.get("dominant_emotion", "Neutral")
        
        log.info(f"Emotion Analysis Complete. Dominant: {dominant} ({confidence}%)")
        
        # Only update if confidence > 70%
        if confidence > 70 and dominant in ["Happiness", "Sadness", "Fear", "Anger", "Disgust", "Surprise", "Neutral"]:
            settings = load_settings()
            settings["current_mood"] = dominant
            save_settings(settings)
            log.info(f"System mood updated to: {dominant}")
            
    except Exception as e:
        log.error(f"Emotion analysis failed: {e}")

if __name__ == "__main__":
    run_emotion_analysis()
