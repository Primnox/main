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

    def _loop(self):
        last_mem_extraction = time.time()
        error_keywords = ["traceback", "error", "exception", "syntaxerror", "typeerror", "cannot find", "undefined", "null reference"]
        
        while self.running:
            title, process = self.get_active_info()
            current_time = time.time()
            focus_changed = False
            
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

            # --- UIA Continuous Scan & Error Monitor ---
            if current_time - self.last_uia_scan_time > 10 or focus_changed:
                self.last_uia_scan_time = current_time
                try:
                    from screen_reader import read_screen
                    uia_data = read_screen()
                    if uia_data and "error" not in uia_data:
                        if self.callback:
                            self.callback("uia_update", uia_data)
                        
                        # Proactive Screen Error Assist (VS Code focused)
                        is_vscode = process.lower() in ["code.exe", "code"]
                        if is_vscode:
                            errors = uia_data.get("errors", [])
                            # Increment frequency of detected errors
                            for err in errors:
                                self.screen_error_frequency[err] = self.screen_error_frequency.get(err, 0) + 1
                                if self.screen_error_frequency[err] >= 3 and err not in self.fired_screen_errors:
                                    log.warning(f"Persistent screen error detected in VS Code: {err}")
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
                    
            time.sleep(3)

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
