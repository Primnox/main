# backend/core.py
from dotenv import load_dotenv
load_dotenv()  # ABSOLUTE FIRST LINE

from pathlib import Path
import threading
from settings_manager import load_settings
from memory import get_memory, add_memory, delete_memory, list_memories, search_memories
from notes_manager import add_note, get_notes, add_task, get_tasks, complete_task
from chat_manager import append_message_to_session
from screen_reader import read_screen
from sensor_vision import describe_screen
from vad_listener import VADListener
from voice_id import identify_speaker
from brain import transcribe, think, think_stream
from context_builder import build_context
from feed_manager import FeedManager
from proactive import ProactiveEngine
from meeting_recorder import MeetingRecorder
from tools import web_search
from voice import speak
from skills.skill_router import route_skill
from reminder_manager import parse_reminder, add_reminder, set_callback as set_reminder_callback
from logger import get_logger
import time
import re
import tempfile

log = get_logger("core")

class PrimnoxCore:
    def __init__(self):
        log.info("Initializing PrimnoxCore...")
        self.settings = load_settings()
        self.mic_muted = True
        self.incognito = False
        self.broadcast_callback = None
        self.latest_uia_data = {"window_title": "Unknown", "focused_text": "", "visible_texts": [], "errors": []}

        # Background task timers
        self._last_emotion_check = 0     # run every 30 min
        self._last_profile_update = 0    # run every 60 min
        self._last_backup = 0            # run every 6 hours
        self._proactive_feed_counter = 0 # fire every N feed events

        log.info("Starting FeedManager...")
        self.feed = FeedManager(callback=self.on_feed_update)
        self.feed.start()

        self.vad = None  # Disabled per user request

        log.info("Starting MeetingRecorder...")
        self.recorder = MeetingRecorder()
        self.recorder.start()

        self.proactive = ProactiveEngine()

        # Start the lightweight background worker (reminders + periodic tasks)
        threading.Thread(target=self._background_worker, daemon=True, name="primnox-bg").start()

        log.info("PrimnoxCore initialization complete.")

    def register_broadcast_callback(self, cb):
        log.debug("Registering broadcast callback.")
        self.broadcast_callback = cb
        # Wire reminders to broadcast as soon as we have a callback
        set_reminder_callback(cb)
        # Wire tool-execution events (note_added, task_added, memory_updated)
        try:
            from tools import set_broadcast_callback as set_tool_broadcast_callback
            set_tool_broadcast_callback(cb)
        except Exception as e:
            log.warning(f"Could not wire tool broadcast callback: {e}")

    def _background_worker(self):
        """
        Lightweight periodic worker — runs every 60 s.
        Handles: emotion analysis (30 min), profiler (60 min).
        Reminder firing is handled inside reminder_manager's own daemon thread.
        """
        while True:
            time.sleep(60)
            now = time.time()
            try:
                # ── Emotion analysis every 30 minutes ──────────────────────
                if now - self._last_emotion_check > 1800:
                    self._last_emotion_check = now
                    log.debug("Background: running emotion analysis...")
                    threading.Thread(
                        target=self._run_emotion_safe,
                        daemon=True,
                        name="emotion-bg"
                    ).start()

                # ── Profiler update every 60 minutes ───────────────────────
                if now - self._last_profile_update > 3600:
                    self._last_profile_update = now
                    log.debug("Background: running profiler update...")
                    threading.Thread(
                        target=self._run_profiler_safe,
                        daemon=True,
                        name="profiler-bg"
                    ).start()

                # ── Auto-backup every 6 hours ───────────────────────────
                if now - self._last_backup > 21600:
                    self._last_backup = now
                    log.debug("Background: running auto-backup...")
                    threading.Thread(
                        target=self._run_backup_safe,
                        daemon=True,
                        name="backup-bg"
                    ).start()
            except Exception as e:
                log.error(f"Background worker error: {e}")

    def _run_emotion_safe(self):
        try:
            from emotion_agent import run_emotion_analysis
            run_emotion_analysis()
            # Reload settings so the updated mood feeds into the next brain call
            self.settings = load_settings()
            mood = self.settings.get("current_mood")
            if mood and self.broadcast_callback:
                self.broadcast_callback("emotion_updated", {"mood": mood})
        except Exception as e:
            log.warning(f"Emotion analysis failed silently: {e}")

    def _run_profiler_safe(self):
        try:
            from profiler import run_background_profiler
            run_background_profiler()
            self.settings = load_settings()
            profile = self.settings.get("onboarding_profile", {})
            if profile and self.broadcast_callback:
                self.broadcast_callback("profile_updated", {"profile": profile})
        except Exception as e:
            log.warning(f"Profiler update failed silently: {e}")

    def _run_backup_safe(self):
        try:
            import zipfile, time as _t
            from settings_manager import get_appdata_dir
            appdata = get_appdata_dir()
            backups_dir = appdata / "backups"
            backups_dir.mkdir(parents=True, exist_ok=True)
            stamp = _t.strftime("%Y%m%d_%H%M%S")
            zip_path = backups_dir / f"backup_{stamp}.zip"
            files_to_backup = [appdata / "memory.db", appdata / "chat.db", appdata / "settings.json"]
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fp in files_to_backup:
                    if fp.exists():
                        zf.write(fp, fp.name)
            # Keep 5 most recent
            for old in sorted(backups_dir.glob("backup_*.zip"), reverse=True)[5:]:
                try:
                    old.unlink()
                except Exception:
                    pass
            size_kb = zip_path.stat().st_size // 1024
            log.info(f"Auto-backup complete: {zip_path.name} ({size_kb} KB)")
            if self.broadcast_callback:
                self.broadcast_callback("backup_complete", {"path": str(zip_path), "size_kb": size_kb})
        except Exception as e:
            log.error(f"Auto-backup failed: {e}")
            if self.broadcast_callback:
                self.broadcast_callback("backup_failed", {"error": str(e)})

    def on_vad_state_change(self, state):
        log.info(f"VAD state changed: {state}")
        if self.broadcast_callback:
            self.broadcast_callback("state", {"value": state})

    def on_voice_state_change(self, state):
        log.info(f"Voice state changed: {state}")
        if self.broadcast_callback:
            self.broadcast_callback("state", {"value": state})

    def on_feed_update(self, event, data):
        log.debug(f"Feed update: {event}")
        if event == "uia_update":
            self.latest_uia_data = data
        if self.broadcast_callback:
            self.broadcast_callback(event, data)

        # ── Proactive engine: fire every 20 feed events ──────────────────
        if not self.incognito:
            self._proactive_feed_counter += 1
            if self._proactive_feed_counter >= 20:
                self._proactive_feed_counter = 0
                window = self.latest_uia_data.get("window_title", "Unknown")
                threading.Thread(
                    target=self._run_proactive_safe,
                    args=(window,),
                    daemon=True,
                    name="proactive-bg"
                ).start()

    def _run_proactive_safe(self, context_summary: str):
        try:
            # Build richer context: active window + last 10 feed events
            recent_feed = list(self.feed.history[-10:])
            rich_context = f"Active Window: {context_summary}"
            if recent_feed:
                rich_context += "\nRecent Activity:\n" + "\n".join(recent_feed)
            comment = self.proactive.analyze_proactively(rich_context)
            if comment and self.broadcast_callback:
                self.broadcast_callback("proactive_message", {
                    "message": comment,
                    "suggestions": []
                })
        except Exception as e:
            log.warning(f"Proactive engine error: {e}")

    def on_speech(self, text, audio_bytes):
        if self.mic_muted:
            log.info("Speech detected, but mic is muted. Discarding.")
            return
        log.info("Speech detected, processing...")
        # Write to unique temp file for speaker ID (prevents race conditions)
        audio_path = None
        try:
            fd, audio_path = tempfile.mkstemp(suffix=".wav")
            with open(fd, "wb") as f:
                f.write(audio_bytes)
        except Exception as e:
            log.error(f"Failed to write temp audio: {e}")
            return
            
        log.info(f"Transcription: {text}")
        if self.broadcast_callback:
            self.broadcast_callback("transcript", {"text": text})
        
        try:
            speaker, conf = identify_speaker(audio_path)
            log.info(f"Speaker identified: {speaker} (conf: {conf})")
        except Exception as e:
            log.error(f"Speaker identification failed: {e}")
            speaker = "Unknown"
        finally:
            # Cleanup temp file
            try:
                import os
                os.remove(audio_path)
            except Exception:
                pass
        
        self._process_input(text, speaker, input_mode="voice")

    def handle_text_input(self, text: str, session_id="current", display_text: str = None):
        """Process a user message. If display_text is provided, it is shown in
        the chat UI while `text` (which may contain extracted file contents) is
        sent to the LLM for processing."""
        shown = display_text or text
        log.info(f"Handling text input: {shown[:50]}...")
        if not self.incognito:
            append_message_to_session(session_id, shown, speaker="User")
        
        if self.broadcast_callback:
            self.broadcast_callback("message", {
                "sender": "User",
                "text": shown,
                "speaker": "User"
            })
            
        self._process_input(text, "User", input_mode="text", session_id=session_id,
                            user_text=display_text or text)


    def _process_input(self, raw_text, speaker, input_mode="text", session_id="current", user_text=None):
        """Unified Processing Logic for Voice and Text (Agentic).
        
        raw_text:  full text sent to LLM (may include extracted file contents).
        user_text: the original short user message (used for trigger matching).
        """
        if not raw_text:
            log.debug("Empty input, skipping.")
            return

        # Use user_text for trigger/reminder matching; fall back to raw_text
        trigger_text = user_text or raw_text

        # ── Reminder intercept (before LLM) ──────────────────────────────
        reminder = parse_reminder(trigger_text)
        if reminder:
            add_reminder(reminder["message"], reminder["delay_secs"])
            mins = reminder["delay_secs"] // 60
            secs = reminder["delay_secs"] % 60
            time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            reply = f"got it — i'll remind you to **{reminder['message']}** in {time_str}"
            log.info(f"Reminder set: {reminder}")
            if not self.incognito:
                append_message_to_session(session_id, reply, speaker="Primnox")
            if self.broadcast_callback:
                self.broadcast_callback("state", {"value": "idle"})
                self.broadcast_callback("message", {
                    "sender": "Primnox",
                    "text": reply,
                    "speaker": "Primnox",
                })
            return

        if self.broadcast_callback:
            self.broadcast_callback("state", {"value": "thinking"})

        if input_mode != "text" and not self.incognito:
            append_message_to_session(session_id, raw_text, speaker=speaker)

        log.info(f"Agentic processing input '{trigger_text[:30]}'")

        # ── Skill intercept (before LLM) ─────────────────────────────────
        # Only match triggers against the original user message, NOT file contents
        try:
            from skills.skill_router import get_skill_for_trigger
            skill_cls = get_skill_for_trigger(trigger_text)
            if skill_cls:
                log.info(f"Skill trigger matched: {skill_cls.name}")
                # Broadcast skill_started so the frontend task pill appears
                if self.broadcast_callback:
                    self.broadcast_callback("skill_started", {
                        "skill": skill_cls.name,
                        "label": skill_cls.name,
                        "description": getattr(skill_cls, "description", skill_cls.name),
                    })
                notes_count = 0
                try:
                    notes_count = len(get_notes())
                except Exception:
                    pass
                skill_result = route_skill(
                    user_message=raw_text,
                    session_id=session_id,
                    metadata={
                        "notes_count": notes_count,
                        "feed_history": list(self.feed.history[-50:]),
                    }
                )
                reply = skill_result.get("output_text") or skill_result.get("error") or "done."
                # Broadcast skill_complete with outcome
                if self.broadcast_callback:
                    self.broadcast_callback("skill_complete", {
                        "skill": skill_cls.name,
                        "label": skill_cls.name,
                        "success": skill_result.get("success", True),
                        "output_path": skill_result.get("output_path"),
                    })
                    # If skill produced a file, fire a separate file_ready event
                    if skill_result.get("output_path"):
                        self.broadcast_callback("file_ready", {
                            "skill": skill_cls.name,
                            "path": skill_result["output_path"],
                        })
                if not self.incognito and reply:
                    append_message_to_session(session_id, reply, speaker="Primnox")
                if self.broadcast_callback:
                    self.broadcast_callback("state", {"value": "idle"})
                    self.broadcast_callback("message", {
                        "sender": "Primnox",
                        "text": reply,
                        "speaker": "Primnox",
                    })
                return
        except Exception as e:
            log.warning(f"Skill intercept error (falling through to LLM): {e}")

        # Sensor Fusion: Gather UIA and basic context
        log.debug("Gathering screen state (UIA)...")
        uia_data = self.latest_uia_data or {"window_title": "Unknown", "focused_text": "", "visible_texts": [], "errors": []}

        # ── Semantic memory injection ─────────────────────────────────────
        # Search for memories relevant to the user's message and inject them.
        memory_context = ""
        try:
            relevant = search_memories(raw_text, limit=5)
            if relevant:
                mem_lines = "\n".join(f"- {m['text']}" for m in relevant)
                memory_context = f"\n[RELEVANT MEMORIES]:\n{mem_lines}\n"
                log.debug(f"Injected {len(relevant)} relevant memories into context")
        except Exception as e:
            log.warning(f"Memory injection failed: {e}")

        # Build Context for Primnox
        log.debug("Building context...")
        current_time = time.strftime('%I:%M %p')

        # Inject a sample of visible UI texts (UIA accessibility tree) so the
        # LLM can see what's actually on screen without a full vision call.
        visible_texts = uia_data.get("visible_texts", [])
        ui_context = ""
        if visible_texts:
            sampled = [str(v) for v in visible_texts[:15] if str(v).strip()]
            if sampled:
                ui_context = f"\n[VISIBLE UI ELEMENTS]: {', '.join(sampled)}\n"

        context = (
            f"Time: {current_time}\n"
            f"Speaker: {speaker}\n"
            f"{memory_context}"
        )

        # ── PII redaction (privacy_mirror) ────────────────────────────────
        # Scrub the injected context (memory snippets, visible UI text, etc.)
        # before it ever leaves this machine. Respect the settings toggle.
        if self.settings.get("privacy_mirror_enabled", True):
            try:
                from privacy_mirror import redact_text
                context = redact_text(context)
            except Exception:
                pass
        
        # Stream response
        response_chunks = []
        token_buffer = []
        last_broadcast = time.time()
        
        if self.broadcast_callback:
            self.broadcast_callback("message", {
                "sender": "Primnox",
                "text": "",
                "speaker": "Primnox",
                "isTyping": True
            })
            
        full_text = ""
        try:
            for token in think_stream(raw_text, context=context, session_id=session_id):
                if not token:
                    continue

                if token.startswith("[API ERROR"):
                    log.error(f"LLM API Error intercepted: {token}")
                    if self.broadcast_callback:
                        self.broadcast_callback("message", {"sender": "Primnox", "text": "Sorry, something went wrong. Please try again."})
                    break

                # Strip [SYSTEM: ...] tool-execution notifications from the visible chat
                if "[SYSTEM:" in token:
                    # Broadcast as a subtle tool event instead of printing to chat
                    import re as _re
                    sys_match = _re.search(r'\[SYSTEM:\s*(.*?)\]', token)
                    if sys_match and self.broadcast_callback:
                        self.broadcast_callback("tool_executing", {"tool": sys_match.group(1).strip()})
                    continue

                response_chunks.append(token)
                token_buffer.append(token)
                full_text += token
                
                # Intercept [NAVIGATE:screen]
                if "[NAVIGATE:" in full_text and "]" in full_text:
                    import re
                    nav_match = re.search(r'\[NAVIGATE:(.*?)\]', full_text)
                    if nav_match:
                        screen = nav_match.group(1)
                        if self.broadcast_callback:
                            self.broadcast_callback("navigate", {"screen": screen})
                        full_text = full_text.replace(nav_match.group(0), "")
                        token_buffer.clear() # clear buffer to avoid sending it

                now = time.time()
                if now - last_broadcast > 0.1 or len(token_buffer) >= 5:
                    batched_text = "".join(token_buffer)
                    if "[NAVIGATE" not in batched_text: # Don't send partial navigate strings
                        if self.broadcast_callback:
                            self.broadcast_callback("token", {"text": batched_text})
                        token_buffer = []
                        last_broadcast = now
            
            if token_buffer:
                batched_text = "".join(token_buffer)
                if "[NAVIGATE" not in batched_text:
                    if self.broadcast_callback:
                        self.broadcast_callback("token", {"text": batched_text})
        except Exception as e:
            log.error(f"Stream exception: {e}")
            if self.broadcast_callback:
                self.broadcast_callback("message", {"sender": "Primnox", "text": "Sorry, something went wrong. Please try again."})
        
        response = full_text.strip()

        # Archive Primnox's response
        if not self.incognito and response:
            append_message_to_session(session_id, response, speaker="Primnox")

        if self.broadcast_callback:
            self.broadcast_callback("state", {"value": "idle"})

        # ── Post-exchange tasks (fire-and-forget background threads) ─────
        if not self.incognito and response and raw_text:
            threading.Thread(
                target=self._post_exchange_tasks,
                args=(raw_text, response, session_id),
                daemon=True,
                name="post-exchange"
            ).start()

    def _post_exchange_tasks(self, user_msg: str, ai_reply: str, session_id: str):
        """
        Runs after every chat exchange — never blocks the main stream.
        1. Extract and store a memory from the exchange if it's meaningful.
        2. Auto-title the session if it's still the default "New Chat".
        """
        exchange = f"User: {user_msg}\nPrimnox: {ai_reply}"

        # 1. Memory extraction from the conversation ─────────────────────
        try:
            resp = think(
                "Extract a single concise memory from this exchange that would be useful to remember "
                "for future conversations. Focus on facts about the user, their projects, preferences, "
                "or decisions made. If nothing worth remembering, reply with just: none\n\n" + exchange,
                system_override=(
                    "You extract memories. Output one short sentence (max 20 words) or the word 'none'. "
                    "No preamble, no quotes."
                )
            )
            mem_text = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if mem_text and mem_text.lower() not in ("none", "none.", "nothing"):
                add_memory(mem_text, category="session", session_id=session_id)
                if self.broadcast_callback:
                    self.broadcast_callback("memory_updated", {"text": mem_text})
                log.debug(f"Extracted memory: {mem_text[:60]}")
        except Exception as e:
            log.warning(f"Post-exchange memory extraction failed: {e}")

        # 2. Auto-title session if still default ─────────────────────────
        try:
            from chat_manager import get_session, update_session
            session = get_session(session_id)
            if session and session.get("title", "").strip() in ("New Chat", "current", ""):
                resp = think(
                    f"Give this conversation a short title (3-5 words, no quotes):\n{exchange[:300]}",
                    system_override="Output only the title. 3-5 words. No quotes. No punctuation at end."
                )
                title = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                title = title.strip('"\'').strip()
                if title and len(title) < 60:
                    update_session(session_id, title=title)
                    log.debug(f"Auto-titled session '{session_id}': {title}")
                    if self.broadcast_callback:
                        self.broadcast_callback("session_updated", {"id": session_id, "title": title})
        except Exception as e:
            log.warning(f"Auto-title failed: {e}")

    def route_by_trigger(self, text):
        if not text:
            return "DEFAULT"
        t = text.lower()
        if any(w in t for w in ["export notes", "export my notes", "export md", "export to markdown", "save notes to markdown"]):
            return "EXPORT_MD"
        if any(w in t for w in ["access data vault", "open data vault", "go to data vault", "show data vault", "data vault"]):
            return "DATA_VAULT"
        if any(w in t for w in ["open settings", "go to settings", "show settings", "island settings", "configure settings"]):
            return "SETTINGS"
        if any(w in t for w in ["open logs", "go to logs", "show logs", "system logs"]):
            return "LOGS"
        if any(w in t for w in ["open chat", "go to chat", "show chat", "synapse stream"]):
            return "CHAT"
        if any(w in t for w in ["open nodes", "go to nodes", "show nodes", "open notes", "go to notes", "neural nodes"]):
            return "NODES"
        if any(w in t for w in ["stop", "cancel", "abort", "pause", "halt"]):
            return "STOP"
        if any(w in t for w in ["forget", "delete memory", "remove memory"]):
            return "FORGET"
        if any(w in t for w in ["look", "see", "what's on screen", "what do you see", "check the screen", "read this", "what does it say", "what's open", "what am i looking at", "check this", "analyse screen", "analyze screen", "what's happening", "describe this", "whats on", "what can you see", "look at this", "screen", "scan", "observe", "visualize"]):
            return "VISION"
        if any(w in t for w in ["what do you remember", "show memory", "list memories"]):
            return "MEMORY"
        if any(w in t for w in ["meeting summary", "what was decided", "summarise call", "what did they say", "meeting notes"]):
            return "MEETING"
        if any(w in t for w in ["take ss", "take screenshot", "screenshot this", "capture screen"]):
            return "SCREENSHOT"
        if any(w in t for w in ["search", "google", "look up", "find on internet"]):
            return "SEARCH"
        if any(w in t for w in ["create pdf", "generate pdf", "make a pdf", "create a ppt", "make a presentation", "generate powerpoint"]):
            return "SKILL"
        return "DEFAULT"

    def handle_route(self, route, text, context, uia_data=None, vision_data=None, input_mode="text"):
        response = ""
        if route == "STOP":
            response = "stopped"
        elif route == "FORGET":
            # Extract the actual content to forget
            target = text.lower().replace("forget", "").replace("delete memory", "").replace("remove memory", "").strip()
            if target:
                delete_memory(target)
                response = f"forgotten: {target}"
            else:
                response = "forget what exactly?"
        elif route == "VISION":
            if vision_data and vision_data.get("description"):
                response = vision_data.get("description")
            else:
                res = describe_screen(uia_context=uia_data)
                response = res.get("description", "can't see.")
        elif route == "MEMORY":
            response = str(list_memories())
        elif route == "MEETING":
            response = "on it. summarizing the last call."
        elif route == "SCREENSHOT":
            res = route_skill(user_message="take ss")
            response = res.get("output_text", "ss failed")
        elif route == "SEARCH":
            search_query = text.lower().replace("search", "").replace("google", "").strip()
            search_results = web_search(search_query)
            
            # Feed search results back to brain for a natural response, with streaming
            from brain import think_stream
            import time
            response_chunks = []
            token_buffer = []
            last_broadcast = time.time()
            
            if self.broadcast_callback:
                self.broadcast_callback("message", {
                    "sender": "Primnox",
                    "text": "",
                    "speaker": "Primnox",
                    "route": route,
                    "isTyping": True
                })
                
            for token in think_stream(f"The user wants to know about '{search_query}'. Here are the results: {search_results}. Summarize them briefly."):
                response_chunks.append(token)
                token_buffer.append(token)
                now = time.time()
                if now - last_broadcast > 0.1 or len(token_buffer) >= 5:
                    batched_text = "".join(token_buffer)
                    if self.broadcast_callback:
                        self.broadcast_callback("token", {"text": batched_text})
                    token_buffer = []
                    last_broadcast = now
            
            if token_buffer:
                batched_text = "".join(token_buffer)
                if self.broadcast_callback:
                    self.broadcast_callback("token", {"text": batched_text})
            
            response = "".join(response_chunks)
        elif route == "SKILL":
            res = route_skill(user_message=text)
            response = res.get("output_text", "skill failed.")
        elif route == "EXPORT_MD":
            from notes_manager import get_notes
            import time
            from pathlib import Path
            notes = get_notes()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            export_path = Path.home() / "Documents" / "Primnox" / f"export_{timestamp}.md"
            export_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(export_path, "w", encoding="utf-8") as f:
                    f.write("# Primnox Notes Export\n\n")
                    for i, note in enumerate(notes):
                        if isinstance(note, dict):
                            f.write(f"## {note.get('title', f'Node {i}')}\n{note.get('text', '')}\n\n")
                        else:
                            f.write(f"## Node {i}\n{note}\n\n")
                if self.broadcast_callback:
                    self.broadcast_callback("file_attached", {"filename": f"export_{timestamp}.md"})
                response = f"i've exported your notes to Documents/Primnox/export_{timestamp}.md."
            except Exception as e:
                log.error(f"Failed to write export markdown file: {e}")
                response = "failed to export notes."
        elif route == "DATA_VAULT":
            if self.broadcast_callback:
                self.broadcast_callback("navigate", {"screen": "archive"})
            response = "opening data vault."
        elif route == "SETTINGS":
            if self.broadcast_callback:
                self.broadcast_callback("navigate", {"screen": "island_settings"})
            response = "opening system settings."
        elif route == "LOGS":
            if self.broadcast_callback:
                self.broadcast_callback("navigate", {"screen": "logs"})
            response = "opening system logs."
        elif route == "CHAT":
            if self.broadcast_callback:
                self.broadcast_callback("navigate", {"screen": "chat_expanded_sidebar"})
            response = "opening synapse stream chat."
        elif route == "NODES":
            if self.broadcast_callback:
                self.broadcast_callback("navigate", {"screen": "notes_icon_sidebar"})
            response = "opening notes workspace."
        else:
            from brain import think_stream
            import time
            response_chunks = []
            token_buffer = []
            last_broadcast = time.time()
            
            if self.broadcast_callback:
                self.broadcast_callback("message", {
                    "sender": "Primnox",
                    "text": "",
                    "speaker": "Primnox",
                    "route": route,
                    "isTyping": True
                })
                
            try:
                for token in think_stream(text, context):
                    if not token:
                        continue
                    
                    if token.startswith("[API ERROR"):
                        log.error(f"LLM API Error intercepted: {token}")
                        if self.broadcast_callback:
                            self.broadcast_callback("message", {"sender": "Primnox", "text": "Sorry, something went wrong. Please try again."})
                        break

                    response_chunks.append(token)
                    token_buffer.append(token)
                    now = time.time()
                    if now - last_broadcast > 0.1 or len(token_buffer) >= 5:
                        batched_text = "".join(token_buffer)
                        if self.broadcast_callback:
                            self.broadcast_callback("token", {"text": batched_text})
                        token_buffer = []
                        last_broadcast = now
                
                if token_buffer:
                    batched_text = "".join(token_buffer)
                    if self.broadcast_callback:
                        self.broadcast_callback("token", {"text": batched_text})
            except Exception as e:
                log.error(f"Stream exception: {e}")
                if self.broadcast_callback:
                    self.broadcast_callback("message", {"sender": "Primnox", "text": "Sorry, something went wrong. Please try again."})
            
            response = "".join(response_chunks)

        # PRIMNOX speaks her mind ONLY if the user spoke first
        if input_mode == "voice":
            speak(response)
        return response

    def toggle_mic(self):
        self.mic_muted = not self.mic_muted
        if hasattr(self, 'vad') and self.vad:
            self.vad.muted = self.mic_muted
        log.info(f"Microphone toggled. Muted: {self.mic_muted}")
        if self.broadcast_callback:
            self.broadcast_callback("mic_state", {"muted": self.mic_muted})
        return self.mic_muted

    def toggle_incognito(self):
        self.incognito = not self.incognito
        if hasattr(self, 'recorder') and self.recorder:
            self.recorder.incognito = self.incognito
        log.info(f"Incognito mode toggled. Active: {self.incognito}")
        if self.broadcast_callback:
            self.broadcast_callback("incognito_changed", {"active": self.incognito})
        return self.incognito

if __name__ == "__main__":
    core = PrimnoxCore()
    print("PrimnoxCore initialized.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        core.feed.stop()
        core.vad.stop()
        core.recorder.stop()
