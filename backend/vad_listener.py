# backend/vad_listener.py
import threading
import time
import re
import numpy as np
import pyaudiowpatch as pyaudio
from collections import deque
import io
import wave
from brain import transcribe
from logger import get_logger
from settings_manager import load_settings

log = get_logger("vad")

class VADListener:
    def __init__(self, callback=None, ambient_callback=None, state_callback=None):
        self.callback = callback
        self.ambient_callback = ambient_callback
        self.state_callback = state_callback
        self.running = False
        self.lock = threading.Lock()
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.rms_history = deque(maxlen=10)
        self.last_broadcast = 0
        
        # Load settings
        self.settings = load_settings()
        
        # Utterance State
        self.is_recording = False
        self.muted = False
        self.frames = []
        self.silence_start = 0
        # Map sensitivity slider (0.0-1.0) to RMS threshold (0.05-0.005)
        # Higher slider = more sensitive = lower threshold
        sensitivity = float(self.settings.get("vad_sensitivity", 0.5))
        self.SILENCE_THRESHOLD = max(0.005, 0.05 - (sensitivity * 0.045))
        self.SILENCE_DURATION = 0.8     # Secs of silence to end utterance

    def start(self):
        log.info("Starting VADListener thread...")
        self.running = True
        # Refresh settings on start
        self.settings = load_settings()
        sensitivity = float(self.settings.get("vad_sensitivity", 0.5))
        self.SILENCE_THRESHOLD = max(0.005, 0.05 - (sensitivity * 0.045))
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        log.info("Stopping VADListener...")
        self.running = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                log.error(f"Error closing audio stream: {e}")
            self.stream = None
        if self.audio:
            try:
                self.audio.terminate()
            except Exception as e:
                log.error(f"Error terminating PyAudio: {e}")

    def _wrap_wav(self, frames):
        """Wrap raw PCM frames into a WAV container in memory."""
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(b''.join(frames))
        return buf.getvalue()

    def _loop(self):
        try:
            log.debug("Opening audio stream (16kHz, mono)...")
            self.stream = self.audio.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
        except Exception as e:
            log.error(f"Failed to open audio stream: {e}")
            return

        while self.running:
            try:
                data = self.stream.read(1024, exception_on_overflow=False)
                if getattr(self, 'muted', False):
                    time.sleep(0.05)
                    continue
                # Convert to float32 to avoid overflow during squaring
                samples = np.frombuffer(data, np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(samples ** 2)) / 32768
                self.rms_history.append(rms)
                
                now = time.time()
                
                if rms > self.SILENCE_THRESHOLD:
                    if not self.is_recording:
                        log.info(f"Speech started (RMS: {rms:.4f})")
                        self.is_recording = True
                        self.frames = []
                        if self.state_callback:
                            try:
                                self.state_callback("listening")
                            except Exception as e:
                                log.error(f"Failed to trigger state callback (listening): {e}")
                    self.frames.append(data)
                    self.silence_start = 0
                elif self.is_recording:
                    if self.silence_start == 0:
                        self.silence_start = now
                    self.frames.append(data)
                    
                    if now - self.silence_start > self.SILENCE_DURATION:
                        log.info(f"Utterance complete ({len(self.frames)} frames).")
                        self.is_recording = False
                        if self.state_callback:
                            try:
                                self.state_callback("thinking")
                            except Exception as e:
                                log.error(f"Failed to trigger state callback (thinking): {e}")
                        wav_data = self._wrap_wav(self.frames)
                        
                        # Transcribe and check for wake word
                        res = transcribe(wav_data)
                        text = res.get("text", "").strip()
                        
                        if text:
                            low_text = text.lower()
                            # Strip punctuation for cleaner matching
                            clean_low_text = re.sub(r'[^\w\s]', '', low_text)
                            
                            wake_word = self.settings.get("wake_word", "primnox").lower()
                            clean_wake_word = re.sub(r'[^\w\s]', '', wake_word)
                            wake_enabled = self.settings.get("wake_word_enabled", True)

                            # Also accept common misspellings of Primnox since ASR often fails on it
                            fuzzy_wake_words = [
                                clean_wake_word,
                                "hey prim knox", "hey prem knox", "hey premnox", "hey brimnox",
                                "prim knox", "prem knox", "premnox", "brimnox", "rimnox", "prim box",
                                "hey bremnox", "hey primbox"
                            ]

                            is_wake_detected = not wake_enabled or any(fw in clean_low_text for fw in fuzzy_wake_words)

                            if is_wake_detected:
                                # Strip wake word if enabled
                                cleaned_text = text
                                if wake_enabled:
                                    # Just remove whatever matched
                                    for fw in fuzzy_wake_words:
                                        if fw in clean_low_text:
                                            # Case-insensitive replacement of the fuzzy matched word
                                            cleaned_text = re.sub(fw, "", cleaned_text, flags=re.IGNORECASE).strip()
                                            break
                                    # Fallback in case exact regex replacement missed punctuation
                                    cleaned_text = re.sub(r'^(hey[,.]?\s*(primnox|prim knox|prem knox|premnox|brimnox|prim box))[,.]?\s*', '', cleaned_text, flags=re.IGNORECASE).strip()
                                
                                log.info(f"Wake word detected: {wake_word}. Cleaned text: {cleaned_text}")
                                with self.lock:
                                    if self.callback:
                                        try:
                                            self.callback(cleaned_text, wav_data)
                                        except Exception as e:
                                            log.error(f"VAD callback failed: {e}", exc_info=True)
                            else:
                                log.debug(f"Ambient speech: {text}")
                                with self.lock:
                                    if self.ambient_callback:
                                        try:
                                            self.ambient_callback(text)
                                        except Exception as e:
                                            log.error(f"Ambient callback failed: {e}", exc_info=True)
                        
                        self.frames = []
                        self.silence_start = 0
                
            except Exception as e:
                log.error(f"VAD Loop error: {e}")
                time.sleep(0.1)
                
            time.sleep(0.01)

if __name__ == "__main__":
    def on_speech(rms, data):
        print(f"Speech detected! Size: {len(data)} bytes")
    vad = VADListener(callback=on_speech)
    vad.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: pass
    vad.stop()
