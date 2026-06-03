# backend/voice_id.py
from pathlib import Path
from resemblyzer import VoiceEncoder, preprocess_wav
import numpy as np
import os
import json
from logger import get_logger

log = get_logger("voice_id")

PROFILES_PATH = Path(__file__).parent / "voice_profiles.json"
encoder = None
profiles = {}

# Load encoder once
if encoder is None:
    log.info("Loading Resemblyzer VoiceEncoder...")
    encoder = VoiceEncoder()

# Load profiles
if PROFILES_PATH.exists():
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            profiles = json.load(f)
        log.info(f"Loaded {len(profiles)} voice profiles.")
    except Exception as e:
        log.error(f"Failed to load voice profiles: {e}")
        profiles = {}
else:
    profiles = {}

def save_profiles():
    try:
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2)
        log.debug("Voice profiles saved to disk.")
    except Exception as e:
        log.error(f"Failed to save voice profiles: {e}")

def identify_speaker(wav_path):
    log.debug(f"Identifying speaker from {wav_path}...")
    try:
        wav = preprocess_wav(wav_path)
        emb = encoder.embed_utterance(wav)
        best, best_score = None, 0.0
        for name, vec in profiles.items():
            score = np.dot(emb, np.array(vec)) / (np.linalg.norm(emb) * np.linalg.norm(vec))
            if score > best_score:
                best, best_score = name, score
        
        if best_score > 0.75:
            log.info(f"Speaker identified: {best} (score: {best_score:.4f})")
            return best, best_score
        
        log.info(f"Speaker unknown (best score: {best_score:.4f})")
        return "Unknown", best_score
    except Exception as e:
        log.error(f"Speaker identification failed: {e}")
        return "Error", 0.0

def enroll_speaker(wav_path, name):
    log.info(f"Enrolling speaker: {name} from {wav_path}")
    try:
        wav = preprocess_wav(wav_path)
        emb = encoder.embed_utterance(wav)
        profiles[name] = emb.tolist()
        save_profiles()
        log.info(f"Speaker {name} enrolled successfully.")
        return True
    except Exception as e:
        log.error(f"Enrollment failed: {e}")
        return False

def get_profiles():
    return list(profiles.keys())

def delete_profile(name):
    if name in profiles:
        log.info(f"Deleting profile: {name}")
        del profiles[name]
        save_profiles()
        return True
    log.warning(f"Profile {name} not found for deletion.")
    return False

if __name__ == "__main__":
    print("Profiles:", get_profiles())
