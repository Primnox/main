import sys
import subprocess
import threading
import time
import psutil
import pyperclip
import difflib
from pathlib import Path
from brain import think
from memory import add_memory
from logger import get_logger
from project_context import parse_editor_title

log = get_logger("feed")

PLATFORM = sys.platform  # 'win32', 'darwin', 'linux'

try:
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    log.warning("win32 libraries not found, window tracking limited.")

# Windows System Media Transport Controls — reads now-playing from ANY app
# that registers with Windows (Spotify, Chrome/YouTube, Edge, VLC, etc.).
# Optional: falls back to window-title scanning if winsdk isn't installed.
try:
    import asyncio as _asyncio
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _SMTCManager,
    )
    HAS_SMTC = True
except Exception:
    HAS_SMTC = False

# ── Persistent asyncio event loop for SMTC ───────────────────────────────────
# asyncio.run() creates and destroys a new loop every call, which breaks the
# Windows Runtime COM apartment model that winsdk relies on.
# One stable loop running on a dedicated daemon thread solves this.
_smtc_loop: '_asyncio.AbstractEventLoop | None' = None

def _get_smtc_loop() -> '_asyncio.AbstractEventLoop':
    global _smtc_loop
    if HAS_SMTC and (_smtc_loop is None or _smtc_loop.is_closed()):
        _smtc_loop = _asyncio.new_event_loop()
        t = threading.Thread(target=_smtc_loop.run_forever, daemon=True, name="smtc-loop")
        t.start()
        log.debug("SMTC event loop started")
    return _smtc_loop  # type: ignore[return-value]

# Start it immediately so the first SMTC query is fast
if HAS_SMTC:
    try:
        _get_smtc_loop()
    except Exception:
        pass

