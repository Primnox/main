# backend/brain.py
import requests
import os
import json
import threading
from pathlib import Path
from dotenv import load_dotenv
from system_prompts import MASTER_PROMPT
from logger import get_logger
from tools import TOOL_DEFINITIONS, execute_tool

load_dotenv()

log = get_logger("brain")

GROQ_FALLBACK_CHAIN = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "mistralai/mistral-saba-24b",
    "llama-3.3-70b-versatile",
]

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]

# Global Load Balancer State for Groq
_groq_lb_lock = threading.Lock()
_groq_lb_state = {
    "current_idx": 0,
}

def rotate_groq_model():
    """Advances the global Groq model index to load balance (thread-safe)."""
    with _groq_lb_lock:
        _groq_lb_state["current_idx"] = (_groq_lb_state["current_idx"] + 1) % len(GROQ_FALLBACK_CHAIN)
        model = GROQ_FALLBACK_CHAIN[_groq_lb_state["current_idx"]]
    log.info(f"[LB] Rotated Groq model to {model}")
    return model

def _gemini_fallback_target():
    """url / model / headers to retry on Gemini's OpenAI-compatible endpoint once
    every Groq model is rate-limited. Returns None when no Gemini key is configured."""
    gkey = get_api_key("gemini")
    if not gkey:
        return None
    return (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "gemini-2.0-flash",
        {"Authorization": f"Bearer {gkey}", "Content-Type": "application/json"},
    )

def get_adaptive_system_prompt(settings):
    """Injects user onboarding profile into the base persona."""
    base_prompt = MASTER_PROMPT

    # Always inject the user's name so the AI can address them properly
    user_name = settings.get("operator_alias") or settings.get("nickname") or ""
    if user_name:
        base_prompt += f"\n\n[USER IDENTITY] The user's name is {user_name}. Use it naturally in conversation — not every message, just when it feels right."

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
    elif provider.lower() == "llamacpp":
        return "llamacpp"  # llama.cpp server needs no API key
    return None

def get_groq_api_key():
    return get_api_key("groq")

