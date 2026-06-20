# backend/sensor_vision.py
from PIL import ImageGrab, Image
import base64
import requests
import os
import hashlib
import io
from system_prompts import VISION_PROMPT
from logger import get_logger

log = get_logger("vision")

# Spatial Engine - lazy loaded on demand
spatial = None

# Optional dependency for active window cropping
try:
    import win32gui
    import win32ui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    log.warning("win32 libraries not found, active window cropping disabled.")

# Global state for debouncing
last_frame_hash = None
last_description = "no changes detected"

def get_api_key(provider):
    try:
        from settings_manager import load_settings
        settings = load_settings()
        key_name = f"{provider.lower()}_api_key"
        if settings.get(key_name):
            return settings[key_name]
    except Exception:
        pass
    
    if provider.lower() == "groq":
        return os.getenv("GROQ_API_KEY")
    elif provider.lower() == "openai":
        return os.getenv("OPENAI_API_KEY")
    elif provider.lower() == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    return None

def get_groq_api_key():
    return get_api_key("groq")

def get_active_window_rect():
    """Returns the (left, top, right, bottom) rect of the active window."""
    if not HAS_WIN32:
        return None
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            log.debug(f"Active window rect: {rect}")
            return rect
    except Exception as e:
        log.error(f"Failed to get active window rect: {e}")
    return None

def take_screenshot(crop_active=True, scale_to=1280):
    """
    Captures screen, optionally crops to active window, scales down,
    and returns PIL Image, b64 string and its SHA256 hash.
    """
    log.debug(f"Capturing screenshot (crop={crop_active}, scale={scale_to})...")
    try:
        img = ImageGrab.grab()
    except Exception as e:
        log.error(f"Screenshot capture failed: {e}")
        return None, "", ""

    # 1. Active Window Cropping
    if crop_active:
        rect = get_active_window_rect()
        if rect:
            l, t, r, b = rect
            w, h = img.size
            # Clamp to valid image bounds
            l = max(0, l)
            t = max(0, t)
            r = min(w, r)
            b = min(h, b)
            if r > l and b > t:
                img = img.crop((l, t, r, b))

    # 2. Resolution Scaling
    if scale_to:
        w, h = img.size
        if max(w, h) > scale_to:
            if w > h:
                new_w = scale_to
                new_h = int(h * (scale_to / w))
            else:
                new_h = scale_to
                new_w = int(w * (scale_to / h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            log.debug(f"Resized screenshot from {w}x{h} to {new_w}x{new_h}")

    # Convert to bytes for hashing and b64
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    b64 = base64.b64encode(raw_bytes).decode()
    img_hash = hashlib.sha256(raw_bytes).hexdigest()

    return img, b64, img_hash

def describe_screen(force=False, crop_active=True, uia_context=None):
    """
    Sovereign V2 Vision: Fuses UIA structural data + Vision pixels.
    Supports dynamic routing based on settings.
    """
    global last_frame_hash, last_description

    try:
        from settings_manager import load_settings
        settings = load_settings()
        active_model = settings.get("active_model", "Groq_Llama_3")
    except Exception:
        active_model = "Groq_Llama_3"

    # Get appropriate API key
    if active_model == "OpenAI_GPT_4o":
        api_key = get_api_key("openai")
        if not api_key:
            log.error("OpenAI API key missing!")
            return {"error": "OpenAI API key not set"}
    elif active_model == "Anthropic_Claude_3":
        api_key = get_api_key("anthropic")
        if not api_key:
            log.error("Anthropic API key missing!")
            return {"error": "Anthropic API key not set"}
    else: # Groq_Llama_3
        api_key = get_api_key("groq")
        if not api_key:
            log.error("Groq API key missing!")
            return {"error": "Groq API key not set"}

    pil_img, img_b64, current_hash = take_screenshot(crop_active=crop_active)

    # Frame Debouncing
    if not force and current_hash == last_frame_hash:
        log.info("Frame hash unchanged, using cached description.")
        return {"status": "unchanged", "description": last_description}

    log.info(f"Requesting vision analysis from {active_model}...")

    # UIA Fusion
    user_prompt = "What do you see on the screen?"
    hint_text = ""
    if uia_context:
        title = uia_context.get("window_title", "Unknown")
        focused = uia_context.get("focused_text", "")
        visible = ", ".join(uia_context.get("visible_texts", []))[:300]
        hint_text += f"\n\nUIA Structural Hint:\nActive Window: {title}\nFocused Element: {focused}\nVisible Elements: {visible}"

    try:
        if active_model == "OpenAI_GPT_4o":
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": VISION_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"{user_prompt}{hint_text}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                            ]
                        }
                    ]
                },
                timeout=30
            )
            result = resp.json()
            description = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        elif active_model == "Anthropic_Claude_3":
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1024,
                    "system": VISION_PROMPT,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": img_b64
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": f"{user_prompt}{hint_text}"
                                }
                            ]
                        }
                    ]
                },
                timeout=30
            )
            result = resp.json()
            description = result.get("content", [{}])[0].get("text", "")

        else: # Groq_Llama_3
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    "messages": [
                        {"role": "system", "content": VISION_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"{user_prompt}{hint_text}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                            ]
                        }
                    ]
                },
                timeout=30
            )
            result = resp.json()
            description = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        description = description or ""
        log.info(f"Vision result: {description[:100]}...")
        last_frame_hash = current_hash
        last_description = description
        return {"status": "updated", "description": description}

    except requests.exceptions.RequestException as e:
        log.warning(f"Vision failed (offline/network): {e}")
        # Offline Short-Circuit
        return {"status": "offline", "description": "offline. can't see screen."}
    except Exception as e:
        log.error(f"Vision crash: {e}", exc_info=True)
        return {"error": str(e)}

if __name__ == "__main__":
    print(describe_screen())
