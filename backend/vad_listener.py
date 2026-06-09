# backend/vad_listener.py
import sys
import threading
import time
import re
import numpy as np
import sounddevice as sd
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
        self._thread: threading.Thread | None = None
        self.lock = threading.Lock()
        self.rms_history = deque(maxlen=10)
        self.last_broadcast = 0

        # Load settings
        self.settings = load_settings()

        # Utterance state
        self.is_recording = False
        self.muted = False
        self.frames: list[bytes] = []
        self.silence_start = 0.0

        # Map sensitivity slider (0.0-1.0) → RMS threshold (0.05-0.005)
        sensitivity = float(self.settings.get("vad_sensitivity", 0.5))
        self.SILENCE_THRESHOLD = max(0.005, 0.05 - (sensitivity * 0.045))
        self.SILENCE_DURATION = 0.8  # seconds of silence to end utterance
        self.SAMPLE_RATE = 16000
        self.CHUNK = 1024

    def start(self):
        log.info("Starting VADListener thread...")
        self.running = True
        # Refresh settings on start
        self.settings = load_settings()
        sensitivity = float(self.settings.get("vad_sensitivity", 0.5))
        self.SILENCE_THRESHOLD = max(0.005, 0.05 - (sensitivity * 0.045))
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        log.info("Stopping VADListener...")
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            self._thread = None

    def _wrap_wav(self, frames: list[bytes]) -> bytes:
        """Wrap raw PCM frames into a WAV container in memory."""
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(b''.join(frames))
        return buf.getvalue()

    def _loop(self):
        try:
            log.debug("Opening audio stream (16kHz, mono)...")
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype='int16',
                blocksize=self.CHUNK,
            ) as stream:
                while self.running:
                    try:
                        data, _ = stream.read(self.CHUNK)

                        if getattr(self, 'muted', False):
                            time.sleep(0.05)
                            continue

                        samples = data.flatten().astype(np.float32)
                        rms = float(np.sqrt(np.mean(samples ** 2)) / 32768)
                        self.rms_history.append(rms)

                        now = time.time()
                        raw_bytes = data.tobytes()

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
                            self.frames.append(raw_bytes)
                            self.silence_start = 0.0

                        elif self.is_recording:
                            if self.silence_start == 0.0:
                                self.silence_start = now
                            self.frames.append(raw_bytes)

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
                                    clean_low_text = re.sub(r'[^\w\s]', '', low_text)

                                    wake_word = self.settings.get("wake_word", "primnox").lower()
                                    clean_wake_word = re.sub(r'[^\w\s]', '', wake_word)
                                    wake_enabled = self.settings.get("wake_word_enabled", True)

                                    fuzzy_wake_words = [
                                        clean_wake_word,
                                        "hey prim knox", "hey prem knox", "hey premnox", "hey brimnox",
                                        "prim knox", "prem knox", "premnox", "brimnox", "rimnox", "prim box",
                                        "hey bremnox", "hey primbox",
                                    ]

                                    is_wake_detected = (
                                        not wake_enabled
                                        or any(fw in clean_low_text for fw in fuzzy_wake_words)
                                    )

                                    if is_wake_detected:
                                        cleaned_text = text
                                        if wake_enabled:
                                            for fw in fuzzy_wake_words:
                                                if fw in clean_low_text:
                                                    cleaned_text = re.sub(fw, "", cleaned_text, flags=re.IGNORECASE).strip()
                                                    break
                                            cleaned_text = re.sub(
                                                r'^(hey[,.]?\s*(primnox|prim knox|prem knox|premnox|brimnox|prim box))[,.]?\s*',
                                                '',
                                                cleaned_text,
                                                flags=re.IGNORECASE,
                                            ).strip()

                                        log.info(f"Wake word detected: {wake_word}. Cleaned: {cleaned_text}")
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
                                self.silence_start = 0.0

                    except Exception as e:
                        log.error(f"VAD loop error: {e}")
                        time.sleep(0.1)

                    time.sleep(0.01)

        except Exception as e:
            log.error(f"Failed to open audio stream: {e}")
            self.running = False  # caller can detect VAD never started


if __name__ == "__main__":
    def on_speech(text, data):
        print(f"Speech: {text!r}  ({len(data)} bytes)")
    vad = VADListener(callback=on_speech)
    vad.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    vad.stop()