def _safe_local_url(url: str, default_port: int) -> str:
    """Validate that a local model URL is a well-formed localhost/127.0.0.1 HTTP URL.
    Rejects anything that could cause SSRF-style requests to external hosts."""
    import re
    url = url.strip().rstrip("/")
    if re.match(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$', url):
        return url
    log.warning(f"Rejected unsafe local model URL '{url}' — falling back to localhost:{default_port}")
    return f"http://localhost:{default_port}"

def _safe_int_header(val, default: int) -> int:
    """Parse an HTTP header value as int without crashing on non-integer strings."""
    try:
        return int(float(val))
    except Exception:
        return default

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

def transcribe(audio_bytes, timeout=15):
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
            timeout=timeout
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
    """Non-streaming thinking entry. Wraps the model call with the Privacy Mirror
    cloud-boundary gate: cloud routes get a pseudonymized payload and the returned
    content is de-anonymized before callers (memory extraction, profiler, etc.)
    ever see it; local routes are untouched."""
    box: dict = {}
    res = _think_inner(prompt, context=context, image_base64=image_base64,
                       messages=messages, system_override=system_override, _scrub_box=box)
    sess = box.get("sess")
    if sess is not None:
        try:
            msg = res["choices"][0]["message"]
            if isinstance(msg.get("content"), str):
                msg["content"] = sess.rehydrate(msg["content"])
        except Exception:
            pass
    return res


def _think_inner(prompt, context=None, image_base64=None, messages=None, system_override=None, _scrub_box=None):
    """
    Primnox Thinking Engine (Dynamic Routing)
    Supports Groq, OpenAI, and Anthropic.
    Locks the default MASTER_PROMPT system persona.
    """
    if _scrub_box is None:
        _scrub_box = {}
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

    # ── Privacy Mirror: scrub at the cloud boundary (non-streaming) ──────────
    # Local models keep the raw payload on-device; cloud routes get a reversibly
    # pseudonymized payload, and think()'s wrapper rehydrates the reply.
    sess = None
    if active_model not in ("Ollama_Local", "LlamaCpp_Local") and settings.get("privacy_mirror_enabled", True):
        try:
            from privacy_mirror import ScrubSession, ensure_model_ready
            ensure_model_ready(timeout=45)  # wait for the scrubber on a cold start so the
            # first cloud message is never sent unscrubbed (normally instant: the model is
            # preloaded at server startup, so this returns immediately)
            sess = ScrubSession()
            system_content = sess.scrub(system_content)
            text_content = sess.scrub(text_content)
            user_content = text_content
            if messages:
                for _m in messages:
                    if isinstance(_m.get("content"), str):
                        _m["content"] = sess.scrub(_m["content"])
            _scrub_box["sess"] = sess
        except Exception as e:
            log.warning(f"Privacy Mirror scrub failed in think() (sending unscrubbed): {e}")
            sess = None

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
                    # All entries were system-role; synthesise a user turn from the current prompt
                    anthropic_messages = [{"role": "user", "content": msg_content}]
                elif anthropic_messages[-1]["role"] != "user":
                    # History ends on an assistant turn — append the current user message
                    anthropic_messages.append({"role": "user", "content": msg_content})
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
            ollama_url = _safe_local_url(settings.get("ollama_base_url", "http://localhost:11434"), 11434)
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

        elif active_model == "LlamaCpp_Local":
            llamacpp_url = _safe_local_url(settings.get("llamacpp_base_url", "http://localhost:8080"), 8080)
            llamacpp_model = settings.get("llamacpp_model", "") or "default"
            log.info(f"Routing think() → llama.cpp ({llamacpp_model} @ {llamacpp_url})")
            try:
                resp = requests.post(
                    f"{llamacpp_url}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": llamacpp_model,
                        "messages": [
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": user_content}
                        ],
                        "stream": False
                    },
                    timeout=120
                )
                res = resp.json()
                return res
            except requests.exceptions.Timeout:
                log.error("llama.cpp timed out — model may still be loading.")
                return {"choices": [{"message": {"content": "llama.cpp timed out — the model might still be loading. try again in a few seconds."}}]}
            except requests.exceptions.ConnectionError:
                log.error("llama.cpp not reachable — is the server running?")
                return {"choices": [{"message": {"content": "llama.cpp server isn't running. start it with `./llama-server -m your_model.gguf`"}}]}

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
                models_to_try = ["meta-llama/llama-4-scout-17b-16e-instruct"]
            else:
                with _groq_lb_lock:
                    idx = _groq_lb_state["current_idx"]
                models_to_try = GROQ_FALLBACK_CHAIN[idx:] + GROQ_FALLBACK_CHAIN[:idx]
                
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
                
                if resp.status_code == 200 and "error" not in res:
                    req_rem = _safe_int_header(resp.headers.get("x-ratelimit-remaining-requests", 100), 100)
                    tok_rem = _safe_int_header(resp.headers.get("x-ratelimit-remaining-tokens", 50000), 50000)
                    if req_rem <= 2 or tok_rem <= 1000:
                        log.warning(f"[LB] Groq limits dangerously low for {groq_model} (reqs: {req_rem}, toks: {tok_rem}). Rotating.")
                        rotate_groq_model()
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


# Control tokens that must pass through the stream verbatim (never rehydrated,
# and they flush any held partial placeholder first to preserve ordering).
_STREAM_CONTROL_PREFIXES = ("[SYSTEM:", "[API ERROR", "[Error", "[Anthropic", "[Gemini", "[Ollama", "[[PRIVACY]]")


def _is_stream_control(tok) -> bool:
    return isinstance(tok, str) and tok.lstrip().startswith(_STREAM_CONTROL_PREFIXES)


