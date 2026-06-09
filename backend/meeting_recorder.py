import pyaudiowpatch as pyaudio
import wave
import threading
import time
from pathlib import Path
from PIL import ImageGrab
import os
from brain import think
from logger import get_logger

log = get_logger("recorder")

try:
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    log.warning("win32 libraries not found, meeting detection disabled.")

MEETING_APPS = ["zoom", "teams", "slack", "meet", "webex", "discord"]

class MeetingRecorder:
    def __init__(self):
        self.running = False
        self.active_meeting = False
        self.thread = None
        self.base_dir = Path.home() / "Documents" / "Primnox" / "Meetings"
        self.current_meeting_dir = None
        self.audio_frames = []
        self.audio_stream = None
        self.p = None
        self.capture_channels = 2
        self.capture_rate = 44100

    def start(self):
        if self.running: return
        log.info("Starting MeetingRecorder thread...")
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        log.info("Stopping MeetingRecorder...")
        self.running = False
        if self.thread: self.thread.join()

    def is_meeting_active(self):
        if not HAS_WIN32: return False
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd: return False
            title = win32gui.GetWindowText(hwnd).lower()
            return any(app in title for app in MEETING_APPS)
        except Exception: return False

    def _start_audio_capture(self):
        log.info("Initializing loopback audio capture for meeting...")
        self.p = pyaudio.PyAudio()
        try:
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = self.p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

            # Collect ALL loopback devices once so we can fall back gracefully
            all_loopbacks = list(self.p.get_loopback_device_info_generator())

            if not default_speakers.get("isLoopbackDevice"):
                # 1st choice: loopback whose name contains the default speaker name
                matched = next(
                    (lb for lb in all_loopbacks if default_speakers["name"] in lb["name"]),
                    None
                )
                # 2nd choice (fallback): any loopback device at all
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

            channels = int(default_speakers.get("maxInputChannels", 0))
            if channels == 0:
                # Some loopback devices report 0 input channels; use stereo as safe default
                channels = 2
                log.warning("Loopback device reports 0 input channels — defaulting to 2")

            self.capture_channels = channels
            self.capture_rate = int(default_speakers["defaultSampleRate"])
            log.debug(
                f"Capturing '{default_speakers['name']}' — "
                f"{self.capture_channels}ch @ {self.capture_rate}Hz"
            )

            self.audio_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=self.capture_channels,
                rate=self.capture_rate,
                input=True,
                input_device_index=default_speakers["index"],
                frames_per_buffer=1024,
                stream_callback=self._audio_callback
            )
        except Exception as e:
            log.error(f"Audio setup error: {e}")

    def _audio_callback(self, in_data, frame_count, time_info, status):
        if self.active_meeting:
            self.audio_frames.append(in_data)
        return (in_data, pyaudio.paContinue)

    def _save_meeting(self):
        if not self.audio_frames:
            log.warning("No audio frames captured during meeting.")
            return
        
        log.info(f"Saving meeting to {self.current_meeting_dir}...")
        audio_path = self.current_meeting_dir / "meeting_audio.wav"
        try:
            wf = wave.open(str(audio_path), 'wb')
            wf.setnchannels(self.capture_channels)
            wf.setsampwidth(self.p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(self.capture_rate)
            wf.writeframes(b''.join(self.audio_frames))
            wf.close()
        except Exception as e:
            log.error(f"Failed to save meeting audio: {e}")
        
        # Trigger Summary logic (Primnox)
        log.info("Generating meeting summary via Groq...")
        try:
            resp = think(
                "Summarize this meeting based on the captured audio and visuals. "
                "Format it clearly with headings and bullet points using markdown.",
                context="[Meeting Audio Saved]"
            )
            summary_text = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

            if summary_text:
                with open(self.current_meeting_dir / "summary.txt", "w", encoding="utf-8") as f:
                    f.write(summary_text)

                # Save as its own note
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

    def _loop(self):
        last_ss = 0
        while self.running:
            if self.is_meeting_active() and not getattr(self, 'incognito', False):
                if not self.active_meeting:
                    log.info("Meeting detected! Recording started.")
                    self.active_meeting = True
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    self.current_meeting_dir = self.base_dir / f"Meeting_{timestamp}"
                    self.current_meeting_dir.mkdir(parents=True, exist_ok=True)
                    self._start_audio_capture()
                
                # Screenshots every 10 seconds
                if time.time() - last_ss > 10:
                    fname = self.current_meeting_dir / f"ss_{int(time.time())}.png"
                    log.debug(f"Capturing meeting screenshot: {fname.name}")
                    try:
                        ImageGrab.grab().save(fname)
                    except Exception as e:
                        log.error(f"Failed to capture meeting screenshot: {e}")
                    last_ss = time.time()
            else:
                if self.active_meeting:
                    log.info("Meeting ended or incognito mode enabled. Stopping recording.")
                    self.active_meeting = False
                    if self.audio_stream:
                        try:
                            self.audio_stream.stop_stream()
                            self.audio_stream.close()
                        except Exception as e:
                            log.error(f"Error closing meeting audio stream: {e}")
                    if getattr(self, 'incognito', False):
                        log.info("Incognito mode active: discarding current meeting data.")
                        self.audio_frames = []
                        if self.current_meeting_dir and self.current_meeting_dir.exists():
                            import shutil
                            try:
                                shutil.rmtree(self.current_meeting_dir)
                            except Exception as e:
                                log.error(f"Failed to remove meeting directory: {e}")
                    else:
                        self._save_meeting()
            
            time.sleep(2)

if __name__ == "__main__":
    rec = MeetingRecorder()
    print("Meeting Recorder initialized (dry-run mode).")
