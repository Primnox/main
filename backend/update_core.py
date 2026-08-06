import re
from pathlib import Path

# Resolve paths relative to this file. These were absolute paths on the
# original author's Windows machine, which leaked a username and broke the
# script for everyone else.
_BACKEND_DIR = Path(__file__).resolve().parent

new_process_input = """
    def _process_input(self, raw_text, speaker, input_mode="text", session_id="current"):
        \"\"\"Unified Processing Logic for Voice and Text (Agentic).\"\"\"
        if not raw_text:
            log.debug("Empty input, skipping.")
            return

        if self.broadcast_callback:
            self.broadcast_callback("state", {"value": "thinking"})

        if input_mode == "voice" and not self.incognito:
            append_message_to_session(session_id, raw_text, speaker=speaker)

        log.info(f"Agentic processing input '{raw_text[:30]}'")

        # Sensor Fusion: Gather UIA and basic context (no massive auto-injection of all memory)
        log.debug("Gathering screen state (UIA)...")
        uia_data = self.latest_uia_data or {"window_title": "Unknown", "focused_text": "", "visible_texts": [], "errors": []}
        
        # Build Context for Primnox (lightweight)
        log.debug("Building lightweight context...")
        import time
        current_time = time.strftime('%I:%M %p')
        context = f"Time: {current_time}\\nSpeaker: {speaker}\\nActive OS Window: {uia_data.get('window_title')}\\n"
        
        # Stream response
        import time
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
        for token in think_stream(raw_text, context=context):
            response_chunks.append(token)
            token_buffer.append(token)
            full_text += token
            
            # Intercept [NAVIGATE:screen]
            if "[NAVIGATE:" in full_text and "]" in full_text:
                import re
                nav_match = re.search(r'\\[NAVIGATE:(.*?)\\]', full_text)
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
        
        response = full_text.strip()
        
        # Archive Primnox's response
        if not self.incognito and response:
            append_message_to_session(session_id, response, speaker="Primnox")
            
        if self.broadcast_callback:
            self.broadcast_callback("state", {"value": "idle"})
            
        # Voice TTS (if active)
        if not self.incognito and response:
            from settings_manager import load_settings
            s = load_settings()
            if s.get("voice_feedback", True):
                speak(response)

"""

with open(str(_BACKEND_DIR / "core.py"), 'r', encoding='utf-8') as f:
    content = f.read()

# Replace _process_input entirely. We also need to strip out route_by_trigger and handle_route as they are obsolete, but it's safer to just replace _process_input.
content = re.sub(r'    def _process_input\(self, raw_text, speaker, input_mode="text", session_id="current"\):.*?(?=    def route_by_trigger)', new_process_input, content, flags=re.DOTALL)

with open(str(_BACKEND_DIR / "core.py"), 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated core.py.')