def think_stream(prompt, context="", session_id="", images_b64=None):
    """Public streaming entry. Wraps the model loop with the Privacy Mirror
    cloud-boundary gate: emits a one-shot ``[[PRIVACY]]{...}`` sentinel with the
    scrub diff (for the in-chat reveal), then de-anonymizes streamed tokens so the
    user sees real names while the cloud only ever saw placeholders."""
    import itertools, json as _json

    scrub_box: dict = {}
    inner = _think_stream_inner(prompt, context=context, session_id=session_id,
                                images_b64=images_b64, _scrub_box=scrub_box)

    # Pull the first token — this also runs the inner generator far enough to
    # build + scrub the outbound messages, so the map is populated by now.
    try:
        first = next(inner)
    except StopIteration:
        return

    mapping = scrub_box.get("map")
    if mapping:
        yield "[[PRIVACY]]" + _json.dumps({"mapping": mapping, "model": scrub_box.get("model", "")})

    sess = scrub_box.get("sess")
    rehy = None
    if sess is not None:
        from privacy_mirror import StreamRehydrator
        rehy = StreamRehydrator(sess)

    for tok in itertools.chain([first], inner):
        if tok is None:
            continue
        if rehy is None:
            yield tok
            continue
        if _is_stream_control(tok):
            held = rehy.flush()
            if held:
                yield held
            yield tok
        else:
            out = rehy.feed(tok)
            if out:
                yield out

    if rehy is not None:
        tail = rehy.flush()
        if tail:
            yield tail


