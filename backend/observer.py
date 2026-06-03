# backend/observer.py
import asyncio
import pyperclip
import re
from logger import get_logger

log = get_logger("observer")

# Global callback register
broadcast_callback = None

def register_observer_callback(cb):
    global broadcast_callback
    broadcast_callback = cb

async def start_clipboard_monitor():
    log.info("Starting clipboard monitor...")
    last_clipboard = ""
    # Better pattern: detect API keys (16+ alphanumeric chars) and 2FA codes (6 digits with word boundaries)
    key_pattern = re.compile(r'(?:key|secret|token|password|api)[=:"\s]+([A-Za-z0-9_\-]{16,})', re.IGNORECASE)
    twofa_pattern = re.compile(r'(?:^|\s)(\d{6})(?:\s|$)')
    
    while True:
        try:
            current_clipboard = pyperclip.paste()
            if current_clipboard and current_clipboard != last_clipboard:
                last_clipboard = current_clipboard
                is_sensitive = key_pattern.search(current_clipboard) or twofa_pattern.search(current_clipboard)
                if is_sensitive:
                    log.warning("Sensitive data detected on clipboard! Notifying frontend.")
                    # Send a flag only — never send the raw sensitive data to the frontend
                    if broadcast_callback:
                        try:
                            broadcast_callback("clipboard_sensitive", {"detected": True})
                        except Exception as e:
                            log.warning(f"Failed to broadcast clipboard alert: {e}")
        except Exception as e:
            log.debug(f"Clipboard polling error: {e}")
        await asyncio.sleep(1.0)

def clear_clipboard_data():
    log.info("Sanitizing clipboard data...")
    try:
        pyperclip.copy('')
    except Exception as e:
        log.error(f"Failed to clear clipboard: {e}")
