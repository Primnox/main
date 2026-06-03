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

        log.info("Starting FeedManager...")
        self.feed = FeedManager(callback=self.on_feed_update)
        self.feed.start()

        # log.info("Starting VADListener...")
        # self.vad = VADListener(
        #     callback=self.on_speech, 
        #     ambient_callback=self.feed.log_ambient,
        #     state_callback=self.on_vad_state_change
        # )
        # self.vad.start()
        self.vad = None # Disabled per user request

        log.info("Starting MeetingRecorder...")
        self.recorder = MeetingRecorder()
        self.recorder.start()

        self.proactive = ProactiveEngine()
        
        # Register voice state callback
        # import voice
        # voice.register_state_callback(self.on_voice_state_change)
        
        log.info("PrimnoxCore initialization complete.")

    def register_broadcast_callback(self, cb):
        log.debug("Registering broadcast callback.")
        self.broadcast_callback = cb

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

    def handle_text_input(self, text: str, session_id="current"):
        log.info(f"Handling text input: {text[:50]}...")
        if not self.incognito:
            append_message_to_session(session_id, text, speaker="User")
        
        if self.broadcast_callback:
            self.broadcast_callback("message", {
                "sender": "User",
                "text": text,
                "speaker": "User"
            })
            
        self._process_input(text, "User", input_mode="text", session_id=session_id)


    def _process_input(self, raw_text, speaker, input_mode="text", session_id="current"):
        """Unified Processing Logic for Voice and Text (Agentic)."""
        if not raw_text:
            log.debug("Empty input, skipping.")
            return

        if self.broadcast_callback:
            self.broadcast_callback("state", {"value": "thinking"})

        if not self.incognito:
            append_message_to_session(session_id, raw_text, speaker=speaker)

        log.info(f"Agentic processing input '{raw_text[:30]}'")

        # Sensor Fusion: Gather UIA and basic context (no massive auto-injection of all memory)
        log.debug("Gathering screen state (UIA)...")
        uia_data = self.latest_uia_data or {"window_title": "Unknown", "focused_text": "", "visible_texts": [], "errors": []}
        
        # Build Context for Primnox (lightweight)
        log.debug("Building lightweight context...")
        current_time = time.strftime('%I:%M %p')
        context = f"Time: {current_time}\nSpeaker: {speaker}\nActive OS Window: {uia_data.get('window_title')}\n"
        
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
            
        # Voice TTS (if active)
        # if not self.incognito and response:
        #     from settings_manager import load_settings
        #     s = load_settings()
        #     if s.get("voice_feedback", True):
        #         speak(response)

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
