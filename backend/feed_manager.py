import threading
import time
import psutil
import pyperclip
import difflib
from pathlib import Path
from brain import think
from memory import add_memory
from logger import get_logger

log = get_logger("feed")

try:
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    log.warning("win32 libraries not found, window tracking limited.")

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
        self.error_streak_start: dict = {}      # {error_text: start_time}
        self.error_streak_notified: dict = {}   # {error_text: last_reported_minute}

        # ── Feature: Flow State ──────────────────────────────────────────
        self.focus_apps = {
            "code.exe", "code", "pycharm64.exe", "idea64.exe",
            "sublime_text.exe", "obsidian.exe", "nvim.exe", "vim.exe",
            "cmd.exe", "powershell.exe", "windowsterminal.exe", "wt.exe"
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
        if not HAS_WIN32: return "Unknown", "Unknown"
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd: return "Unknown", "Unknown"
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid).name()
            return title, process
        except Exception as e:
            log.error(f"Failed to get active window info: {e}")
            return "Unknown", "Unknown"

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
            resp = think("Extract key memories from this activity log. focus on projects, tasks, and important context.", context=recent_log)
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content and "none" not in content.lower():
                log.info(f"Memory extracted: {content[:100]}...")
                add_memory(content)
                if self.callback:
                    self.callback("memory_updated", {"text": content})
        except Exception as e:
            log.error(f"Memory extraction failed: {e}")

    def generate_daily_debrief(self):
        """Primnox: Summarize the day's activity."""
        log.info("Generating daily debrief summary...")
        log_content = "\n".join(self.history)
        try:
            resp = think("Generate a professional daily debrief. summarize my productivity and key achievements.", context=log_content)
            debrief = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            log.info("Daily debrief generated.")
            if self.callback:
                self.callback("daily_debrief", {"debrief": debrief})
            return debrief
        except Exception as e:
            log.error(f"Debrief generation failed: {e}")
            return "failed to generate debrief."

    # ── Now Playing Detection ─────────────────────────────────────────────────

    def _detect_now_playing(self):
        """Detect currently playing track from Spotify window title."""
        if not HAS_WIN32:
            return None
        result = {}
        def _cb(hwnd, data):
            if data:
                return False  # already found, stop enumeration
            try:
                cls = win32gui.GetClassName(hwnd)
                title = win32gui.GetWindowText(hwnd)
                # Spotify: title is "Artist - Track" when playing
                if "Spotify" in cls and " - " in title:
                    clean = title.strip()
                    if clean.lower() not in ("spotify", "spotify premium", "spotify free", ""):
                        parts = clean.split(" - ", 1)
                        if parts[0].strip() and parts[1].strip():
                            data.update({
                                "artist": parts[0].strip(),
                                "title": parts[1].strip(),
                                "source": "Spotify"
                            })
                            return False  # stop enumeration immediately after finding
            except Exception:
                pass
            return True
        try:
            win32gui.EnumWindows(_cb, result)
        except Exception:
            pass  # EnumWindows raises pywintypes.error when callback returns False (early exit)
        return result or None

    # ── Two-Stage Error Detection ─────────────────────────────────────────────

    def _stage1_uai_triage(self, uia_data) -> tuple:
        """
        Text-only Groq call: decide if the UAI data represents a real error.
        Returns (error_detected: bool, description: str).
        Respects stage1_cooldown so we don't hammer the API.
        """
        import json
        from brain import think
        from system_prompts import UAI_ERROR_TRIAGE_PROMPT

        now = time.time()
        if now - self.last_stage1_time < self.stage1_cooldown:
            return False, ""
        self.last_stage1_time = now

        uai_summary = (
            f"Window: {uia_data.get('window_title', 'Unknown')}\n"
            f"Errors: {', '.join(uia_data.get('errors', []))}\n"
            f"Visible: {', '.join(list(uia_data.get('visible_texts', []))[:25])}"
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
            return bool(result.get("error", False)), result.get("description", "")
        except Exception as e:
            log.debug(f"Stage 1 UAI triage error: {e}")
            return False, ""

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

    def _run_two_stage_error_detect(self, uia_data):
        """
        Fire Stage 1 + Stage 2 in a background thread so the feed loop doesn't block.
        Uses a non-blocking trylock so overlapping runs are skipped, not queued.
        """
        if not self._stage_lock.acquire(blocking=False):
            log.debug("Two-stage detection already running — skipping.")
            return

        def _run():
            try:
                error_detected, description = self._stage1_uai_triage(uia_data)
                if not error_detected or not description:
                    return
                log.warning(f"Stage 1 confirmed error on screen: {description}")

                # Stage 2 — screenshot only if Stage 2 cooldown allows
                vision_detail = self._stage2_vision_detail(description)

                if self.callback:
                    self.callback("error_island", {
                        "error_message": description,
                        "context": vision_detail   # empty string → frontend uses error_message alone
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
                    from screen_reader import read_screen
                    uia_data = read_screen()
                    if uia_data and "error" not in uia_data:
                        if self.callback:
                            self.callback("uia_update", uia_data)
                        
                        errors = uia_data.get("errors", [])

                        # ── Error Streak Tracking ──────────────────────────────
                        active_errors = set(errors)
                        # Start new streaks for freshly appeared errors
                        for err in active_errors:
                            if err not in self.error_streak_start:
                                self.error_streak_start[err] = current_time
                                self.error_streak_notified[err] = -1
                        # Resolve streaks for errors that disappeared
                        for err in list(self.error_streak_start.keys()):
                            if err not in active_errors:
                                dur = int((current_time - self.error_streak_start[err]) / 60)
                                if dur >= 1 and self.callback:
                                    self.callback("error_resolved", {
                                        "error": err,
                                        "duration_minutes": dur
                                    })
                                del self.error_streak_start[err]
                                self.error_streak_notified.pop(err, None)
                        # Report growing streaks (at each new minute)
                        for err, start in list(self.error_streak_start.items()):
                            dur = int((current_time - start) / 60)
                            if dur > self.error_streak_notified.get(err, -1) and dur >= 1:
                                self.error_streak_notified[err] = dur
                                if self.callback:
                                    self.callback("error_streak", {
                                        "error": err,
                                        "duration_minutes": dur
                                    })

                        # ── VS Code proactive toast (light, no LLM) ──────────
                        is_vscode = process.lower() in ["code.exe", "code"]
                        if is_vscode and errors:
                            for err in errors:
                                self.screen_error_frequency[err] = self.screen_error_frequency.get(err, 0) + 1
                                if self.screen_error_frequency[err] >= 3 and err not in self.fired_screen_errors:
                                    log.warning(f"Persistent screen error in VS Code: {err}")
                                    if self.callback:
                                        self.callback("proactive_message", {
                                            "message": f"looks like you're facing a persistent error in VS Code: '{err}'. want me to debug it?",
                                            "suggestions": ["debug this error", "explain what is wrong"]
                                        })
                                    self.fired_screen_errors.add(err)

                            # Clean up resolved errors
                            for err in list(self.screen_error_frequency.keys()):
                                if err not in errors:
                                    self.screen_error_frequency[err] -= 1
                                    if self.screen_error_frequency[err] <= 0:
                                        del self.screen_error_frequency[err]
                                        self.fired_screen_errors.discard(err)

                        # ── Two-stage error detection (all apps) ─────────────
                        # Stage 1: text-only Groq confirms the error from UAI.
                        # Stage 2: screenshot vision extracts full details.
                        # Both run in a background thread; cooldowns prevent spam.
                        if errors:
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

            # --- 4. VS Code Stuck ---
            is_vscode = process.lower() in ["code.exe", "code"]
            if is_vscode and not self.fired_vscode_session and (current_time - self.vscode_start_time > 420): # 7 minutes
                 if self.callback:
                    log.info("Stuck detected in VS Code.")
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
                                    self.last_error_fire_time = current_time
                                    self.error_history = [] # Clear after firing
            except Exception as e:
                log.debug(f"Clipboard read error: {e}")

            # Extract memories every 5 minutes
            if current_time - last_mem_extraction > 300:
                self._extract_memories()
                last_mem_extraction = current_time

            # ── Now Playing (every 5 s) ───────────────────────────────────────
            if current_time - self.last_now_playing_check >= self.now_playing_interval:
                self.last_now_playing_check = current_time
                np_state = self._detect_now_playing() or {}
                if np_state != self.last_now_playing_state:
                    self.last_now_playing_state = np_state
                    if self.callback:
                        self.callback("now_playing", np_state)  # empty dict = stopped

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
