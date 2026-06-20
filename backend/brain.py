# backend/brain.py
import requests
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from system_prompts import MASTER_PROMPT
from logger import get_logger
from tools import TOOL_DEFINITIONS, execute_tool

load_dotenv()

log = get_logger("brain")

GROQ_FALLBACK_CHAIN = [
    "llama-3.3-70b-versatile",                    # default — think_stream() starts here
    "openai/gpt-oss-120b",                         # fallback 1
    "qwen/qwen3-32b",                              # fallback 2
    "openai/gpt-oss-20b",                          # fallback 3
    "meta-llama/llama-4-scout-17b-16e-instruct",   # fallback 4
    "llama-3.1-8b-instant"                         # fallback 5 — last resort
]

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]

def get_adaptive_system_prompt(settings):
    """Injects user onboarding profile into the base persona."""
    base_prompt = MASTER_PROMPT
    if settings.get("onboarding_completed", False):
        profile = settings.get("onboarding_profile", {})
        comm_style = ", ".join(profile.get("communication_style", []))
        topics = ", ".join(profile.get("topics", []))
        
        if comm_style or topics:
            base_prompt += (
                f"\n\n[ADAPTIVE PROFILE INJECTION] "
                f"The user prefers this communication style: {comm_style}. "
                f"Blend this tone with your core directives. "
                f"The user's interests include: {topics}. "
                f"Keep these topics in mind when formulating responses."
            )
            
    current_mood = settings.get("current_mood")
    if current_mood:
        try:
            from system_prompts import EMOTION_PROMPTS
            mood_prompt = EMOTION_PROMPTS.get(current_mood)
            if mood_prompt:
                base_prompt += f"\n\n{mood_prompt}"
        except ImportError:
            pass
            
    return base_prompt

def get_api_key(provider):
    """Fetch API keys from settings first, then fall back to environment variables/keyring."""
    try:
        from settings_manager import load_settings
        settings = load_settings()
        key_name = f"{provider.lower()}_api_key"
        if settings.get(key_name):
            return settings[key_name]
    except Exception:
        pass

    # Keyring or Env fallbacks
    if provider.lower() == "groq":
        try:
            import keyring
            key = keyring.get_password("primnox", "groq_api_key")
            if key:
                return key
        except Exception:
            pass
        return os.getenv("GROQ_API_KEY")
    elif provider.lower() == "openai":
        return os.getenv("OPENAI_API_KEY")
    elif provider.lower() == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    elif provider.lower() == "gemini":
        try:
            import keyring
            key = keyring.get_password("primnox", "gemini_api_key")
            if key:
                return key
        except Exception:
            pass
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return None

def get_groq_api_key():
    return get_api_key("groq")

def get_ollama_status(base_url: str = "http://localhost:11434") -> dict:
    """Returns {'running': bool, 'models': [str, ...]}"""
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return {"running": True, "models": models}
        return {"running": False, "models": []}
    except Exception:
        return {"running": False, "models": []}

def transcribe(audio_bytes):
    log.info("Requesting transcription from Groq Whisper...")
    api_key = get_groq_api_key()
    if not api_key:
        log.error("Groq API key missing!")
        return {"error": "Groq API key not set"}
    try:
        # Multilingual Prompt: Optimized for English, Hindi, and Telugu
        prompt = "Listen for English, Hindi, and Telugu. Keep transcriptions faithful to the spoken language."
        
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            data={"prompt": prompt, "model": "whisper-large-v3-turbo"},
            timeout=15
        )
        res = resp.json()
        log.debug(f"Transcription result: {res.get('text', 'NO TEXT')[:50]}...")
        return res
    except requests.exceptions.RequestException as e:
        log.warning(f"Transcription failed (offline/network): {e}")
        # Offline Short-Circuit
        return {"error": "offline", "text": "[System: Offline - Transcription Failed]"}
    except Exception as e:
        log.error(f"Transcription crash: {e}", exc_info=True)
        return {"error": str(e)}

