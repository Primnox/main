# backend/meeting_recorder.py
import re
import shutil
import sys
import threading
import time
import wave
import subprocess
from pathlib import Path
import psutil
from brain import think, transcribe
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

# Screenshots fire every 10s with no prior cap — a 2h meeting meant ~700
# images. 180 × 10s = 30 minutes of coverage, which is enough to show what
# was being screen-shared without an unboundedly growing meeting folder.
_MAX_MEETING_SCREENSHOTS = 180

# How long a cached is_meeting_running() native-app check stays valid before
# re-scanning every process on the system.
_NATIVE_CHECK_INTERVAL = 8


def create_tasks_from_summary(summary_text: str, meeting_name: str) -> int:
    """Parse action-item-shaped lines out of a meeting summary and create a
    real Task per item, instead of leaving them buried in note prose that's
    easy to never re-read. Returns the number of tasks created."""
    from notes_manager import add_task, extract_action_items
    items = list(dict.fromkeys(extract_action_items(summary_text)))[:10]
    created = 0
    for item in items:
        try:
            add_task(f"[{meeting_name}] {item}", priority="normal")
            created += 1
        except Exception as e:
            log.warning(f"Could not create task from action item: {e}")
    return created


def transcribe_meeting_audio(audio_path) -> str:
    """Transcribe a meeting WAV via Groq Whisper in SIZE-bounded chunks so a long
    call — or a large stereo/44.1k fallback track — never exceeds Whisper's
    per-file size limit. Shared by the recorder and the meeting-summary skill so
    there's a single transcription implementation. Returns the concatenated
    transcript ('' if transcription is unavailable)."""
    try:
        audio_path = Path(audio_path)
        if not audio_path.exists():
            return ""
        import io
        parts: list[str] = []
        with wave.open(str(audio_path), 'rb') as wf:
            nch, sw, fr = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
            bytes_per_frame = max(1, nch * sw)
            # Bound each chunk by BYTES (≤18 MB, safely under Whisper's ~25 MB
            # limit regardless of channels/rate) and also by duration for latency.
            MAX_CHUNK_BYTES = 18 * 1024 * 1024
            frames_by_size = MAX_CHUNK_BYTES // bytes_per_frame
            frames_by_time = fr * 300  # 5 minutes
            chunk_frames = max(1, min(frames_by_size, frames_by_time))
            while True:
                frames = wf.readframes(chunk_frames)
                if not frames:
                    break
                buf = io.BytesIO()
                with wave.open(buf, 'wb') as cw:
                    cw.setnchannels(nch)
                    cw.setsampwidth(sw)
                    cw.setframerate(fr)
                    cw.writeframes(frames)
                res = transcribe(buf.getvalue(), timeout=120)
                text = (res.get("text", "") if isinstance(res, dict) else "").strip()
                if text and not text.startswith("[System:"):
                    parts.append(text)
        transcript = "\n".join(parts).strip()
        log.info(f"Transcription produced {len(transcript)} chars from {audio_path.name}.")
        return transcript
    except Exception as e:
        log.error(f"Meeting transcription failed: {e}")
        return ""


