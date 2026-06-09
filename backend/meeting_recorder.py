# backend/meeting_recorder.py
import sys
import threading
import time
import wave
import subprocess
from pathlib import Path
import psutil
from brain import think
from logger import get_logger

log = get_logger("recorder")

PLATFORM = sys.platform  # 'win32', 'darwin', 'linux'

MEETING_APPS = ["zoom", "teams", "slack", "meet", "webex", "discord"]


class MeetingRecorder:
    def __init__(self):
        self.running = False
        self.active_meeting = False
        self.thread = None
        self.base_dir = Path.home() / "Documents" / "Primnox" / "Meetings"
        self.current_meeting_dir = None
        self.audio_frames: list[bytes] = []
        self.audio_stream = None
        self.p = None  # pyaudiowpatch instance (Windows only)
        self._pyaudio_mod = None        # pyaudiowpatch module ref (Windows only)
        self._sd_stop_event: threading.Event | None = None
        self._sd_thread: threading.Thread | None = None
        self.capture_channels = 2
        self.capture_rate = 44100

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self):
        if self.running:
            return
        log.info("Starting MeetingRecorder thread...")
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        log.info("Stopping MeetingRecorder...")
        self.running = False
        if self.thread:
            self.thread.join()

    # ── Meeting detection ──────────────────────────────────────────────────────

    def is_meeting_active(self) -> bool:
        """Cross-platform: a meeting app must be running AND in the foreground.
        Checking only the foreground window prevents background Discord/Slack
        from triggering continuous recording."""
        try:
            # Fast pre-check: any meeting app running at all?
            running = any(
                any(app in (p.info.get('name') or '').lower() for app in MEETING_APPS)
                for p in psutil.process_iter(['name'])
            )
            if not running:
                return False
            # Expensive check only when a candidate is running:
            # verify it is actually the active/foreground window.
            from screen_reader import _get_foreground_win, _get_foreground_mac, _get_foreground_linux
            if PLATFORM == 'win32':
                _, process = _get_foreground_win()
            elif PLATFORM == 'darwin':
                _, process = _get_foreground_mac()
            else:
                _, process = _get_foreground_linux()
            return any(app in process.lower() for app in MEETING_APPS)
        except Exception:
            pass
        return False

    # ── Screenshot ─────────────────────────────────────────────────────────────

    def _capture_screenshot(self, fname: Path) -> None:
        """Take a full-screen screenshot, platform-aware."""
        try:
            if PLATFORM in ('win32', 'darwin'):
                from PIL import ImageGrab
                ImageGrab.grab().save(str(fname))
            else:
                # Linux: try scrot first, fall back to mss
                try:
                    subprocess.run(['scrot', str(fname)], check=True, timeout=5)
                except Exception:
                    import mss
                    from PIL import Image as PILImage
                    with mss.mss() as sct:
                        img = sct.grab(sct.monitors[0])
                        PILImage.frombytes('RGB', img.size, img.bgra, 'raw', 'BGRX').save(str(fname))
        except Exception as e:
            log.error(f"Screenshot capture failed: {e}")

    # ── Audio capture ──────────────────────────────────────────────────────────

    def _start_audio_capture(self) -> None:
        if PLATFORM == 'win32':
            self._start_audio_capture_win()
        else:
            self._start_audio_capture_sd()

    def _start_audio_capture_win(self) -> None:
        """Windows: WASAPI loopback capture via pyaudiowpatch."""
        log.info("Initializing WASAPI loopback audio capture...")
        try:
            import pyaudiowpatch as pyaudio
            self._pyaudio_mod = pyaudio   # store ref so the hot callback never re-imports
            self.p = pyaudio.PyAudio()
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = self.p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            all_loopbacks = list(self.p.get_loopback_device_info_generator())

            if not default_speakers.get("isLoopbackDevice"):
                matched = next(
                    (lb for lb in all_loopbacks if default_speakers["name"] in lb["name"]),
                    None,
                )
                if matched is None and all_loopbacks:
                    matched = all_loopbacks[0]
                    log.warning(
                        f"No exact loopback match for '{default_speakers['name']}' — "
                        f"falling back to '{matched['name']}'"
                    )
                if matched:
                    default_speakers = matched
                else:
                    log.error("No WASAPI loopback device found — audio will not be captured.")
                    return

            channels = int(default_speakers.get("maxInputChannels", 0)) or 2
            self.capture_channels = channels
            self.capture_rate = int(default_speakers["defaultSampleRate"])
            log.debug(f"Capturing '{default_speakers['name']}' — {self.capture_channels}ch @ {self.capture_rate}Hz")

            self.audio_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=self.capture_channels,
                rate=self.capture_rate,
                input=True,
                input_device_index=default_speakers["index"],
                frames_per_buffer=1024,
                stream_callback=self._audio_callback_win,
            )
        except Exception as e:
            log.error(f"Windows audio setup error: {e}")

    def _audio_callback_win(self, in_data, frame_count, time_info, status):
        if self.active_meeting:
            self.audio_frames.append(in_data)
        return (in_data, self._pyaudio_mod.paContinue)

    def _start_audio_capture_sd(self) -> None:
        """macOS / Linux: record from default input device via sounddevice."""
        log.info("Initializing sounddevice audio capture...")
        try:
            import sounddevice as sd
            import numpy as np

            # Sync capture_rate / capture_channels with the actual default input
            # device so the WAV header matches the recorded data.
            try:
                dev = sd.query_devices(kind='input')
                self.capture_rate = int(dev['default_samplerate'])
                self.capture_channels = min(int(dev['max_input_channels']), 2) or 1
                log.debug(f"Sounddevice input: {self.capture_channels}ch @ {self.capture_rate}Hz")
            except Exception as e:
                log.warning(f"Could not query input device; using defaults (44100/1ch): {e}")

            self._sd_stop_event = threading.Event()

            def _record():
                try:
                    with sd.InputStream(
                        samplerate=self.capture_rate,
                        channels=self.capture_channels,
                        dtype='int16',
                        blocksize=1024,
                    ) as stream:
                        while not self._sd_stop_event.is_set():
                            try:
                                data, _ = stream.read(1024)
                                if self.active_meeting:
                                    self.audio_frames.append(data.tobytes())
                            except Exception as e:
                                log.error(f"Audio read error mid-stream: {e}")
                                break
                except Exception as e:
                    log.error(f"Sounddevice stream failed: {e}")

            self._sd_thread = threading.Thread(target=_record, daemon=True)
            self._sd_thread.start()
        except Exception as e:
            log.error(f"Sounddevice audio setup error: {e}")

    def _stop_audio_capture(self) -> None:
        if PLATFORM == 'win32':
            if self.audio_stream:
                try:
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except Exception as e:
                    log.error(f"Error closing WASAPI stream: {e}")
                self.audio_stream = None
            if self.p:
                try:
                    self.p.terminate()
                except Exception:
                    pass
                self.p = None
        else:
            if self._sd_stop_event:
                self._sd_stop_event.set()
            if self._sd_thread:
                self._sd_thread.join(timeout=3)
                if self._sd_thread.is_alive():
                    # Thread outlived the timeout — keep references live so the
                    # thread can still dereference _sd_stop_event safely.
                    log.warning("Audio thread did not stop within 3s; references kept.")
                else:
                    self._sd_stop_event = None
                    self._sd_thread = None

    # ── Save + summarise ───────────────────────────────────────────────────────

    def _save_meeting(self) -> None:
        if not self.audio_frames:
            log.warning("No audio frames captured during meeting.")
            return

        log.info(f"Saving meeting to {self.current_meeting_dir}...")
        audio_path = self.current_meeting_dir / "meeting_audio.wav"
        try:
            with wave.open(str(audio_path), 'wb') as wf:
                wf.setnchannels(self.capture_channels)
                wf.setsampwidth(2)  # int16
                wf.setframerate(self.capture_rate)
                wf.writeframes(b''.join(self.audio_frames))
        except Exception as e:
            log.error(f"Failed to save meeting audio: {e}")

        log.info("Generating meeting summary via LLM...")
        try:
            resp = think(
                "Summarize this meeting based on the captured audio and visuals. "
                "Format it clearly with headings and bullet points using markdown.",
                context="[Meeting Audio Saved]",
            )
            summary_text = (
                resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            )
            if summary_text:
                with open(self.current_meeting_dir / "summary.txt", "w", encoding="utf-8") as f:
                    f.write(summary_text)
                try:
                    from notes_manager import add_note, get_notes
                    meeting_title = f"Meeting: {self.current_meeting_dir.name}"
                    if not any(n.get("title") == meeting_title for n in get_notes()):
                        add_note(summary_text, title=meeting_title)
                        log.info(f"Meeting summary saved to notes: {meeting_title}")
                except Exception as e:
                    log.error(f"Failed to save meeting summary to notes: {e}")
            log.info("Meeting summary saved.")
        except Exception as e:
            log.error(f"Failed to generate meeting summary: {e}")

        self.audio_frames = []

    # ── Main loop ──────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        last_ss = 0.0
        while self.running:
            if self.is_meeting_active() and not getattr(self, 'incognito', False):
                if not self.active_meeting:
                    log.info("Meeting detected — recording started.")
                    self.active_meeting = True
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    self.current_meeting_dir = self.base_dir / f"Meeting_{timestamp}"
                    self.current_meeting_dir.mkdir(parents=True, exist_ok=True)
                    self._start_audio_capture()

                # Screenshot every 10 seconds
                if time.time() - last_ss > 10:
                    fname = self.current_meeting_dir / f"ss_{int(time.time())}.png"
                    log.debug(f"Capturing screenshot: {fname.name}")
                    self._capture_screenshot(fname)
                    last_ss = time.time()
            else:
                if self.active_meeting:
                    log.info("Meeting ended — stopping recording.")
                    self.active_meeting = False
                    self._stop_audio_capture()
                    if getattr(self, 'incognito', False):
                        log.info("Incognito mode: discarding meeting data.")
                        self.audio_frames = []
                        if self.current_meeting_dir and self.current_meeting_dir.exists():
                            import shutil
                            try:
                                shutil.rmtree(self.current_meeting_dir)
                            except Exception as e:
                                log.error(f"Failed to remove meeting dir: {e}")
                    else:
                        self._save_meeting()

            time.sleep(2)


if __name__ == "__main__":
    rec = MeetingRecorder()
    print("MeetingRecorder initialized (dry-run mode).")
