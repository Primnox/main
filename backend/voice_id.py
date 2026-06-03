# backend/voice_id.py
from pathlib import Path
import os
import json
from logger import get_logger

log = get_logger("voice_id")

PROFILES_PATH = Path(__file__).parent / "voice_profiles.json"
profiles = {}

# Resemblyzer has been fully disconnected as requested.

def save_profiles():
    pass

def identify_speaker(wav_path):
    log.info("Voice identification disabled (resemblyzer disconnected)")
    return "Unknown", 0.0

def enroll_speaker(wav_path, name):
    log.error("Voice enrollment disabled (resemblyzer disconnected)")
    return False

def get_profiles():
    return []

def delete_profile(name):
    return False

if __name__ == "__main__":
    print("Profiles:", get_profiles())