def think(prompt, context=None, image_base64=None, messages=None, system_override=None):
    """
    Primnox Thinking Engine (Dynamic Routing)
    Supports Groq, OpenAI, and Anthropic.
    Locks the default MASTER_PROMPT system persona.
    """
    log.info(f"Thinking about: {prompt[:50]}...")
    
    # Load settings to check active model
    try:
        from settings_manager import load_settings
        settings = load_settings()
        active_model = settings.get("active_model", "Groq_Llama_3")
    except Exception:
        active_model = "Groq_Llama_3"
        settings = {}

    system_content = system_override if system_override else get_adaptive_system_prompt(settings)

    import re
    # Check for context references
    refs = re.findall(r'#([a-fA-F0-9]{6})', prompt)
    if refs:
        try:
            from chat_manager import get_sessions, get_session_messages
            sessions = get_sessions()
            for ref in refs:
                matching = [s for s in sessions if s["id"].startswith(ref)]
                if matching:
                    ref_hist = get_session_messages(matching[0]["id"])[-20:]
                    ref_text_parts = []
                    for msg in ref_hist:
                        txt = msg['text']
                        if len(txt) > 500: txt = txt[:500] + "...[truncated]"
                        ref_text_parts.append(f"{msg['speaker']}: {txt}")
                    ref_text = "\n".join(ref_text_parts)
                    system_content += f"\n\n[REFERENCED CONTEXT FROM CHAT #{ref}]:\n{ref_text}"
        except Exception as e:
            log.error(f"Failed to load referenced chat context: {e}")

    text_content = f"Context:\n{context}\n\nUser: {prompt}" if context else prompt
    user_content = text_content

    # Vision payload builders
    def build_openai_vision(text, img_b64):
        return [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
        ]
        
    def build_anthropic_vision(text, img_b64):
        return [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
            {"type": "text", "text": text}
        ]

    try:
        if active_model == "OpenAI_GPT_4o":
            api_key = get_api_key("openai")
            if not api_key:
                log.error("OpenAI API key missing!")
                return {"error": "OpenAI API key not set"}
                
            msg_content = build_openai_vision(text_content, image_base64) if image_base64 else text_content
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": msg_content}
                    ]
                },
                timeout=20
            )
            res = resp.json()
            return res

        elif active_model == "Anthropic_Claude_3":
            api_key = get_api_key("anthropic")
            if not api_key:
                log.error("Anthropic API key missing!")
                return {"error": "Anthropic API key not set"}
                
            msg_content = build_anthropic_vision(text_content, image_base64) if image_base64 else text_content
            # Use caller-provided message history when available (strips system role as
            # Anthropic requires it in the separate "system" field). Falls back to
            # single-message for internal/skill calls that don't pass history.
            if messages:
                anthropic_messages = [m for m in messages if m["role"] != "system"]
                if not anthropic_messages:
                    # All entries were system-role; fall back to single user message
                    anthropic_messages = [{"role": "user", "content": msg_content}]
            else:
                anthropic_messages = [{"role": "user", "content": msg_content}]
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
                    "system": system_content,
                    "messages": anthropic_messages
                },
                timeout=20
            )
            res = resp.json()
            # Map Anthropic response structure to OpenAI compatibility
            content = res.get("content", [{}])[0].get("text", "")
            mapped_res = {
                "choices": [{
                    "message": {
                        "content": content
                    }
                }]
            }
            return mapped_res

        elif active_model == "Ollama_Local":
            ollama_url = settings.get("ollama_base_url", "http://localhost:11434").rstrip("/")
            ollama_model = settings.get("ollama_model", "llama3.2")
            log.info(f"Routing think() → Ollama ({ollama_model} @ {ollama_url})")
            try:
                resp = requests.post(
                    f"{ollama_url}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": ollama_model,
                        "messages": [
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": user_content}
                        ],
                        "stream": False
                    },
                    timeout=120   # local models can be slow
                )
                res = resp.json()
                return res
            except requests.exceptions.Timeout:
                log.error("Ollama timed out — model may be loading. Try again shortly.")
                return {"choices": [{"message": {"content": "ollama timed out — the model might still be loading. try again in a few seconds."}}]}
            except requests.exceptions.ConnectionError:
                log.error("Ollama not reachable — is it running? (ollama serve)")
                return {"choices": [{"message": {"content": "ollama isn't running bro. start it with `ollama serve`."}}]}

        elif active_model == "Gemini_Flash":
            api_key = get_api_key("gemini")
            if not api_key:
                log.error("Gemini API key missing!")
                return {"choices": [{"message": {"content": "Gemini API key not set. Add it in Settings or set GEMINI_API_KEY env var."}}]}
            gemini_model = settings.get("gemini_model", "gemini-2.0-flash")
            log.info(f"Routing think() → Gemini ({gemini_model})")
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": gemini_model,
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_content}
                    ]
                },
                timeout=30
            )
            try:
                res = resp.json()
            except Exception:
                return {"choices": [{"message": {"content": f"Gemini returned non-JSON (HTTP {resp.status_code})"}}]}
            if "error" in res:
                log.warning(f"Gemini error: {res['error']}")
            return res

        else: # Default/Groq_Llama_3
            api_key = get_api_key("groq")
            if not api_key:
                log.error("Groq API key missing!")
                return {
                    "error": "Groq API key not set",
                    "choices": [{
                        "message": {
                            "content": "Sorry, cannot process this request without AI. Please add your Groq API key in Settings."
                        }
                    }]
                }

            msg_content = build_openai_vision(text_content, image_base64) if image_base64 else text_content
            
            if image_base64:
                models_to_try = ["llama-3.2-11b-vision-preview"]
            else:
                models_to_try = GROQ_FALLBACK_CHAIN
                
            last_res = {
                "error": "all_models_failed",
                "choices": [{"message": {"content": "all AI models unavailable right now — please try again in a moment."}}]
            }
            for groq_model in models_to_try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": groq_model,
                        "messages": [
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": msg_content}
                        ]
                    },
                    timeout=20
                )
                # Guard against non-JSON bodies (e.g. Cloudflare HTML 502) before
                # calling resp.json() — a JSONDecodeError would escape the
                # requests.exceptions handler below and surface as a bare Exception.
                try:
                    res = resp.json()
                except Exception:
                    log.warning(f"Groq model {groq_model} returned non-JSON (HTTP {resp.status_code}) — trying next")
                    continue
                last_res = res
                if "error" not in res:
                    return res
                # if there is an error, we can try the next model
                log.warning(f"Groq model {groq_model} failed: {res.get('error')}")

            # ── Gemini automatic fallback when all Groq models fail ──────
            gemini_key = get_api_key("gemini")
            if gemini_key:
                for gm in GEMINI_MODELS:
                    log.info(f"All Groq models failed. Trying Gemini fallback: {gm}")
                    try:
                        resp = requests.post(
                            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                            headers={"Authorization": f"Bearer {gemini_key}", "Content-Type": "application/json"},
                            json={
                                "model": gm,
                                "messages": [
                                    {"role": "system", "content": system_content},
                                    {"role": "user", "content": msg_content}
                                ]
                            },
                            timeout=30
                        )
                        res = resp.json()
                        if "error" not in res:
                            return res
                        log.warning(f"Gemini model {gm} failed: {res.get('error')}")
                    except Exception as e:
                        log.warning(f"Gemini fallback {gm} exception: {e}")

            return last_res
    except requests.exceptions.RequestException as e:
        log.warning(f"Thinking failed (offline/network): {e}")
        # Offline Short-Circuit
        return {
            "error": "offline",
            "choices": [{
                "message": {
                    "content": "offline. can't think. check your net."
                }
            }]
        }
    except Exception as e:
        log.error(f"Thinking crash: {e}", exc_info=True)
        return {"error": str(e)}


