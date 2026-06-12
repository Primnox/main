# backend/meeting_recorder.py
import re
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

# ── Meeting app categories ─────────────────────────────────────────────────────

# Apps whose sole purpose is video meetings — just being in the foreground is
# sufficient to start recording. Nobody opens Zoom to browse the web.
DEDICATED_MEETING_APPS = [
    "zoom", "webex", "gotomeeting", "whereby",
    "ringcentral", "bluejeans", "lifesize",
]

# Chat/communication apps that also support calls. Opening these does NOT mean
# you are in a call — you might just be messaging. We require a call indicator
# in the window title before starting a recording.
CHAT_WITH_CALLS = ["discord", "slack", "teams", "skype"]

# Combined list — used for the "is the app still running?" stop check
MEETING_APPS = DEDICATED_MEETING_APPS + CHAT_WITH_CALLS


# Browser processes that can host web-based meeting services
BROWSER_PROCS = ["chrome", "firefox", "msedge", "opera", "brave", "safari", "arc"]

# Page title fragments that identify an active browser-based meeting tab
BROWSER_MEETING_KEYWORDS = [
    "google meet", "meet.google.com",
    "bigbluebutton", "bbb.",
    "jitsi",
    "zoom.us/j",
    "teams.microsoft.com",
    "whereby.com",
]

# After how many 2-second checks without seeing a browser meeting tab do we
# consider the meeting over. 150 × 2 s = 5 minutes — enough grace time for
# switching to a doc-sharing window during the call.
_BROWSER_ABSENT_LIMIT = 150