class MeetingRecorder:
    def __init__(self):
        self.running = False
        self.active_meeting = False
        self.thread = None
        self.base_dir = Path.home() / "Documents" / "Primnox" / "Meetings"
        self.current_meeting_dir = None
        self.audio_frames: list[bytes] = []   # speaker / loopback (other participants)
        self.audio_stream = None
        self.p = None               # pyaudiowpatch instance (Windows only)
        self._pyaudio_mod = None    # module ref so the hot callback never re-imports
        self._sd_stop_event: threading.Event | None = None
        self._sd_thread: threading.Thread | None = None
        self.capture_channels = 2
        self.capture_rate = 44100
        # Microphone capture (your own voice) — recorded alongside the loopback
        # so the saved meeting has BOTH sides of the conversation, not just the
        # audio coming out of your speakers.
        self.mic_frames: list[bytes] = []
        self.mic_stream = None
        self.mic_channels = 1
        self.mic_rate = 44100
        # Raw tracks are streamed to disk incrementally (see
        # _flush_audio_to_disk) instead of held in audio_frames/mic_frames
        # for the whole meeting — a long call used to mean multi-GB of RAM
        # held for as long as the call lasted.
        self._spk_writer = None
        self._mic_writer = None
        self._frame_lock = threading.Lock()
        # Browser-meeting tracking
        self._active_in_browser = False
        self._browser_absent_checks = 0
        self._screenshot_count = 0
        # is_meeting_running()'s native-app path scans every process on the
        # system — caching it for a few seconds avoids doing that on every
        # single 2s poll tick for the whole meeting.
        self._native_check_at = 0.0
        self._native_check_cached = True

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

        # Enumerating every process on the system is real work — a native
        # meeting app doesn't quit and relaunch inside a couple of seconds,
        # so cache the result instead of re-scanning on every 2s poll tick.
        now = time.time()
        if now - self._native_check_at < _NATIVE_CHECK_INTERVAL:
            return self._native_check_cached
        self._native_check_at = now

        try:
            self._native_check_cached = any(
                any(app in (p.info.get('name') or '').lower() for app in MEETING_APPS)
                for p in psutil.process_iter(['name'])
            )
        except Exception:
            self._native_check_cached = False
        return self._native_check_cached

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
            self._spk_writer = self._open_wav_writer(
                self.current_meeting_dir / "audio_speakers.wav", self.capture_channels, self.capture_rate
            )

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

        # ── Microphone (your own voice) ──────────────────────────────────────
        # Open a SECOND stream on the default input device. Wrapped separately
        # so that if the mic can't be opened we still capture the loopback.
        try:
            mic_info = self.p.get_device_info_by_index(
                wasapi_info["defaultInputDevice"]
            )
            self.mic_channels = min(int(mic_info.get("maxInputChannels", 1)) or 1, 2)
            self.mic_rate = int(mic_info["defaultSampleRate"])
            log.debug(f"Capturing mic '{mic_info['name']}' — {self.mic_channels}ch @ {self.mic_rate}Hz")
            self._mic_writer = self._open_wav_writer(
                self.current_meeting_dir / "audio_mic.wav", self.mic_channels, self.mic_rate
            )
            self.mic_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=self.mic_channels,
                rate=self.mic_rate,
                input=True,
                input_device_index=mic_info["index"],
                frames_per_buffer=1024,
                stream_callback=self._mic_callback_win,
            )
        except Exception as e:
            log.warning(f"Mic capture unavailable (recording speakers only): {e}")
            self.mic_stream = None

    def _audio_callback_win(self, in_data, frame_count, time_info, status):
        if self.active_meeting:
            with self._frame_lock:
                self.audio_frames.append(in_data)
        return (in_data, self._pyaudio_mod.paContinue)

    def _mic_callback_win(self, in_data, frame_count, time_info, status):
        if self.active_meeting:
            with self._frame_lock:
                self.mic_frames.append(in_data)
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

            self._spk_writer = self._open_wav_writer(
                self.current_meeting_dir / "audio_speakers.wav", self.capture_channels, self.capture_rate
            )
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
                                    with self._frame_lock:
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

    # ── Streaming-to-disk (bounded memory) ──────────────────────────────────────

    def _open_wav_writer(self, path: Path, channels: int, rate: int):
        """Open a WAV file for incremental writeframes() calls. wave patches
        the header's data-length field on close(), so this doesn't need to
        know the total duration up front."""
        try:
            w = wave.open(str(path), 'wb')
            w.setnchannels(max(1, channels))
            w.setsampwidth(2)  # int16
            w.setframerate(rate)
            return w
        except Exception as e:
            log.error(f"Could not open WAV writer for {path}: {e}")
            return None

    def _flush_audio_to_disk(self) -> None:
        """Drain audio_frames/mic_frames to their WAV writers and clear the
        in-memory lists. Called periodically from the polling loop — NOT the
        audio callback, which must stay fast — so a long meeting's memory
        footprint stays bounded to a couple of seconds of audio instead of
        growing for the entire call."""
        with self._frame_lock:
            spk_chunk = self.audio_frames
            self.audio_frames = []
            mic_chunk = self.mic_frames
            self.mic_frames = []
        if self._spk_writer and spk_chunk:
            try:
                self._spk_writer.writeframes(b''.join(spk_chunk))
            except Exception as e:
                log.error(f"Speaker audio flush failed: {e}")
        if self._mic_writer and mic_chunk:
            try:
                self._mic_writer.writeframes(b''.join(mic_chunk))
            except Exception as e:
                log.error(f"Mic audio flush failed: {e}")

    def _close_wav_writers(self) -> None:
        for attr in ("_spk_writer", "_mic_writer"):
            writer = getattr(self, attr)
            if writer:
                try:
                    writer.close()
                except Exception as e:
                    log.error(f"Error closing {attr}: {e}")
                setattr(self, attr, None)

    def _stop_audio_capture(self) -> None:
        if PLATFORM == 'win32':
            if self.audio_stream:
                try:
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except Exception as e:
                    log.error(f"Error closing WASAPI stream: {e}")
                self.audio_stream = None
            if self.mic_stream:
                try:
                    self.mic_stream.stop_stream()
                    self.mic_stream.close()
                except Exception as e:
                    log.error(f"Error closing mic stream: {e}")
                self.mic_stream = None
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

        # Streams are fully stopped now, so no callback can still be appending
        # — safe to catch whatever's left since the last periodic flush, then
        # close the writers (this is what finalizes the WAV headers).
        self._flush_audio_to_disk()
        self._close_wav_writers()

    # ── Save + summarise ───────────────────────────────────────────────────────

    @staticmethod
    def _read_wav(path: Path):
        """Returns (raw_pcm_bytes, channels, rate), or (b'', 0, 0) if the file
        doesn't exist or has no frames — same as an empty/absent track."""
        if not path.exists():
            return b"", 0, 0
        try:
            with wave.open(str(path), 'rb') as wf:
                return wf.readframes(wf.getnframes()), wf.getnchannels(), wf.getframerate()
        except Exception as e:
            log.error(f"Could not read {path.name}: {e}")
            return b"", 0, 0

    def _save_mixed_wav(self, path: Path, spk_path: Path, mic_path: Path) -> bool:
        """Mix the speaker (loopback) and mic tracks into one mono 16 kHz WAV —
        the format that works best for downstream speech transcription. Both
        tracks are downmixed to mono, resampled to a common rate, and summed
        with clip protection. Returns False if mixing isn't possible (caller
        then falls back to a raw single-source track).

        Reads the tracks back from the WAV files written incrementally during
        the meeting (see _flush_audio_to_disk) rather than from in-memory
        buffers — this is the one place the full call's audio needs to be in
        memory at once, and it happens here only, once, at save time, not
        held for the whole meeting's duration."""
        if not spk_path.exists() and not mic_path.exists():
            return False
        try:
            import numpy as np
            TARGET_RATE = 16000  # speech-optimal, compact

            def to_mono_target(raw: bytes, channels: int, rate: int):
                if not raw:
                    return np.zeros(0, dtype=np.float32)
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                if channels and channels > 1:
                    usable = (arr.size // channels) * channels
                    arr = arr[:usable].reshape(-1, channels).mean(axis=1)
                if rate and rate != TARGET_RATE and arr.size:
                    from math import gcd
                    from scipy.signal import resample_poly
                    g = gcd(int(rate), TARGET_RATE)
                    arr = resample_poly(arr, TARGET_RATE // g, int(rate) // g).astype(np.float32)
                return arr

            spk_raw, spk_ch, spk_rate = self._read_wav(spk_path)
            mic_raw, mic_ch, mic_rate = self._read_wav(mic_path)
            spk = to_mono_target(spk_raw, spk_ch, spk_rate)
            mic = to_mono_target(mic_raw, mic_ch, mic_rate)
            n = max(spk.size, mic.size)
            if n == 0:
                return False
            if spk.size < n:
                spk = np.pad(spk, (0, n - spk.size))
            if mic.size < n:
                mic = np.pad(mic, (0, n - mic.size))
            mixed = spk + mic
            peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
            if peak > 32767.0:
                mixed *= (32767.0 / peak)
            mixed = mixed.astype(np.int16)
            with wave.open(str(path), 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(TARGET_RATE)
                wf.writeframes(mixed.tobytes())
            return True
        except Exception as e:
            log.error(f"Audio mix failed ({e}); will fall back to a raw track.")
            return False

    def _transcribe_meeting(self, audio_path) -> str:
        return transcribe_meeting_audio(audio_path)

    def _save_meeting(self) -> None:
        d = self.current_meeting_dir
        spk_path = d / "audio_speakers.wav" if d else None
        mic_path = d / "audio_mic.wav" if d else None
        # Raw per-source tracks are already fully written — _flush_audio_to_disk
        # streamed them incrementally during the meeting, and _stop_audio_capture
        # closed the writers (which finalizes the WAV headers) before this runs.
        if not (spk_path and spk_path.exists()) and not (mic_path and mic_path.exists()):
            log.warning("No audio captured during meeting.")
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

        log.info(f"Saving meeting to {d}...")
        log.info(f"Captured tracks — speakers: {spk_path.exists()}, mic: {mic_path.exists()}")
        # Primary combined recording (keeps the meeting_audio.wav name other code
        # expects). Prefer the mic+speaker mix; fall back to whichever raw track
        # exists if the mix can't be produced.
        mixed_path = d / "meeting_audio.wav"
        if not self._save_mixed_wav(mixed_path, spk_path, mic_path):
            fallback = spk_path if spk_path.exists() else (mic_path if mic_path.exists() else None)
            if fallback:
                try:
                    shutil.copyfile(fallback, mixed_path)
                except Exception as e:
                    log.error(f"Could not create fallback meeting_audio.wav: {e}")

        # Transcribe the audio FIRST so the summary reflects what was actually
        # said, not a guess. The full transcript is saved alongside the summary.
        transcript = self._transcribe_meeting(d / "meeting_audio.wav")
        if transcript:
            try:
                (d / "transcript.txt").write_text(transcript, encoding="utf-8")
            except Exception as e:
                log.error(f"Failed to save transcript: {e}")

        log.info("Generating meeting summary via LLM...")
        try:
            if transcript:
                excerpt = transcript[:15000]
                if len(transcript) > 15000:
                    excerpt += "\n\n[...transcript truncated for summary; full text in transcript.txt...]"
                resp = think(
                    "Summarize this meeting from the transcript below. Use markdown with a short "
                    "overview, key discussion points, decisions made, and action items (with owners "
                    "if named).\n\nTRANSCRIPT:\n" + excerpt,
                )
            else:
                resp = think(
                    "Write a brief meeting note. No transcript was available (the audio could not be "
                    "transcribed), so keep it short and say so.",
                    context="[Meeting recorded — transcript unavailable]",
                )
            summary_text = (
                resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            )
            if summary_text:
                with open(self.current_meeting_dir / "summary.txt", "w", encoding="utf-8") as f:
                    f.write(summary_text)
                try:
                    from notes_manager import add_note, note_title_exists, init_db
                    init_db()  # ensure the notes table exists before inserting
                    meeting_title = f"Meeting: {meeting_name}"
                    if not note_title_exists(meeting_title):
                        add_note(summary_text, title=meeting_title)
                        log.info(f"Meeting summary saved to notes: {meeting_title}")

                        # The summary prompt already asks the LLM for action items —
                        # previously that just sat as prose in the note, easy to never
                        # re-read. Turn them into real tasks so they show up where
                        # tasks actually get looked at.
                        created = create_tasks_from_summary(summary_text, meeting_name)
                        if created:
                            log.info(f"Created {created} task(s) from meeting action items.")
                except Exception as e:
                    log.error(f"Failed to save meeting summary to notes: {e}")
            log.info("Meeting summary saved.")
        except Exception as e:
            log.error(f"Failed to generate meeting summary: {e}")

        self.audio_frames = []
        self.mic_frames = []

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
                    self._screenshot_count = 0
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
                        self.mic_frames = []
                        if self.current_meeting_dir and self.current_meeting_dir.exists():
                            try:
                                shutil.rmtree(self.current_meeting_dir)
                            except Exception as e:
                                log.error(f"Failed to remove meeting dir: {e}")
                    else:
                        self._save_meeting()
                else:
                    # Bounds memory to a couple of seconds of audio instead of
                    # letting it grow for the entire meeting — see
                    # _flush_audio_to_disk's docstring.
                    self._flush_audio_to_disk()

                    # Screenshot every 10 seconds while recording, up to a cap
                    if time.time() - last_ss > 10:
                        if self._screenshot_count < _MAX_MEETING_SCREENSHOTS:
                            fname = self.current_meeting_dir / f"ss_{int(time.time())}.png"
                            log.debug(f"Capturing screenshot: {fname.name}")
                            self._capture_screenshot(fname)
                            self._screenshot_count += 1
                        last_ss = time.time()

            time.sleep(2)


if __name__ == "__main__":
    rec = MeetingRecorder()
    print("MeetingRecorder initialized (dry-run mode).")