def think_stream(prompt, context="", session_id="", images_b64=None):
    try:
        from settings_manager import load_settings
        settings = load_settings()
        active_model = settings.get("active_model", "Groq_Llama_3")
    except Exception:
        active_model = "Groq_Llama_3"
        settings = {}
        
    system_content = get_adaptive_system_prompt(settings)

    import re
    # Check for context references
    refs = re.findall(r'#([a-fA-F0-9]{6})', prompt)
    if refs:
        try:
            from chat_manager import get_sessions, get_session_messages
            sessions = get_sessions()
            for ref in refs:
                matching = [s for s in sessions if s["id"].startswith(ref)]
                if matching:
                    ref_hist = get_session_messages(matching[0]["id"])[-20:]
                    ref_text_parts = []
                    for msg in ref_hist:
                        txt = msg['text']
                        if len(txt) > 500: txt = txt[:500] + "...[truncated]"
                        ref_text_parts.append(f"{msg['speaker']}: {txt}")
                    ref_text = "\n".join(ref_text_parts)
                    system_content += f"\n\n[REFERENCED CONTEXT FROM CHAT #{ref}]:\n{ref_text}"
        except Exception as e:
            log.error(f"Failed to load referenced chat context: {e}")
            
    messages = [
        {"role": "system", "content": system_content}
    ]

    if session_id:
        try:
            from chat_manager import get_session_messages
            history = get_session_messages(session_id)[-20:] # Limit to 20 to prevent Groq crash
            for i, msg in enumerate(history):
                # Skip if it's the exact same prompt at the end (just added by core.py)
                if i == len(history) - 1 and msg["text"] == prompt and msg["speaker"] != "Primnox":
                    continue
                role = "assistant" if msg["speaker"] == "Primnox" else "user"
                msg_text = msg["text"]
                if len(msg_text) > 1000:
                    msg_text = msg_text[:1000] + "\n...[truncated for length]"
                messages.append({"role": role, "content": msg_text})
        except Exception as e:
            log.error(f"Failed to load chat history: {e}")

    user_content = f"Context:\n{context}\n\nUser: {prompt}" if context else prompt
    if images_b64:
        if active_model == "Anthropic_Claude_3":
            content_arr = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}} for b64 in images_b64]
            content_arr.append({"type": "text", "text": user_content})
            user_content = content_arr
        else:
            # Gemini's OpenAI-compat endpoint and vision-capable Ollama models
            # (llava, llama3.2-vision, etc) both accept the same OpenAI-style
            # image_url/base64 content blocks — previously these were silently
            # dropped for Ollama/Gemini, leaving images unused with no warning.
            content_arr = [{"type": "text", "text": user_content}]
            content_arr.extend([{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}} for b64 in images_b64])
            user_content = content_arr

    messages.append({"role": "user", "content": user_content})

    api_key = ""
    url = ""
    model_name = ""
    headers = {}
    is_ollama = False
    is_gemini = False

    if active_model == "OpenAI_GPT_4o":
        api_key = get_api_key("openai")
        url = "https://api.openai.com/v1/chat/completions"
        model_name = "gpt-4o"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif active_model == "Anthropic_Claude_3":
        api_key = get_api_key("anthropic")
        url = "https://api.anthropic.com/v1/messages"
        model_name = "claude-3-5-sonnet-20241022"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    elif active_model == "Ollama_Local":
        ollama_url = settings.get("ollama_base_url", "http://localhost:11434").rstrip("/")
        if images_b64:
            vision_model = settings.get("ollama_vision_model", "")
            if not vision_model:
                yield ("Local vision needs a vision-capable Ollama model "
                       "(e.g. `ollama pull llava` or `llama3.2-vision`), "
                       "then set it as 'ollama_vision_model' in Settings.")
                return
            model_name = vision_model
        else:
            model_name = settings.get("ollama_model", "llama3.2")
        url = f"{ollama_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = "ollama"   # sentinel — Ollama needs no real key
        is_ollama = True
        log.info(f"Routing think_stream() → Ollama ({model_name} @ {ollama_url})")
    elif active_model == "Gemini_Flash":
        api_key = get_api_key("gemini")
        gemini_model = settings.get("gemini_model", "gemini-2.0-flash")
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        model_name = gemini_model
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        is_gemini = True
        log.info(f"Routing think_stream() → Gemini ({model_name})")
    else:
        api_key = get_api_key("groq")
        url = "https://api.groq.com/openai/v1/chat/completions"
        model_name = "llama-3.2-11b-vision-preview" if images_b64 else "llama-3.3-70b-versatile"
        headers = {"Authorization": f"Bearer {api_key}"}

    if not api_key:
        yield "Sorry, cannot process this request without AI. Please add your API key in Settings."
        return

    # ── Ollama fast-path: no tool-calling loop, direct streaming ─────────────
    if is_ollama:
        try:
            resp_stream = requests.post(
                url, headers=headers,
                json={"model": model_name, "messages": messages, "stream": True},
                stream=True, timeout=120
            )
            if resp_stream.status_code != 200:
                yield f"[Ollama error {resp_stream.status_code}]: {resp_stream.text}"
                return
            for line in resp_stream.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if token:
                                yield token
                        except Exception:
                            pass
        except requests.exceptions.Timeout:
            yield "ollama timed out — the model might still be loading. try again in a few seconds."
        except requests.exceptions.ConnectionError:
            yield "ollama isn't running bro. start it with `ollama serve`."
        return

    # ── Gemini fast-path: direct streaming, no tool-calling loop ─────────────
    if is_gemini:
        try:
            resp_stream = requests.post(
                url, headers=headers,
                json={"model": model_name, "messages": messages, "stream": True},
                stream=True, timeout=60
            )
            if resp_stream.status_code != 200:
                yield f"[Gemini error {resp_stream.status_code}]: {resp_stream.text[:200]}"
                return
            for line in resp_stream.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if token:
                                yield token
                        except Exception:
                            pass
        except Exception as e:
            yield f"gemini error: {e}"
        return

    try:
        if active_model not in ("Anthropic_Claude_3", "Gemini_Flash"):
            max_steps = 5
            for step in range(max_steps):
                for _retry in range(3):
                    resp = requests.post(
                        url,
                        headers=headers,
                        json={
                            "model": model_name,
                            "messages": messages,
                            "tools": TOOL_DEFINITIONS,
                            "tool_choice": "auto"
                        },
                        timeout=60
                    )
                    if resp.status_code == 429:
                        if "groq.com" in url and model_name in GROQ_FALLBACK_CHAIN:
                            current_idx = GROQ_FALLBACK_CHAIN.index(model_name)
                            if current_idx + 1 < len(GROQ_FALLBACK_CHAIN):
                                next_model = GROQ_FALLBACK_CHAIN[current_idx + 1]
                                log.warning(f"Rate limit hit. Falling back to {next_model}...")
                                model_name = next_model
                                continue
                            else:
                                # All Groq models exhausted — try Gemini
                                gemini_key = get_api_key("gemini")
                                if gemini_key:
                                    log.warning("All Groq models rate-limited. Falling back to Gemini...")
                                    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                                    model_name = "gemini-2.0-flash"
                                    headers = {"Authorization": f"Bearer {gemini_key}", "Content-Type": "application/json"}
                                    continue
                        log.warning("Rate limit hit. Retrying in 2 seconds...")
                        import time
                        time.sleep(2)
                        continue
                    break
                
                res_data = None
                if resp.status_code != 200:
                    if "tool_use_failed" in resp.text:
                        try:
                            err_data = resp.json()
                            failed_gen = err_data.get("error", {}).get("failed_generation", "")
                            if failed_gen.startswith("<function="):
                                func_part = failed_gen[10:].split("</function>")[0]
                                brace_idx = func_part.find("{")
                                if brace_idx != -1:
                                    func_name = func_part[:brace_idx].strip('=>"\' ')
                                    func_args_str = func_part[brace_idx:]
                                    tool_call = {
                                        "id": "call_simulated",
                                        "type": "function",
                                        "function": {
                                            "name": func_name,
                                            "arguments": func_args_str
                                        }
                                    }
                                    response_msg = {
                                        "role": "assistant",
                                        "content": None,
                                        "tool_calls": [tool_call]
                                    }
                                    res_data = {"choices": [{"message": response_msg}]}
                                    log.warning(f"Groq tool parsed manually: {func_name}")
                        except Exception:
                            pass
                            
                        if not res_data:
                            log.warning("Groq tool parsing failed entirely. Retrying without tools.")
                            for _retry in range(3):
                                resp = requests.post(
                                    url, headers=headers,
                                    json={"model": model_name, "messages": messages}, timeout=60
                                )
                                if resp.status_code == 429:
                                    if "groq.com" in url and model_name in GROQ_FALLBACK_CHAIN:
                                        current_idx = GROQ_FALLBACK_CHAIN.index(model_name)
                                        if current_idx + 1 < len(GROQ_FALLBACK_CHAIN):
                                            next_model = GROQ_FALLBACK_CHAIN[current_idx + 1]
                                            log.warning(f"Rate limit hit. Falling back to {next_model}...")
                                            model_name = next_model
                                            continue
                                    log.warning("Rate limit hit. Retrying in 2 seconds...")
                                    import time
                                    time.sleep(2)
                                    continue
                                break
                            if resp.status_code != 200:
                                yield f"[API ERROR {resp.status_code}]: {resp.text}"
                                return
                            res_data = resp.json()
                    else:
                        yield f"[API ERROR {resp.status_code}]: {resp.text}"
                        return
                else:
                    res_data = resp.json()
                    
                response_msg = res_data.get("choices", [{}])[0].get("message", {})
                
                tool_calls = response_msg.get("tool_calls")
                if tool_calls:
                    log.info(f"LLM decided to use {len(tool_calls)} tools (Step {step+1}).")
                    messages.append(response_msg)
                    
                    for tool_call in tool_calls:
                        func_name = tool_call.get("function", {}).get("name")
                        try:
                            args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                        except Exception:
                            args = {}
                            
                        log.info(f"Executing tool {func_name}...")
                        yield f"\n[SYSTEM: Executing {func_name}]\n"
                        result = execute_tool(func_name, args, session_id=session_id)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "name": func_name,
                            "content": str(result)
                        })
                    
                    # If we reached max steps, break to force final response
                    if step == max_steps - 1:
                        log.warning("Max steps reached, forcing final response.")
                        break
                else:
                    # No tools called. Stream the text response directly
                    content = response_msg.get("content", "")
                    for word in content.split(" "):
                        yield word + " "
                    return
                    
            # Force a final streaming pass if we hit max_steps or broke out needing a final pass
            for _retry in range(3):
                resp_stream = requests.post(
                    url,
                    headers=headers,
                    json={
                        "model": model_name,
                        "messages": messages,
                        "stream": True
                    },
                    stream=True,
                    timeout=60
                )
                if resp_stream.status_code == 429:
                    if "groq.com" in url and model_name in GROQ_FALLBACK_CHAIN:
                        current_idx = GROQ_FALLBACK_CHAIN.index(model_name)
                        if current_idx + 1 < len(GROQ_FALLBACK_CHAIN):
                            next_model = GROQ_FALLBACK_CHAIN[current_idx + 1]
                            log.warning(f"Rate limit hit on streaming. Falling back to {next_model}...")
                            model_name = next_model
                            continue
                    log.warning("Rate limit hit on streaming. Retrying in 2 seconds...")
                    import time
                    time.sleep(2)
                    continue
                break
            
            if resp_stream.status_code != 200:
                yield f"[Error {resp_stream.status_code}]: rate limit or server error — try again in a moment."
                return
            for line in resp_stream.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if token:
                                yield token
                        except Exception:
                            pass

        else:
            # Anthropic streaming — pass full conversation history.
            # Anthropic requires system prompt in its own "system" field,
            # and messages must only contain role=user/assistant (no system).
            anthropic_messages = [m for m in messages if m["role"] != "system"]
            resp = requests.post(
                url,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": anthropic_messages,
                    "system": system_content,
                    "stream": True,
                    "max_tokens": 1024
                },
                stream=True,
                timeout=60
            )
            if resp.status_code != 200:
                yield f"[Anthropic error {resp.status_code}]: {resp.text[:200]}"
                return
            for line in resp.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        try:
                            chunk = json.loads(data_str)
                            if chunk.get("type") == "content_block_delta":
                                token = chunk.get("delta", {}).get("text", "")
                                if token:
                                    yield token
                        except Exception:
                            pass

    except Exception as e:
        log.error(f"Streaming thinking crash: {e}", exc_info=True)
        yield f"error thinking: {e}"

if __name__ == "__main__":
    print("Testing think:")
    print(think("status update"))
    print("\nTesting think_stream:")
    for token in think_stream("status update"):
        print(token, end="", flush=True)
    print()