class FeedManager:
    def __init__(self, callback=None):
        self.callback = callback
        self.running = False
        self.thread = None
        self.session_start = time.time()
        self.active_window_title = None
        self.active_process_name = None
        self.history = []
        
        # Proactive Detection State
        self.window_start_time = time.time()
        self.vscode_start_time = time.time()
        self.last_clipboard = ""
        self.error_history = [] # List of (timestamp, error_text)
        self.screen_error_frequency = {} # Map of {error_text: consecutive_scan_count}
        self.fired_screen_errors = set() # Set of error_texts that we already alerted on
        
        # Fire Control (Prevention of spam)
        self.fired_stuck_session = False
        self.fired_vscode_session = False
        self.last_error_fire_time = 0
        # macOS osascript circuit breaker (prevents zombie accumulation)
        self._mac_fail_count = 0
        self._mac_circuit_open_until = 0.0
        self.last_stuck_fire_time = 0 # cooldown tracking
        self.last_vscode_fire_time = 0
        self.last_uia_scan_time = 0

        # Two-stage error detection cooldowns
        self.last_stage1_time = 0
        self.stage1_cooldown = 60    # seconds between UAI→Groq text checks
        self.last_stage2_time = 0
        self.stage2_cooldown = 300   # seconds between vision SS calls
        self._stage_lock = threading.Lock()  # prevent overlapping stage runs

        # ── Feature: Error Streak ────────────────────────────────────────
        # Keyed by fingerprint (screen_reader.fingerprint), not raw text — two
        # scans of "TypeError at file.py:42" and "TypeError at file.py:57" are
        # the same underlying error and used to be tracked as two unrelated
        # streaks because the raw strings differed.
        self.error_streak_start: dict = {}      # {fingerprint: {"text":..., "start":...}}
        self.error_streak_notified: dict = {}   # {fingerprint: last_reported_minute}
        # Bounds how often the SAME error (by fingerprint) re-triggers the
        # two-stage LLM investigation: once it's been investigated, a repeat
        # sighting within this window is assumed to be the same still-open
        # error, not a new event worth another Groq+vision round trip.
        self.fired_error_fps: dict = {}         # {fingerprint: last_investigated_time}
        self.fired_error_fp_ttl = 1800          # 30 minutes

        # ── Feature: Flow State ──────────────────────────────────────────
        self.focus_apps = {
            # Windows (.exe names)
            "code.exe", "pycharm64.exe", "idea64.exe",
            "sublime_text.exe", "obsidian.exe", "nvim.exe", "vim.exe",
            "cmd.exe", "powershell.exe", "windowsterminal.exe", "wt.exe",
            # macOS / Linux (no extension)
            "code", "pycharm", "idea", "sublime_text", "obsidian", "nvim", "vim",
            "terminal", "iterm2", "alacritty", "kitty", "warp",
            "gnome-terminal", "konsole", "xterm", "bash", "zsh", "fish",
        }
        self.flow_start_time: float = 0.0
        self.flow_app: str = ""
        self.flow_last_milestone: int = -1   # last 5-min bucket reported

        # ── Feature: Now Playing ─────────────────────────────────────────
        self.last_now_playing_check: float = 0.0
        self.now_playing_interval: float = 5.0
        self.last_now_playing_state: dict = {}

        # ── Feature: Productivity Score ──────────────────────────────────
        self.productivity_focus_seconds: float = 0.0
        self.productivity_total_seconds: float = 0.0
        self.last_productivity_report: float = time.time()
        self.productivity_report_interval: float = 60.0

        # ── Island Skills (pluggable strips) ──────────────────────────────
        # Populated lazily on first loop tick so imports are fully resolved.
        self._island_skills: list = []
        self._island_skill_timers: dict = {}   # skill.island_name → last_check ts
        self._island_skills_loaded: bool = False

    def start(self):
        if self.running: return
        log.info("Starting FeedManager...")
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        log.info("Stopping FeedManager...")
        self.running = False
        if self.thread: self.thread.join()

    def get_active_info(self):
        if PLATFORM == 'win32':
            return self._get_active_info_win()
        elif PLATFORM == 'darwin':
            return self._get_active_info_mac()
        else:
            return self._get_active_info_linux()

    def _get_active_info_win(self):
        if not HAS_WIN32:
            return "Unknown", "Unknown"
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "Unknown", "Unknown"
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid).name()
            return title, process
        except Exception as e:
            log.error(f"Failed to get active window info: {e}")
            return "Unknown", "Unknown"

    def _get_active_info_mac(self):
        # Circuit breaker: if osascript has hung 3+ times recently, skip for 60s
        # to avoid accumulating zombie processes when System Events is unresponsive.
        now = time.time()
        if self._mac_fail_count >= 3 and now < self._mac_circuit_open_until:
            return "Unknown", "Unknown"
        try:
            script = (
                'tell application "System Events"\n'
                '  set frontApp to first application process whose frontmost is true\n'
                '  set appName to name of frontApp\n'
                '  try\n'
                '    set windowTitle to name of front window of frontApp\n'
                '  on error\n'
                '    set windowTitle to appName\n'
                '  end try\n'
                '  return appName & "||SEP||" & windowTitle\n'
                'end tell'
            )
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                self._mac_fail_count = 0   # reset circuit on success
                parts = result.stdout.strip().split('||SEP||', 1)
                app_name = parts[0].strip()
                win_title = parts[1].strip() if len(parts) > 1 else app_name
                return win_title, app_name
            return "Unknown", "Unknown"
        except Exception as e:
            self._mac_fail_count += 1
            if self._mac_fail_count >= 3:
                self._mac_circuit_open_until = time.time() + 60
                log.warning(f"osascript circuit opened for 60s after {self._mac_fail_count} failures")
            log.error(f"macOS active window failed: {e}")
            return "Unknown", "Unknown"

    def _get_active_info_linux(self):
        try:
            win_id = subprocess.run(
                ['xdotool', 'getactivewindow'],
                capture_output=True, text=True, timeout=2
            ).stdout.strip()
            if not win_id:
                return "Unknown", "Unknown"
            title = subprocess.run(
                ['xdotool', 'getwindowname', win_id],
                capture_output=True, text=True, timeout=2
            ).stdout.strip()
            try:
                pid_str = subprocess.run(
                    ['xdotool', 'getwindowpid', win_id],
                    capture_output=True, text=True, timeout=2
                ).stdout.strip()
                process = psutil.Process(int(pid_str)).name() if pid_str else "Unknown"
            except Exception:
                process = "Unknown"
            return title or "Unknown", process
        except Exception as e:
            log.error(f"Linux active window failed: {e}")
            return "Unknown", "Unknown"

    def _get_active_pid(self):
        """PID of the foreground window, or None. Kept separate from
        get_active_info() (whose (title, process) tuple several call sites
        already unpack) rather than widening that tuple everywhere — only
        project-context resolution needs the pid."""
        try:
            if PLATFORM == 'win32':
                if not HAS_WIN32:
                    return None
                hwnd = win32gui.GetForegroundWindow()
                if not hwnd:
                    return None
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                return pid or None
            elif PLATFORM == 'darwin':
                if self._mac_fail_count >= 3 and time.time() < self._mac_circuit_open_until:
                    return None
                result = subprocess.run(
                    ['osascript', '-e',
                     'tell application "System Events" to unix id of '
                     '(first application process whose frontmost is true)'],
                    capture_output=True, text=True, timeout=3
                )
                out = result.stdout.strip()
                return int(out) if result.returncode == 0 and out.isdigit() else None
            else:
                win_id = subprocess.run(
                    ['xdotool', 'getactivewindow'],
                    capture_output=True, text=True, timeout=2
                ).stdout.strip()
                if not win_id:
                    return None
                pid_str = subprocess.run(
                    ['xdotool', 'getwindowpid', win_id],
                    capture_output=True, text=True, timeout=2
                ).stdout.strip()
                return int(pid_str) if pid_str else None
        except Exception:
            return None

    def log_ambient(self, text):
        """Log ambient speech to history with timestamp."""
        event = f"{time.strftime('%H:%M:%S')} - Ambient: {text}"
        self.history.append(event)
        log.debug(f"Logged ambient speech: {text[:50]}...")

    def _extract_memories(self):
        """Primnox: Extract key insights from the last 5 minutes of activity."""
        if not self.history: return
        log.info("Extracting memories from recent feed activity...")
        recent_log = "\n".join(self.history[-100:]) # Last 100 events
        try:
            sys_override = "You are a strict background data-extraction process. Output ONLY the extracted memories as a single concise sentence. Do not converse or add filler. If there is no meaningful activity, output 'None'."
            resp = think(
                "Extract a single concise memory from this activity log. focus on projects, tasks, and important context.",
                context=recent_log,
                system_override=sys_override
            )
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            # Multi-word phrases are safe as substrings; "none" must be an exact
            # match (normalised) so we don't drop valid memories like "nonessential".
            _reject_phrases = ["no meaningful", "no identifiable", "nothing significant",
                               "no specific", "not enough", "no notable",
                               "no project", "no task", "not available", "no activity"]
            _clean = (content or "").strip().lower().rstrip(".!")
            _rejected = (not _clean
                         or _clean == "none"
                         or any(p in _clean for p in _reject_phrases))
            if content and not _rejected:
                log.info(f"Memory extracted: {content[:100]}...")
                # Ambient screen/app activity, not a chat exchange — "session"
                # matches the category core.py's own auto-extraction uses for
                # the same kind of transient context. Was relying on
                # add_memory()'s default, which happened to be "session" too;
                # now explicit so the category can't silently drift if the
                # default ever changes.
                add_memory(content, category="session")
                if self.callback:
                    self.callback("memory_updated", {"text": content})
        except Exception as e:
            log.error(f"Memory extraction failed: {e}")

    def generate_daily_debrief(self):
        """Primnox: Summarize the day's activity."""
        log.info("Generating daily debrief summary...")
        log_content = "\n".join(self.history)
        try:
            sys_override = "You are a strict data summarizer. Output a clean, professional daily debrief of productivity and key achievements. Do not converse or use a sarcastic persona. Output only the report."
            resp = think(
                "Generate a professional daily debrief. summarize my productivity and key achievements.",
                context=log_content,
                system_override=sys_override
            )
            debrief = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            log.info("Daily debrief generated.")
            if self.callback:
                self.callback("daily_debrief", {"debrief": debrief})
            return debrief
        except Exception as e:
            log.error(f"Debrief generation failed: {e}")
            return "failed to generate debrief."

    # ── Island Skills ────────────────────────────────────────────────────────

    def _load_island_skills(self):
        """Discover all BaseIslandSkill subclasses from the skill registry."""
        try:
            from skills.base_island_skill import BaseIslandSkill
            from skills.skill_router import SKILL_REGISTRY, TRIGGER_MAP
            seen = set()
            for skill_cls in list(SKILL_REGISTRY.values()) + list(TRIGGER_MAP.values()):
                if (issubclass(skill_cls, BaseIslandSkill)
                        and skill_cls is not BaseIslandSkill
                        and skill_cls not in seen):
                    seen.add(skill_cls)
                    try:
                        self._island_skills.append(skill_cls())
                        log.info(f"Island skill registered: {skill_cls.island_name or skill_cls.name}")
                    except Exception as e:
                        log.warning(f"Could not instantiate island skill {skill_cls.name}: {e}")
        except Exception as e:
            log.warning(f"Island skill discovery failed: {e}")
        self._island_skills_loaded = True

    def _poll_island_skills(self, current_time: float):
        """Check each island skill and push data if it's time to refresh."""
        if not self._island_skills_loaded:
            self._load_island_skills()

        for skill in self._island_skills:
            key      = getattr(skill, "island_name", None) or skill.name
            interval = getattr(skill, "refresh_seconds", 60)
            last     = self._island_skill_timers.get(key, 0.0)
            if current_time - last < interval:
                continue
            self._island_skill_timers[key] = current_time
            try:
                data = skill.get_island_data()
                if self.callback:
                    self.callback("island_skill", {"skill": key, "data": data})
            except Exception as e:
                log.warning(f"Island skill {key!r} get_island_data failed: {e}")

    # ── Now Playing Detection ─────────────────────────────────────────────────

    # ── SMTC helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _smtc_source_name(app_id: str) -> str:
        """Map a Windows SMTC SourceAppUserModelId to a friendly source name."""
        a = (app_id or "").lower()
        if "spotify"      in a: return "Spotify"
        if "youtubemusic" in a: return "YouTube Music"
        if "youtube"      in a: return "YouTube"
        if "msedge"       in a or "edge" in a: return "Edge"
        if "chrome"       in a: return "Chrome"
        if "firefox"      in a: return "Firefox"
        if "opera"        in a: return "Opera"
        if "brave"        in a: return "Brave"
        if "vlc"          in a: return "VLC"
        if "foobar"       in a: return "foobar2000"
        if "applemusic"   in a or "itunes" in a: return "Apple Music"
        if "amazonmusic"  in a or "amazon" in a: return "Amazon Music"
        if "tidal"        in a: return "TIDAL"
        if "deezer"       in a: return "Deezer"
        if "soundcloud"   in a: return "SoundCloud"
        if "groove"       in a or "zune" in a: return "Groove Music"
        if "winamp"       in a: return "Winamp"
        if "musicbee"     in a: return "MusicBee"
        if "aimp"         in a: return "AIMP"
        # Fallback: strip path, drop .exe, title-case
        name = (app_id or "").split("\\")[-1].split("!")[-1]
        name = name.replace(".exe", "").replace("_", " ")
        return name.title() if name else "Unknown"

    def _try_smtc(self) -> dict | None:
        """Query Windows System Media Transport Controls for the currently
        playing/paused track.  Works with any app that registers with the OS
        media session (Spotify, Chrome, Edge, Firefox, VLC, Apple Music, etc.).

        Uses a single persistent asyncio event loop (see _get_smtc_loop) so
        that the Windows Runtime COM apartment is stable across calls.
        """
        if not HAS_SMTC:
            return None
        try:
            async def _fetch():
                manager = await _SMTCManager.request_async()
                session = manager.get_current_session()
                if not session:
                    return None
                playback = session.get_playback_info()
                # playback_status is a WinRT enum — convert to int to be safe
                # GlobalSystemMediaTransportControlsSessionPlaybackStatus:
                #   Closed=0, Opened=1, Changing=2, Stopped=3, Playing=4, Paused=5
                ps = int(playback.playback_status) if playback else -1
                if ps not in (4, 5):
                    return None
                props = await session.try_get_media_properties_async()
                if not props or not props.title:
                    return None

                # Timeline: position / duration (best-effort — some sources omit it)
                position_ms = 0
                duration_ms = 0
                try:
                    timeline = session.get_timeline_properties()
                    if timeline:
                        pos = timeline.position
                        end = timeline.end_time
                        if pos: position_ms = int(pos.total_seconds() * 1000)
                        if end: duration_ms  = int(end.total_seconds() * 1000)
                except Exception:
                    pass

                return {
                    "title":       props.title.strip(),
                    "artist":      (props.artist or "").strip(),
                    "album":       (props.album_title or "").strip(),
                    "source":      self._smtc_source_name(session.source_app_user_model_id),
                    "is_playing":  ps == 4,
                    "position_ms": position_ms,
                    "duration_ms": duration_ms,
                    "sampled_at":  time.time(),
                }

            # Schedule on the persistent loop — safe to call from any thread
            future = _asyncio.run_coroutine_threadsafe(_fetch(), _get_smtc_loop())
            result = future.result(timeout=4)
            if result:
                log.debug(f"SMTC: {result['source']} — {result['title']}")
            return result
        except Exception as e:
            log.warning(f"SMTC query failed: {e}")
            return None

    # ── Window-title fallback ─────────────────────────────────────────────────

    def _scan_titles_now_playing(self) -> dict | None:
        """Fallback: scan window titles for known music app patterns."""
        if not HAS_WIN32:
            return None

        result = {}

        # Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi) + Firefox
        BROWSER_CLASSES = {
            "Chrome_WidgetWin_1", "MozillaWindowClass", "MozillaDialogClass",
        }

        # Most-specific first so "YouTube Music" is matched before "YouTube"
        BROWSER_SOURCES = [
            (" - YouTube Music",  "YouTube Music"),
            (" - YouTube",        "YouTube"),
            (" - SoundCloud",     "SoundCloud"),
            (" | SoundCloud",     "SoundCloud"),
            (" - Spotify",        "Spotify"),
            (" - Deezer",         "Deezer"),
            (" - Apple Music",    "Apple Music"),
            (" - Tidal",          "TIDAL"),
            (" - TIDAL",          "TIDAL"),
            (" - Amazon Music",   "Amazon Music"),
            (" - Pandora",        "Pandora"),
            (" - Mixcloud",       "Mixcloud"),
            (" - Bandcamp",       "Bandcamp"),
            (" - Twitch",         "Twitch"),
        ]

        def _cb(hwnd, data):
            if data:
                return False
            try:
                cls   = win32gui.GetClassName(hwnd)
                title = win32gui.GetWindowText(hwnd).strip()
                if not title:
                    return True

                # ── Spotify desktop ───────────────────────────────────────
                if "Spotify" in cls and " - " in title:
                    clean = title
                    if clean.lower() not in ("spotify", "spotify premium", "spotify free", ""):
                        parts = clean.split(" - ", 1)
                        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                            data.update({"artist": parts[0].strip(), "title": parts[1].strip(), "source": "Spotify"})
                            return False

                # ── Browser-based (YouTube, SoundCloud, Deezer…) ─────────
                if cls in BROWSER_CLASSES:
                    for suffix, source in BROWSER_SOURCES:
                        if title.endswith(suffix):
                            track = title[:-len(suffix)].strip()
                            if track:
                                data.update({"title": track, "artist": "", "source": source})
                                return False

                # ── foobar2000 ────────────────────────────────────────────
                if title.endswith("[foobar2000]"):
                    track = title[:-len("[foobar2000]")].strip(" -")
                    if track:
                        data.update({"title": track, "artist": "", "source": "foobar2000"})
                        return False

                # ── Winamp ────────────────────────────────────────────────
                if "Winamp" in cls or title.endswith("- Winamp"):
                    track = title.replace("- Winamp", "").strip()
                    # Strip leading "N. " track number
                    import re
                    track = re.sub(r"^\d+\.\s*", "", track)
                    if track and track.lower() != "winamp":
                        data.update({"title": track, "artist": "", "source": "Winamp"})
                        return False

                # ── MusicBee ──────────────────────────────────────────────
                if title.endswith("- MusicBee"):
                    track = title[:-len("- MusicBee")].strip()
                    if track:
                        data.update({"title": track, "artist": "", "source": "MusicBee"})
                        return False

                # ── AIMP ──────────────────────────────────────────────────
                if "AIMP" in cls or title.endswith("- AIMP"):
                    track = title.replace("- AIMP", "").strip()
                    if track and track.lower() != "aimp":
                        data.update({"title": track, "artist": "", "source": "AIMP"})
                        return False

                # ── VLC ───────────────────────────────────────────────────
                if " - VLC media player" in title:
                    track = title.replace(" - VLC media player", "").strip()
                    if track and track.lower() != "vlc media player":
                        data.update({"title": track, "artist": "", "source": "VLC"})
                        return False

                # ── Windows Media Player ──────────────────────────────────
                if "WMPlayerApp" in cls and " - Windows Media Player" in title:
                    track = title.replace(" - Windows Media Player", "").strip()
                    if track:
                        data.update({"title": track, "artist": "", "source": "WMP"})
                        return False

            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(_cb, result)
        except Exception:
            pass
        return result or None

    def _detect_now_playing_mac(self) -> 'dict | None':
        """Query Spotify / Apple Music via AppleScript on macOS."""
        checks = [
            (
                "Spotify",
                'tell application "Spotify" to if player state is playing '
                'then return name of current track & "||SEP||" & artist of current track'
            ),
            (
                "Apple Music",
                'tell application "Music" to if player state is playing '
                'then return name of current track & "||SEP||" & artist of current track'
            ),
        ]
        for source, script in checks:
            try:
                res = subprocess.run(
                    ['osascript', '-e', script],
                    capture_output=True, text=True, timeout=3
                )
                if res.returncode == 0 and res.stdout.strip():
                    parts = res.stdout.strip().split('||SEP||', 1)
                    return {
                        "title": parts[0].strip(),
                        "artist": parts[1].strip() if len(parts) > 1 else "",
                        "source": source,
                        "is_playing": True,
                        "sampled_at": time.time(),
                    }
            except Exception:
                continue
        return None

    def _detect_now_playing_linux(self) -> 'dict | None':
        """Query playerctl for current media on Linux."""
        try:
            res = subprocess.run(
                ['playerctl', 'metadata', '--format',
                 '{{title}}\x1f{{artist}}\x1f{{playerName}}\x1f{{status}}'],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split('\x1f')
                title = parts[0].strip() if parts else ""
                if title:
                    return {
                        "title": title,
                        "artist": parts[1].strip() if len(parts) > 1 else "",
                        "source": parts[2].strip() if len(parts) > 2 else "Unknown",
                        "is_playing": parts[3].strip().lower() == 'playing' if len(parts) > 3 else True,
                        "sampled_at": time.time(),
                    }
        except Exception:
            pass
        return None

    def _detect_now_playing(self):
        """Detect currently playing media — platform-dispatched."""
        if PLATFORM == 'win32':
            return self._try_smtc() or self._scan_titles_now_playing()
        elif PLATFORM == 'darwin':
            return self._detect_now_playing_mac()
        else:
            return self._detect_now_playing_linux()

    # ── Two-Stage Error Detection ─────────────────────────────────────────────

    def _stage1_uai_triage(self, uia_data) -> dict:
        """
        Text-only Groq call: decide if the UAI data represents a real error.
        Returns {"error": bool, "description": str, "confidence": float,
        "file": str, "summary": str, "fix": str}.
        Respects stage1_cooldown so we don't hammer the API.

        Now includes local, zero-token project context (project name, branch,
        active file, stack/dirty/recent files — see project_context.py) in
        the prompt instead of just a bare window title, and asks for
        confidence/summary/fix in the same call so a confident result can
        skip Stage 2 vision entirely and the frontend can skip the separate
        /api/error_explain call that used to always follow.
        """
        import json
        from brain import think
        from screen_reader import _is_code_error
        from system_prompts import UAI_ERROR_TRIAGE_PROMPT

        now = time.time()
        empty = {"error": False, "description": "", "confidence": 0.0, "file": "", "summary": "", "fix": ""}
        if now - self.last_stage1_time < self.stage1_cooldown:
            return empty
        self.last_stage1_time = now

        project = uia_data.get("project") or {}
        context_lines = []
        if project:
            context_lines.append(f"Project: {project.get('project_name', '?')}")
            git = project.get("git") or {}
            if git.get("branch"):
                context_lines.append(f"Branch: {git['branch']}")
            if project.get("active_file"):
                context_lines.append(f"Active file: {project['active_file']}")
            if project.get("stack"):
                context_lines.append(f"Stack: {', '.join(project['stack'][:6])}")
            if git.get("dirty_files"):
                context_lines.append(f"Dirty files: {', '.join(git['dirty_files'][:5])}")
            if project.get("recent_files"):
                context_lines.append(f"Recently touched: {', '.join(project['recent_files'][:8])}")
        context_block = ("\n".join(context_lines) + "\n") if context_lines else ""

        # Prioritise text that already looks like a code error over generic
        # UI chrome — was an unfiltered top-25 slice; trimmed to 12 since the
        # project context block above now carries signal that used to have
        # to come from a longer visible-text dump.
        visible = list(uia_data.get("visible_texts", []))
        prioritised = [t for t in visible if _is_code_error(t)] + [t for t in visible if not _is_code_error(t)]
        visible_slice = prioritised[:12]

        uai_summary = (
            f"{context_block}"
            f"Window: {uia_data.get('window_title', 'Unknown')}\n"
            f"Errors: {', '.join(uia_data.get('errors', []))}\n"
            f"Visible: {', '.join(visible_slice)}"
        )
        try:
            resp = think(uai_summary, system_override=UAI_ERROR_TRIAGE_PROMPT)
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            # Strip markdown fences in case the model disobeys
            if "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            result = json.loads(content)
            return {
                "error": bool(result.get("error", False)),
                "description": result.get("description", ""),
                "confidence": float(result.get("confidence", 0.0) or 0.0),
                "file": result.get("file", ""),
                "summary": result.get("summary", ""),
                "fix": result.get("fix", ""),
            }
        except Exception as e:
            log.debug(f"Stage 1 UAI triage error: {e}")
            return empty

    def _stage2_vision_detail(self, stage1_description: str) -> str:
        """
        Vision call: take a screenshot and extract detailed error info.
        Only fires if stage2_cooldown has elapsed — vision calls are expensive.
        Falls back to the Stage 1 description if the call fails or is on cooldown.
        """
        from sensor_vision import take_screenshot
        from brain import think
        from system_prompts import SS_ERROR_DETAIL_PROMPT

        now = time.time()
        if now - self.last_stage2_time < self.stage2_cooldown:
            log.debug("Stage 2 vision on cooldown — using Stage 1 description only.")
            return ""
        self.last_stage2_time = now

        try:
            _, img_b64, _ = take_screenshot(crop_active=True, scale_to=1280)
            if not img_b64:
                log.warning("Stage 2: screenshot capture returned empty.")
                return ""
            prompt = f"Stage 1 UAI detected: {stage1_description}\n\nConfirm and detail the error visible on screen."
            resp = think(prompt, image_base64=img_b64, system_override=SS_ERROR_DETAIL_PROMPT)
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            log.info(f"Stage 2 vision detail: {content[:120]}...")
            return content or ""
        except Exception as e:
            log.warning(f"Stage 2 vision detail failed: {e}")
            return ""

    # Below this Stage 1 confidence, trust the screenshot more than the model's
    # own read of the UIA text dump and pay for a Stage 2 vision call. At or
    # above it, Stage 1 already has a clear enough picture that a screenshot
    # would just confirm what it already said — this is the single biggest
    # cost cut here, since Stage 2 is a full-resolution image call.
    STAGE2_CONFIDENCE_GATE = 0.75

    def _run_two_stage_error_detect(self, uia_data):
        """
        Fire Stage 1, then Stage 2 only when Stage 1 wasn't confident, in a
        background thread so the feed loop doesn't block. Non-blocking
        trylock so overlapping runs are skipped, not queued.
        """
        if not self._stage_lock.acquire(blocking=False):
            log.debug("Two-stage detection already running — skipping.")
            return

        def _run():
            try:
                result = self._stage1_uai_triage(uia_data)
                if not result["error"] or not result["description"]:
                    return
                log.warning(
                    f"Stage 1 confirmed error on screen (confidence={result['confidence']:.2f}): "
                    f"{result['description']}"
                )

                vision_detail = ""
                if result["confidence"] < self.STAGE2_CONFIDENCE_GATE:
                    vision_detail = self._stage2_vision_detail(result["description"])
                else:
                    log.debug(f"Stage 1 confidence {result['confidence']:.2f} — skipping Stage 2 vision.")

                if self.callback:
                    self.callback("error_island", {
                        "error_message": result["description"],
                        "context": vision_detail,   # empty string → frontend uses error_message alone
                        # Stage 1 now returns enough to render the island
                        # directly — the frontend used this event to make a
                        # THIRD LLM call (/api/error_explain) for exactly
                        # this; passing summary/fix through here removes that
                        # call whenever Stage 1 supplied them.
                        "summary": result["summary"],
                        "fix": result["fix"],
                        "file": result["file"],
                    })
            except Exception as e:
                log.error(f"Two-stage error detection crashed: {e}")
            finally:
                self._stage_lock.release()

        threading.Thread(target=_run, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────────

    def _loop(self):
        last_mem_extraction = time.time()
        error_keywords = ["traceback", "error", "exception", "syntaxerror", "typeerror", "cannot find", "undefined", "null reference"]
        
        while self.running:
            loop_start = time.time()
            title, process = self.get_active_info()
            current_time = time.time()
            focus_changed = False
            previous_process = self.active_process_name  # snapshot before update

            # --- Detection Logic: Window Changes ---
            if title != self.active_window_title or process != self.active_process_name:
                log.info(f"Focus changed: {process} -> {title[:50]}...")
                self.active_window_title = title
                self.active_process_name = process
                focus_changed = True
                
                # Reset Timers
                self.window_start_time = current_time
                self.vscode_start_time = current_time
                self.fired_stuck_session = False
                self.fired_vscode_session = False
                
                event = f"{time.strftime('%H:%M:%S')} - {process}: {title}"
                self.history.append(event)
                
                if self.callback:
                    self.callback("feed_update", {
                        "active_window": title,
                        "active_process": process,
                        "timestamp": current_time
                    })

            # ── Flow State ────────────────────────────────────────────────────
            is_focus_app = bool(process and process.lower() in self.focus_apps)
            if focus_changed:
                # Leaving a focus app — report flow_broken if duration >= 1 min
                if self.flow_start_time and previous_process and previous_process.lower() in self.focus_apps:
                    flow_dur = (current_time - self.flow_start_time) / 60
                    if flow_dur >= 1 and self.callback:
                        self.callback("flow_broken", {
                            "duration_minutes": round(flow_dur, 1),
                            "app": self.flow_app
                        })
                    self.flow_start_time = 0.0
                    self.flow_app = ""
                    self.flow_last_milestone = -1
                # Entering a focus app — start timer
                if is_focus_app:
                    self.flow_start_time = current_time
                    self.flow_app = process
                    self.flow_last_milestone = -1

            # Report flow milestones every 5 minutes starting at 25 min
            if is_focus_app and self.flow_start_time:
                flow_dur_min = int((current_time - self.flow_start_time) / 60)
                milestone = flow_dur_min // 5
                if flow_dur_min >= 25 and milestone != self.flow_last_milestone:
                    self.flow_last_milestone = milestone
                    if self.callback:
                        self.callback("flow_state", {
                            "duration_minutes": flow_dur_min,
                            "started_at": self.flow_start_time,
                            "app": self.flow_app
                        })

            # ── Productivity Score (report only — accumulate after sleep) ────────
            if current_time - self.last_productivity_report >= self.productivity_report_interval:
                self.last_productivity_report = current_time
                total = max(self.productivity_total_seconds, 1)
                score = int((self.productivity_focus_seconds / total) * 100)
                if self.callback:
                    self.callback("productivity_score", {"score": score})

            # --- UIA Continuous Scan & Error Monitor ---
            if current_time - self.last_uia_scan_time > 10 or focus_changed:
                self.last_uia_scan_time = current_time
                try:
                    from screen_reader import read_screen, fingerprint
                    from project_context import get_project_context
                    uia_data = read_screen()
                    if uia_data and "error" not in uia_data and (
                        uia_data.get("focused_text") or uia_data.get("visible_texts") or uia_data.get("errors")
                    ):
                        # Local, zero-token project context (repo, branch, active
                        # file, dirty files) — attached to the existing event so
                        # no new event type / extra round trip is needed. Also
                        # doubles as the reliable "is this actually an IDE"
                        # check, replacing the process-name match below.
                        editor_info = parse_editor_title(title, process)
                        if editor_info:
                            pid = self._get_active_pid()
                            uia_data["project"] = get_project_context(title, process, pid)

                        if self.callback:
                            self.callback("uia_update", uia_data)

                        error_records = uia_data.get("error_records") or [
                            {"text": e, "fingerprint": fingerprint(e)} for e in uia_data.get("errors", [])
                        ]

                        # ── Error Streak Tracking ──────────────────────────────
                        # Keyed by fingerprint so "TypeError at file.py:42" and
                        # "TypeError at file.py:57" count as one ongoing streak
                        # instead of two, which is what raw-text keys used to do.
                        active_fps = {r["fingerprint"]: r["text"] for r in error_records}
                        for fp, text in active_fps.items():
                            if fp not in self.error_streak_start:
                                self.error_streak_start[fp] = {"text": text, "start": current_time}
                                self.error_streak_notified[fp] = -1
                        for fp in list(self.error_streak_start.keys()):
                            if fp not in active_fps:
                                entry = self.error_streak_start[fp]
                                dur = int((current_time - entry["start"]) / 60)
                                if dur >= 1 and self.callback:
                                    self.callback("error_resolved", {
                                        "error": entry["text"],
                                        "duration_minutes": dur
                                    })
                                del self.error_streak_start[fp]
                                self.error_streak_notified.pop(fp, None)
                        for fp, entry in list(self.error_streak_start.items()):
                            dur = int((current_time - entry["start"]) / 60)
                            if dur > self.error_streak_notified.get(fp, -1) and dur >= 1:
                                self.error_streak_notified[fp] = dur
                                if self.callback:
                                    self.callback("error_streak", {
                                        "error": entry["text"],
                                        "duration_minutes": dur
                                    })

                        # ── IDE proactive toast (light, no LLM) ──────────────
                        # Was `process.lower() in ["code.exe","code","electron"]`
                        # — "electron" also matches Slack/Discord/Postman, so
                        # those toasted "persistent error in VS Code" on their
                        # own unrelated notification text. parse_editor_title
                        # only returns non-None for a title shaped like a real
                        # IDE window with a file open.
                        if editor_info and active_fps:
                            for fp, text in active_fps.items():
                                self.screen_error_frequency[fp] = self.screen_error_frequency.get(fp, 0) + 1
                                if self.screen_error_frequency[fp] >= 3 and fp not in self.fired_screen_errors:
                                    log.warning(f"Persistent screen error in {editor_info['editor']}: {text}")
                                    if self.callback:
                                        self.callback("proactive_message", {
                                            "message": f"looks like you're facing a persistent error: '{text}'. want me to debug it?",
                                            "suggestions": ["debug this error", "explain what is wrong"]
                                        })
                                    self.fired_screen_errors.add(fp)

                            # Clean up resolved errors
                            for fp in list(self.screen_error_frequency.keys()):
                                if fp not in active_fps:
                                    self.screen_error_frequency[fp] -= 1
                                    if self.screen_error_frequency[fp] <= 0:
                                        del self.screen_error_frequency[fp]
                                        self.fired_screen_errors.discard(fp)

                        # ── Two-stage error detection (all apps) ─────────────
                        # Stage 1: text-only Groq confirms the error from UAI.
                        # Stage 2: screenshot vision extracts full details.
                        # Both run in a background thread; cooldowns prevent spam.
                        # Gated additionally by fingerprint identity, not just
                        # the global cooldown timers — a still-open error that
                        # keeps appearing on screen used to re-enter this path
                        # (and burn a Stage 1 call) every time the cooldown
                        # window happened to elapse, even though nothing new
                        # was on screen.
                        if active_fps:
                            now = current_time
                            fresh_fps = {
                                fp for fp in active_fps
                                if now - self.fired_error_fps.get(fp, 0) > self.fired_error_fp_ttl
                            }
                            if fresh_fps:
                                for fp in fresh_fps:
                                    self.fired_error_fps[fp] = now
                                stale_cutoff = now - self.fired_error_fp_ttl
                                self.fired_error_fps = {
                                    fp: t for fp, t in self.fired_error_fps.items() if t > stale_cutoff
                                }
                                self._run_two_stage_error_detect(uia_data)
                except Exception as e:
                    log.error(f"UIA continuous background scan failed: {e}")
            
            # --- 1. Stuck Detection ---
            if not self.fired_stuck_session and (current_time - self.window_start_time > 600): # 10 minutes
                if self.callback and title != "Unknown":
                    log.info(f"Stuck detected on window: {title}")
                    self.callback("proactive_message", {
                        "message": f"you've been on {title} for a while. need a hand?",
                        "suggestions": ["summarise what i've done", "take a break reminder"]
                    })
                    self.fired_stuck_session = True

            # --- 4. IDE Stuck ---
            # Was `process.lower() in ["code.exe","code","electron"]`, which
            # also matched every other Electron app (Slack, Discord, Postman)
            # on the frontmost-window check that runs every tick, not just on
            # UIA scan ticks — so this fired for "stuck in VS Code" while the
            # user was just idling in Slack. Cheap string check, safe to run
            # unconditionally.
            is_ide = parse_editor_title(title, process) is not None
            if is_ide and not self.fired_vscode_session and (current_time - self.vscode_start_time > 420): # 7 minutes
                 if self.callback:
                    log.info("Stuck detected in IDE.")
                    self.callback("proactive_message", {
                        "message": "been on this file a while. stuck?",
                        "suggestions": ["review my code", "find the bug"]
                    })
                    self.fired_vscode_session = True

            # --- Clipboard/Error Detection ---
            try:
                clip_content = pyperclip.paste()
                if clip_content:
                    # --- 3. Clipboard Watcher ---
                    if clip_content != self.last_clipboard:
                        low_clip = clip_content.lower()
                        if any(x in low_clip for x in ["traceback", "at line", "file \"", "→"]):
                            log.info("Error detected in clipboard.")
                            if self.callback:
                                self.callback("proactive_message", {
                                    "message": "looks like you copied an error. want me to fix it?",
                                    "suggestions": ["debug this", "explain this error"]
                                })
                        self.last_clipboard = clip_content

                    # --- 2. Error Repetition Detection ---
                    low_clip = clip_content.lower()
                    if any(kw in low_clip for kw in error_keywords):
                        # Avoid duplicate entries in history for the same copy
                        if not self.error_history or self.error_history[-1][1] != clip_content:
                            self.error_history.append((current_time, clip_content))
                        
                        # Cleanup old errors (> 3 mins)
                        self.error_history = [e for e in self.error_history if current_time - e[0] <= 180]

                        # Check for repeats (Fuzzy Match > 80%)
                        if len(self.error_history) >= 2 and (current_time - self.last_error_fire_time > 300):
                            current_error = clip_content
                            matches = 0
                            for _, old_error in self.error_history[:-1]:
                                ratio = difflib.SequenceMatcher(None, current_error, old_error).ratio()
                                if ratio > 0.8:
                                    matches += 1
                            
                            if matches >= 1: # At least one similar error in last 3 mins
                                log.warning("Repeating error detected via clipboard.")
                                if self.callback:
                                    self.callback("proactive_message", {
                                        "message": "same error twice. want me to debug it?",
                                        "suggestions": ["debug this", "search for fix"]
                                    })
                                # Update cooldown outside the callback guard so the
                                # timer advances even when no callback is registered.
                                self.last_error_fire_time = current_time
                                self.error_history = [] # Clear after firing
            except Exception as e:
                log.debug(f"Clipboard read error: {e}")

            # Extract memories every 15 minutes (only if history grew)
            if current_time - last_mem_extraction > 900 and len(self.history) > getattr(self, '_last_mem_history_len', 0):
                self._extract_memories()
                self._last_mem_history_len = len(self.history)
                last_mem_extraction = current_time

            # ── Now Playing (every 5 s) ───────────────────────────────────────
            if current_time - self.last_now_playing_check >= self.now_playing_interval:
                self.last_now_playing_check = current_time
                np_state = self._detect_now_playing() or {}
                was_playing = bool(self.last_now_playing_state)
                is_now_playing = bool(np_state)
                # Always push while playing (keeps sampled_at fresh for the
                # frontend progress bar); push once when playback stops so the
                # strip clears.
                if is_now_playing or was_playing:
                    self.last_now_playing_state = np_state
                    if self.callback:
                        self.callback("now_playing", np_state)  # empty dict = stopped

            # ── Island Skills (pluggable strips) ──────────────────────────────
            self._poll_island_skills(current_time)

            time.sleep(3)

            # Accumulate real elapsed time (UIA scan + all work + sleep) for accurate score
            loop_elapsed = time.time() - loop_start
            self.productivity_total_seconds += loop_elapsed
            if is_focus_app:
                self.productivity_focus_seconds += loop_elapsed

if __name__ == "__main__":
    def mock_cb(event, data):
        print(f"[{event}] {data}")
    fm = FeedManager(callback=mock_cb)
    fm.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    fm.stop()
