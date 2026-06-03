# backend/voice.py
import edge_tts
import asyncio
import pygame
import os
import glob
import threading
import time
from pathlib import Path
from logger import get_logger

log = get_logger("voice")

# Voice for PRIMNOX
VOICE = "en-US-AriaNeural" 

_state_callback = None

def register_state_callback(cb):
    global _state_callback
    _state_callback = cb

def _cleanup_old_tts_files():
    """Remove any leftover resp_*.mp3 files from previous sessions."""
    try:
        for f in glob.glob("resp_*.mp3"):
            try:
                os.remove(f)
            except Exception:
                pass
    except Exception:
        pass

async def speak_async(text):
    if _state_callback:
        try:
            _state_callback("speaking")
        except Exception as e:
            log.error(f"Failed to trigger state callback (speaking): {e}")

    # Use unique filename to avoid permission denied errors (file locks)
    filename = f"resp_{int(time.time() * 1000)}.mp3"
    log.debug(f"Generating TTS for: {text[:50]}...")
    try:
        communicate = edge_tts.Communicate(text, VOICE)
        await communicate.save(filename)
        
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            log.error(f"TTS generation failed: {filename} is empty or missing.")
            if _state_callback:
                try:
                    _state_callback("idle")
                except Exception:
                    pass
            return

        log.debug("Playing audio via pygame...")
        pygame.mixer.init()
        try:
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
            pygame.mixer.music.unload() # Crucial for releasing the lock
        finally:
            pygame.mixer.quit()
            if _state_callback:
                try:
                    _state_callback("idle")
                except Exception as e:
                    log.error(f"Failed to trigger state callback (idle): {e}")
            
        # Cleanup
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            log.error(f"Cleanup error for {filename}: {e}")
            
    except Exception as e:
        log.error(f"TTS Async Error: {e}", exc_info=True)
        if _state_callback:
            try:
                _state_callback("idle")
            except Exception:
                pass

def _speak_worker(text):
    """Worker function for the speech thread."""
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(speak_async(text))
        loop.close()
    except Exception as e:
        log.error(f"Error in voice worker thread: {e}")

def speak(text):
    """Sync wrapper that spawns a thread to avoid event loop conflicts."""
    if not text or len(text.strip()) < 2:
        return
    
    # Strip out any system tokens the LLM may have injected
    import re
    text = re.sub(r'\[NAVIGATE:.*?\]', '', text).strip()
    text = re.sub(r'\[SYSTEM:.*?\]', '', text).strip()
    if not text:
        return
        
    log.info(f"PRIMNOX speaking: {text}")
    # Start in a daemon thread to avoid blocking FastAPI
    threading.Thread(target=_speak_worker, args=(text,), daemon=True).start()

# Cleanup old TTS files on module load
_cleanup_old_tts_files()

if __name__ == "__main__":
    speak("hello there. i am primnox. systems are nominal.")
    import time
    time.sleep(5)