class MeetingRecorder:
    def __init__(self):
        self.running = False
        self.active_meeting = False
        self.thread = None
        self.base_dir = Path.home() / "Documents" / "Primnox" / "Meetings"
        self.current_meeting_dir = None
        self.audio_frames: list[bytes] = []
        self.audio_stream = None
        self.p = None               # pyaudiowpatch instance (Windows only)
        self._pyaudio_mod = None    # module ref so the hot callback never re-imports
        self._sd_stop_event: threading.Event | None = None
        self._sd_thread: threading.Thread | None = None
        self.capture_channels = 2
        self.capture_rate = 44100
        # Browser-meeting tracking
        self._active_in_browser = False
        self._browser_absent_checks = 0

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

    # ── Foreground helper ──────────────────────────────────────────────────────

    def _get_foreground(self) -> tuple[str, str]:
        """Return (window_title, process_name) of the foreground window."""
        from screen_reader import _get_foreground_win, _get_foreground_mac, _get_foreground_linux
        if PLATFORM == 'win32':
            return _get_foreground_win()
        elif PLATFORM == 'darwin':
            return _get_foreground_mac()
        else:
            return _get_foreground_linux()

    # ── Meeting detection ──────────────────────────────────────────────────────

    def is_meeting_running(self) -> bool:
        """True if the active meeting is still in progress.

        For browser-based meetings (Google Meet etc.) we can't check the
        process name (Chrome is always running), so we track whether a meeting
        tab has been visible recently — with a 5-minute grace period for
        switching windows during the call.

        For native apps we just check if the process is still alive.
        """
        if self._active_in_browser:
            try:
                title, process = self._get_foreground()
                in_meeting = (
                    any(bp in process.lower() for bp in BROWSER_PROCS)
                    and any(kw in title.lower() for kw in BROWSER_MEETING_KEYWORDS)
                )
                if in_meeting:
                    self._browser_absent_checks = 0
                    return True
                self._browser_absent_checks += 1
                return self._browser_absent_checks < _BROWSER_ABSENT_LIMIT
            except Exception:
                return True  # be conservative

        try:
            return any(
                any(app in (p.info.get('name') or '').lower() for app in MEETING_APPS)
                for p in psutil.process_iter(['name'])
            )
        except Exception:
            return False

    # ── Call signal helpers ────────────────────────────────────────────────────

    def _has_active_udp(self, app_keyword: str) -> bool:
        """True if any process matching app_keyword has active UDP connections
        with remote endpoints — the hallmark of a live RTP/SRTP media stream."""
        try:
            for proc in psutil.process_iter(['name', 'pid']):
                if app_keyword in (proc.info.get('name') or '').lower():
                    try:
                        for conn in proc.connections(kind='udp'):
                            if conn.raddr:
                                return True
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        except Exception:
            pass
        return False

    def _has_active_audio_win(self, app_keyword: str) -> bool:
        """Windows only: True if a process matching app_keyword has an active
        audio render session (i.e. it is currently outputting sound — hearing
        other participants)."""
        try:
            from pycaw.pycaw import AudioUtilities, AudioSessionState
            for session in AudioUtilities.GetAllSessions():
                if session.Process and app_keyword in session.Process.name().lower():
                    if session.State == AudioSessionState.Active:
                        return True
        except Exception:
            pass
        return False

    def _chat_app_is_in_call(self, app_keyword: str) -> bool:
        """True if a chat app is in a live call.
        UDP connections exist during any RTP stream (even muted mic).
        Active audio session means the app is playing back participant audio.
        Either signal is sufficient — OR gives coverage for edge cases
        (e.g. everyone muted → no audio render, but UDP still flows)."""
        if self._has_active_udp(app_keyword):
            return True
        if PLATFORM == 'win32':
            return self._has_active_audio_win(app_keyword)
        return False

    def is_meeting_in_foreground(self) -> bool:
        """True if a real meeting/call is actively in the foreground.

        Decision tree:
        - Dedicated meeting apps (Zoom, Webex…): foreground is enough.
        - Chat apps (Discord, Slack, Teams, Skype): use UDP + audio session
          signals so that just opening the app never triggers recording.
        - Browser-based meetings (Google Meet, BBB, Jitsi): page title match.
        """
        try:
            title, process = self._get_foreground()
            plow = process.lower()
            tlow = title.lower()

            # Dedicated apps — open = in a meeting
            if any(app in plow for app in DEDICATED_MEETING_APPS):
                return True

            # Browser-based meetings
            if any(bp in plow for bp in BROWSER_PROCS):
                return any(kw in tlow for kw in BROWSER_MEETING_KEYWORDS)

            # Chat apps — require live UDP or active audio, not just foreground
            matched = next((app for app in CHAT_WITH_CALLS if app in plow), None)
            if matched:
                return self._chat_app_is_in_call(matched)

        except Exception:
            pass
        return False

    # ── Meeting naming ─────────────────────────────────────────────────────────

    def _extract_meeting_name(self, title: str, process: str) -> str:
        """Derive a human-readable meeting name from the foreground window."""
        plow = process.lower()
        t    = title.strip()
        tlow = t.lower()

        # ── Zoom ──────────────────────────────────────────────────────────────
        if "zoom" in plow:
            name = re.sub(r'[Zz]oom ?[Mm]eeting', '', t).strip(' -|–')
            return f"Zoom: {name}" if name else "Zoom Meeting"

        # ── Teams ──────────────────────────────────────────────────────────────
        # Title pattern: "Meeting topic | Channel | Microsoft Teams"
        # Last part is always the app name ("Microsoft Teams") — skip it only.
        if "teams" in plow:
            parts = [p.strip() for p in t.split("|")]
            APP_LABELS = {"microsoft teams", "teams"}
            topic = next((p for p in parts if p and p.lower() not in APP_LABELS), "")
            return f"Teams: {topic}" if topic else "Teams Meeting"

        # ── Discord ────────────────────────────────────────────────────────────
        # Possible titles while in a call:
        #   "Discord – #voice-general"  →  voice channel
        #   "Discord – @username"       →  DM call
        #   "Discord – Server Name"     →  server (no channel in title)
        if "discord" in plow:
            cleaned = re.sub(r'^Discord\s*[–\-]?\s*', '', t).strip()
            if not cleaned:
                return "Discord Call"
            if cleaned.startswith("#"):
                return f"Discord – {cleaned}"
            if cleaned.startswith("@"):
                return f"Discord call with {cleaned[1:]}"
            return f"Discord – {cleaned}"

        # ── Slack ──────────────────────────────────────────────────────────────
        # Huddle title: "Huddle | #channel | Workspace"
        # Call title:   "Call | #channel | Workspace"
        if "slack" in plow:
            if "huddle" in tlow:
                parts = [p.strip() for p in t.split("|")]
                channel = next((p for p in parts if p.startswith("#")), "")
                return f"Slack Huddle{' – ' + channel if channel else ''}"
            parts = [p.strip() for p in t.split("|")]
            first = parts[0] if parts else ""
            return f"Slack Call: {first}" if first else "Slack Call"

        # ── Skype ──────────────────────────────────────────────────────────────
        if "skype" in plow:
            cleaned = t.replace("Skype", "").strip(" -|–")
            return f"Skype call with {cleaned}" if cleaned else "Skype Call"

        # ── Webex ──────────────────────────────────────────────────────────────
        if "webex" in plow:
            cleaned = re.sub(r'[Cc]isco ?[Ww]ebex ?[Mm]eetings?', '', t).strip(' -|–')
            return f"Webex: {cleaned}" if cleaned else "Webex Meeting"

        # ── GoToMeeting ────────────────────────────────────────────────────────
        if "gotomeeting" in plow or "goto" in plow:
            cleaned = t.replace("GoToMeeting", "").strip(" -|–")
            return f"GoTo: {cleaned}" if cleaned else "GoToMeeting"

        # ── Browser-based meetings ─────────────────────────────────────────────
        if any(bp in plow for bp in BROWSER_PROCS):

            # Google Meet
            # Title: "Meeting name – Google Meet" or "abc-defg-hij – Google Meet"
            if "google meet" in tlow:
                name = re.sub(r'\s*[–\-]\s*[Gg]oogle [Mm]eet\s*$', '', t).strip()
                # Skip raw meet codes (format: abc-defg-hij) — not useful to humans
                if re.fullmatch(r'[a-z]{3}-[a-z]{4}-[a-z]{3}', name.lower()):
                    return "Google Meet"
                return f"Meet: {name}" if name else "Google Meet"

            # BigBlueButton
            if "bigbluebutton" in tlow or "bbb." in tlow:
                name = re.sub(r'[Bb]ig[Bb]lue[Bb]utton', '', t).strip(' -|–')
                return f"BigBlueButton: {name}" if name else "BigBlueButton Session"

            # Jitsi
            if "jitsi" in tlow:
                name = re.sub(r'[Jj]itsi ?[Mm]eet?', '', t).strip(' -|–')
                return f"Jitsi: {name}" if name else "Jitsi Meeting"

            # Generic browser meeting fallback
            for kw in BROWSER_MEETING_KEYWORDS:
                if kw in tlow:
                    name = t
                    for suffix in [" - Google Meet", " – Google Meet",
                                   " - BigBlueButton", " - Jitsi Meet",
                                   " | Microsoft Teams"]:
                        name = name.replace(suffix, "")
                    name = name.strip()
                    return name or "Online Meeting"

        return t or "Meeting"

    # ── Screenshot ─────────────────────────────────────────────────────────────

    def _capture_screenshot(self, fname: Path) -> None:
        try:
            if PLATFORM in ('win32', 'darwin'):
                from PIL import ImageGrab
                ImageGrab.grab().save(str(fname))
            else:
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
            self._pyaudio_mod = pyaudio
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
                    log.warning("Audio thread did not stop within 3s; references kept.")
                else:
                    self._sd_stop_event = None
                    self._sd_thread = None

    # ── Save + summarise ───────────────────────────────────────────────────────

    def _save_meeting(self) -> None:
        if not self.audio_frames:
            log.warning("No audio frames captured during meeting.")
            return

        # Read the name that was written at recording start
        meeting_name = "Meeting"
        if self.current_meeting_dir:
            name_file = self.current_meeting_dir / "meeting_name.txt"
            if name_file.exists():
                try:
                    meeting_name = name_file.read_text(encoding="utf-8").strip() or "Meeting"
                except Exception:
                    pass

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
                    meeting_title = f"Meeting: {meeting_name}"
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
            incognito = getattr(self, 'incognito', False)

            if not self.active_meeting:
                # Start only when a real call is detected in the foreground.
                # Dedicated apps: just being open is enough.
                # Chat apps (Discord, Slack): must show a call keyword in the title.
                if self.is_meeting_in_foreground() and not incognito:
                    try:
                        title, process = self._get_foreground()
                        meeting_name = self._extract_meeting_name(title, process)
                        plow = process.lower()
                        self._active_in_browser = any(bp in plow for bp in BROWSER_PROCS)
                    except Exception:
                        meeting_name = "Meeting"
                        self._active_in_browser = False

                    self._browser_absent_checks = 0
                    log.info(f"Meeting detected — recording started: {meeting_name}")
                    self.active_meeting = True
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    safe = re.sub(r'[^\w\s\-]', '', meeting_name)[:50].strip()
                    folder = f"Meeting_{timestamp}_{safe}" if safe else f"Meeting_{timestamp}"
                    self.current_meeting_dir = self.base_dir / folder
                    self.current_meeting_dir.mkdir(parents=True, exist_ok=True)
                    (self.current_meeting_dir / "meeting_name.txt").write_text(
                        meeting_name, encoding="utf-8"
                    )
                    self._start_audio_capture()
            else:
                # Keep recording as long as the meeting app/tab is alive.
                # Switching windows during the call does NOT stop recording.
                if not self.is_meeting_running():
                    log.info("Meeting ended — stopping recording.")
                    self.active_meeting = False
                    self._active_in_browser = False
                    self._browser_absent_checks = 0
                    self._stop_audio_capture()
                    if incognito:
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
                else:
                    # Screenshot every 10 seconds while recording
                    if time.time() - last_ss > 10:
                        fname = self.current_meeting_dir / f"ss_{int(time.time())}.png"
                        log.debug(f"Capturing screenshot: {fname.name}")
                        self._capture_screenshot(fname)
                        last_ss = time.time()

            time.sleep(2)


if __name__ == "__main__":
    rec = MeetingRecorder()
    print("MeetingRecorder initialized (dry-run mode).")
