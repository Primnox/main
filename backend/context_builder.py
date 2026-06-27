# backend/context_builder.py
from datetime import datetime
from logger import get_logger

log = get_logger("context")

# NOTE: PII scrubbing is no longer done here. It happens at the cloud boundary in
# brain.think_stream (reversible pseudonymization, gated on local vs cloud route),
# so context is kept raw on-device and only scrubbed if/when it actually leaves.

def build_context(screen_data, vision_data, memory_data, conversation_history, user_message, speaker):
    log.debug("Building context for LLM...")
    
    # Safely handle screen_data (may be dict or string)
    if isinstance(screen_data, dict):
        active_window = screen_data.get("window_title", "Unknown")
        screen_errors = screen_data.get("errors", [])
        visible_elements = screen_data.get("visible_texts", [])
    else:
        active_window = str(screen_data)
        screen_errors = []
        visible_elements = []
    
    # Safely handle vision_data
    if isinstance(vision_data, dict):
        vision_desc = vision_data.get("description", "No vision data available.")
    else:
        vision_desc = str(vision_data) if vision_data else "No vision data available."
    
    # Safely handle conversation_history
    if isinstance(conversation_history, list):
        conv_text = "\n".join(str(m) for m in conversation_history[-10:])
    else:
        conv_text = str(conversation_history) if conversation_history else ""
    
    context = f"""[SYSTEM TIME]: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
[SPEAKER]: {speaker}

[CURRENT SCREEN STATE]:
Active Window: {active_window}
Detected Errors/Warnings: {", ".join(screen_errors) if screen_errors else "None detected."}
Visible Elements (Sample): {", ".join(str(v) for v in visible_elements[:20])}

[VISUAL ANALYSIS]:
{vision_desc}

[LONG-TERM MEMORY]:
{memory_data}

[CONVERSATION HISTORY]:
{conv_text}

[USER INPUT]:
{user_message}
"""
    log.debug(f"Context built successfully ({len(context)} characters)")
    return context

if __name__ == "__main__":
    print(build_context(
        {"window_title": "Test", "errors": [], "visible_texts": ["hello"]},
        {"description": "A test screen."},
        "User likes Python.",
        ["User: hello", "Primnox: hi there"],
        "hello",
        "User"
    ))