def _think_stream_inner(prompt, context="", session_id="", images_b64=None, _scrub_box=None):
    if _scrub_box is None:
        _scrub_box = {}
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
                if len(msg_text) > 16000:
                    msg_text = msg_text[:16000] + "\n...[truncated for length]"
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

    # ── Privacy Mirror: scrub at the cloud boundary ──────────────────────────
    # Only the cloud path leaks — local models (Ollama / llama.cpp) keep the raw
    # payload on-device, so we skip scrubbing entirely for them (full fidelity).
    # For cloud routes we pseudonymize EVERYTHING that's about to leave (system
    # prompt, history, user turn) through one ScrubSession, hand the map to the
    # wrapper (for rehydration + the UI reveal), and scrub tool results too.
    _scrub_box["model"] = active_model
    sess = None
    is_local_route = active_model in ("Ollama_Local", "LlamaCpp_Local")
    if not is_local_route and settings.get("privacy_mirror_enabled", True):
        try:
            from privacy_mirror import ScrubSession, ensure_model_ready
            ensure_model_ready(timeout=45)  # wait for the scrubber on a cold start so the
            # first cloud message is never sent unscrubbed (normally instant: the model is
            # preloaded at server startup, so this returns immediately)
            sess = ScrubSession()
            for _m in messages:
                _c = _m.get("content")
                if isinstance(_c, str):
                    _m["content"] = sess.scrub(_c)
                elif isinstance(_c, list):
                    for _part in _c:
                        if isinstance(_part, dict) and _part.get("type") == "text" and isinstance(_part.get("text"), str):
                            _part["text"] = sess.scrub(_part["text"])
            # Anthropic passes the system prompt via its own field (not messages),
            # so scrub the variable too — stable map keeps placeholders consistent.
            system_content = sess.scrub(system_content)
            _scrub_box["sess"] = sess
            _scrub_box["map"] = sess.mapping
        except Exception as e:
            log.warning(f"Privacy Mirror scrub failed (sending unscrubbed): {e}")
            sess = None

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
        ollama_url = _safe_local_url(settings.get("ollama_base_url", "http://localhost:11434"), 11434)
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
    elif active_model == "LlamaCpp_Local":
        llamacpp_url = _safe_local_url(settings.get("llamacpp_base_url", "http://localhost:8080"), 8080)
        model_name = settings.get("llamacpp_model", "") or "default"
        url = f"{llamacpp_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = "llamacpp"  # sentinel — llama.cpp needs no real key
        is_ollama = True       # shares the same OpenAI-compat streaming path as Ollama
        log.info(f"Routing think_stream() → llama.cpp ({model_name} @ {llamacpp_url})")
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
        if images_b64:
            model_name = "meta-llama/llama-4-scout-17b-16e-instruct"  # Vision-capable model
        else:
            with _groq_lb_lock:
                model_name = GROQ_FALLBACK_CHAIN[_groq_lb_state["current_idx"]]
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
                tried_groq = set()
                recovered_400 = False
                for _retry in range(len(GROQ_FALLBACK_CHAIN) + 1):
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
                            tried_groq.add(model_name)
                            if len(tried_groq) < len(GROQ_FALLBACK_CHAIN):
                                model_name = rotate_groq_model()
                                log.warning(f"Rate limit hit. Rotating to {model_name}...")
                                continue
                            gt = _gemini_fallback_target()
                            if gt:
                                url, model_name, headers = gt
                                log.warning("All Groq models rate-limited. Falling back to Gemini...")
                                continue
                        log.warning("Rate limit hit. Retrying in 2 seconds...")
                        import time
                        time.sleep(2)
                        continue
                    
                    if resp.status_code == 400 and ("invalid JSON" in resp.text or "malformed" in resp.text.lower()):
                        log.error(f"HTTP 400 Bad Request (JSON Error): {resp.text[:200]}")
                        if not recovered_400:
                            # Attempt recovery ONCE per step to prevent message corruption
                            if len(messages) > 1:
                                messages.pop()
                                messages.append({"role": "system", "content": "Your previous tool call contained malformed JSON. Output strictly valid JSON only."})
                            recovered_400 = True
                            continue
                        # Already retried once — break out to avoid corruption
                        break
                    
                    if resp.status_code == 200 and "groq.com" in url:
                        # Pre-emptive load balancing check
                        req_rem = _safe_int_header(resp.headers.get("x-ratelimit-remaining-requests", 100), 100)
                        tok_rem = _safe_int_header(resp.headers.get("x-ratelimit-remaining-tokens", 50000), 50000)
                        if req_rem <= 2 or tok_rem <= 1000:
                            log.warning(f"[LB] Groq limits dangerously low for {model_name} (reqs: {req_rem}, toks: {tok_rem}). Rotating.")
                            rotate_groq_model()
                            
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
                    
                    # SANITIZE JSON TO PREVENT HTTP 400 ON NEXT REQUEST
                    for tc in tool_calls:
                        args_str = tc.get("function", {}).get("arguments", "{}")
                        try:
                            # If it parses, ensure it's tightly formatted
                            clean_args = json.loads(args_str)
                            tc["function"]["arguments"] = json.dumps(clean_args)
                        except json.JSONDecodeError:
                            # Strip common hallucinated chars (e.g. > ) that break Groq's strict validator
                            clean_str = args_str.replace(">", "").replace("<", "")
                            try:
                                json.loads(clean_str)
                                tc["function"]["arguments"] = clean_str
                            except Exception:
                                # Fallback to empty object if completely unparseable
                                tc["function"]["arguments"] = "{}"
                    
                    messages.append(response_msg)
                    
                    _valid_tool_names = {td["function"]["name"] for td in TOOL_DEFINITIONS}
                    for tool_call in tool_calls:
                        func_name = tool_call.get("function", {}).get("name")
                        if func_name not in _valid_tool_names:
                            log.warning(f"LLM requested unknown tool '{func_name}' — skipping")
                            continue
                        try:
                            args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                        except Exception:
                            args = {}

                        log.info(f"Executing tool {func_name}...")
                        yield f"\n[SYSTEM: Executing {func_name}]\n"
                        result = execute_tool(func_name, args, session_id=session_id)

                        # Tool output re-enters the cloud conversation — scrub it
                        # through the same session so new PII gets stable placeholders.
                        tool_content = str(result)
                        if sess is not None:
                            tool_content = sess.scrub(tool_content)
                            _scrub_box["map"] = sess.mapping

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "name": func_name,
                            "content": tool_content
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
            tried_groq = set()
            for _retry in range(len(GROQ_FALLBACK_CHAIN) + 1):
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
                        tried_groq.add(model_name)
                        if len(tried_groq) < len(GROQ_FALLBACK_CHAIN):
                            model_name = rotate_groq_model()
                            log.warning(f"Rate limit hit on streaming. Rotating to {model_name}...")
                            continue
                        gt = _gemini_fallback_target()
                        if gt:
                            url, model_name, headers = gt
                            log.warning("All Groq models rate-limited. Falling back to Gemini (streaming)...")
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

