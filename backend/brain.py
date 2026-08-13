# backend/brain.py
import requests
import os
import json
import threading
import time
from pathlib import Path
from dotenv import load_dotenv
from system_prompts import MASTER_PROMPT
from logger import get_logger
from tools import TOOL_DEFINITIONS, execute_tool

load_dotenv()

log = get_logger("brain")

# Verified against the Groq API on 2026-08-06. The previous chain listed
# llama-4-scout, llama-4-maverick, qwen3-32b and mistral-saba-24b, all of which
# now return 404 model_not_found — including the first entry, which is the
# default, so every request failed even with a valid key. Ordered strongest
# first, ending in the fastest model so the last fallback is the most likely to
# answer under load.
GROQ_FALLBACK_CHAIN = [
    "openai/gpt-oss-120b",      # documented primary
    "qwen/qwen3.6-27b",         # was listed as "qwen/qwen3-32b", which 404s
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",     # fastest — last resort under load
]

# Vision on Groq. Probed 2026-08-06: llama-3.2-*-vision-preview are decommissioned
# (400) and llama-4-scout/maverick return 404 on this account, so there is no
# reachable Groq vision model. Both image paths used to hardcode llama-4-scout,
# which meant every screenshot request failed with a bare 404. Leave this empty
# to route images to Gemini (which is vision-capable) and, failing that, degrade
# to a text-only answer rather than erroring. Set it if Groq vision returns.
GROQ_VISION_MODEL = ""

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]

# Curated last-resort model lists for the per-provider picker in Settings —
# shown when live /v1/models detection fails (no key yet, network error, bad
# key). Not exhaustive, just enough that the dropdown is never empty. These
# drift as providers ship new models — worth re-checking periodically.
OPENAI_FALLBACK_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o1", "o1-mini"]
ANTHROPIC_FALLBACK_MODELS = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]

# Substrings that flag a /v1/models entry as non-chat (audio transcription,
# TTS, image generation, embeddings, moderation, ancient completion-only
# snapshots) — OpenAI's and Groq's model-list endpoints return everything the
# account can see, not just chat models, so the Settings model picker would
# otherwise be cluttered with entries that will just 400 if picked for chat.
_NON_CHAT_MODEL_MARKERS = (
    "whisper", "tts", "dall-e", "embed", "guard", "moderation", "davinci", "babbage", "ada", "orpheus",
)

# Substrings that flag a model as text-to-speech (voice synthesis) — used by
# the Knowledge Nexus "Model Library" picker. Deliberately excludes "whisper"
# (that's transcription/speech-to-text, the opposite direction).
_TTS_MODEL_MARKERS = ("tts", "orpheus")


def _is_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NON_CHAT_MODEL_MARKERS)


def _is_tts_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return any(marker in lowered for marker in _TTS_MODEL_MARKERS)

# Global Load Balancer State for Groq
_groq_lb_lock = threading.Lock()
_groq_lb_state = {
    "current_idx": 0,
}

# Endpoints (url + model) that have told us they can't do tool calling. Plenty
# of models behind an OpenAI-compatible proxy — and most self-hosted ones —
# reject a request carrying `tools` outright with a 400. Primnox attaches tools
# to every agentic turn, so on such a provider EVERY message failed with a raw
# API error and the app was unusable end to end. Learned once per endpoint,
# then that provider is simply used without tools for the rest of the process.
_no_tool_support: set[tuple[str, str]] = set()
_no_tool_support_lock = threading.Lock()

_TOOLS_UNSUPPORTED_MARKERS = (
    "tool calling",
    "tools is not supported",
    "tools are not supported",
    "does not support tools",
    "tool_choice",
    "function calling",
    "unsupported parameter: 'tools'",
    'unsupported parameter: "tools"',
)


def _rejects_tools(response_text: str) -> bool:
    """Is this 400 the provider saying "I don't do tool calling"?

    Deliberately matched on the message rather than a status code alone: a
    400 usually means our payload was wrong, and silently dropping the tools
    on every 400 would hide real bugs and quietly downgrade a capable model.
    """
    lowered = (response_text or "").lower()
    if "not support" not in lowered and "unsupported" not in lowered and "invalid" not in lowered:
        return False
    return any(marker in lowered for marker in _TOOLS_UNSUPPORTED_MARKERS)


_CONTEXT_OVERFLOW_MARKERS = (
    "context_length_exceeded",
    "reduce the length of the messages",
    "maximum context length",
    "too many tokens",
    "prompt is too long",
    "input length and `max_tokens` exceed",
)


def _context_too_long(response_text: str) -> bool:
    lowered = (response_text or "").lower()
    return any(marker in lowered for marker in _CONTEXT_OVERFLOW_MARKERS)


def _drop_oldest_turn(messages: list) -> bool:
    """Sheds the oldest history so an over-long conversation can be retried.

    Keeps the system prompt (index 0) and the user's CURRENT message (last),
    since dropping either changes what was asked rather than how much history
    came with it. Returns False when only those two remain — at that point the
    prompt itself doesn't fit and trimming can't help.

    Drops a QUARTER of the trimmable history per call, not one message. The
    retry budget is small, and a 60-turn chat shortened one message at a time
    would exhaust it while still overflowing — the user would see a failure
    that one more round of trimming would have fixed.
    """
    if len(messages) <= 2:
        return False
    # Skip index 0 when it's the system prompt; never touch the final message.
    start = 1 if messages and messages[0].get("role") == "system" else 0
    trimmable = len(messages) - 1 - start
    if trimmable <= 0:
        return False
    del messages[start:start + max(1, trimmable // 4)]
    return True


def _tools_known_unsupported(url: str, model_name: str) -> bool:
    with _no_tool_support_lock:
        return (url, model_name) in _no_tool_support


def _remember_tools_unsupported(url: str, model_name: str) -> None:
    with _no_tool_support_lock:
        _no_tool_support.add((url, model_name))


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

def _is_local_url(url: str) -> bool:
    """True if url points at localhost/127.0.0.1 — same host check as
    _safe_local_url's SSRF guard, factored out so a Custom provider can be
    classified local-vs-cloud without also inheriting that guard's port
    rewriting (a custom endpoint's URL should be used as typed, or rejected
    outright — never silently swapped for a different port)."""
    import re
    return bool(re.match(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?/?$', (url or "").strip()))


def get_active_custom_provider(settings: dict) -> dict | None:
    """Resolves whichever saved custom-endpoint profile is currently active
    (settings["active_custom_provider_id"]) out of the named-profile list.
    Returns None if no profiles exist or none match — callers should treat
    that as "no custom provider configured", the same as an empty base URL
    used to mean under the old single-slot design."""
    active_id = settings.get("active_custom_provider_id")
    if not active_id:
        return None
    for profile in settings.get("custom_providers", []):
        if profile.get("id") == active_id:
            return profile
    return None


def _is_local_provider(active_model: str, settings: dict) -> bool:
    """Local providers skip Privacy Mirror scrubbing entirely — nothing
    leaves the device, so there's nothing to scrub. Ollama/LlamaCpp are
    always local by construction. A Custom provider is classified by its
    base URL: pointed at localhost, it's local; anything else is treated as
    cloud and scrubbed like Groq/OpenAI/Anthropic/Gemini by default."""
    if active_model in ("Ollama_Local", "LlamaCpp_Local"):
        return True
    if active_model == "Custom":
        profile = get_active_custom_provider(settings)
        return _is_local_url(profile.get("base_url", "")) if profile else False
    return False


def fetch_custom_provider_models(base_url: str, api_type: str, api_key: str) -> dict:
    """Query a custom endpoint's /v1/models so the Settings UI can offer a
    dropdown instead of asking the user to type the exact model id.
    Best-effort: connection problems are reported back as a message, not an
    exception — failing to auto-detect models isn't fatal, the user can still
    type a model name by hand."""
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        return {"models": [], "error": "No base URL provided."}

    headers = {}
    if api_type == "anthropic":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.get(f"{base_url}/v1/models", headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        models = sorted({m.get("id") for m in data if m.get("id")})
        return {"models": models}
    except requests.exceptions.ConnectionError:
        log.debug(f"Custom provider model detection: connection refused at {base_url}")
        return {"models": [], "error": f"Couldn't connect to {base_url} — is it running?"}
    except requests.exceptions.Timeout:
        log.debug(f"Custom provider model detection: timed out at {base_url}")
        return {"models": [], "error": f"{base_url} didn't respond in time."}
    except requests.exceptions.HTTPError as e:
        log.debug(f"Custom provider model detection: HTTP error from {base_url}: {e}")
        status = e.response.status_code if e.response is not None else "?"
        return {"models": [], "error": f"{base_url} returned an error (HTTP {status})."}
    except Exception as e:
        # Anything else (bad URL scheme, DNS failure, malformed JSON, ...) —
        # still a clean user-facing message, not a raw exception dump.
        log.debug(f"Custom provider model detection failed for {base_url}: {e}")
        return {"models": [], "error": f"Couldn't reach {base_url}."}


def fetch_gemini_models(api_key: str) -> dict:
    """Google's List Models API has a different shape than the OpenAI-style
    /v1/models used everywhere else in this file: the key is a query param
    (not a header), and entries are named "models/gemini-..." with a
    supportedGenerationMethods list rather than a flat id — filter to models
    that actually support chat (generateContent) so e.g. embedding models
    don't show up in the picker."""
    if not api_key:
        return {"models": [], "error": "No API key provided."}
    try:
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json().get("models", [])
        models = sorted({
            m["name"].split("/", 1)[-1]
            for m in data
            if "generateContent" in (m.get("supportedGenerationMethods") or []) and m.get("name")
        })
        return {"models": models}
    except requests.exceptions.ConnectionError:
        return {"models": [], "error": "Couldn't reach Google's API — check your connection."}
    except requests.exceptions.Timeout:
        return {"models": [], "error": "Google's API didn't respond in time."}
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        return {"models": [], "error": f"Google's API returned an error (HTTP {status})."}
    except Exception as e:
        log.debug(f"Gemini model detection failed: {e}")
        return {"models": [], "error": "Couldn't reach Google's API."}


_PROVIDER_BASE_URLS = {
    "groq": ("https://api.groq.com/openai", "openai"),
    "openai": ("https://api.openai.com", "openai"),
    "anthropic": ("https://api.anthropic.com", "anthropic"),
}
_PROVIDER_FALLBACKS = {
    "groq": GROQ_FALLBACK_CHAIN,
    "openai": OPENAI_FALLBACK_MODELS,
    "anthropic": ANTHROPIC_FALLBACK_MODELS,
    "gemini": GEMINI_MODELS,
}


def fetch_provider_models(provider: str, api_key: str, capability: str = "chat") -> dict:
    """Unified model-list fetch for the 4 built-in providers, backing the
    Settings and Knowledge Nexus model pickers. Always returns a usable list —
    real detection when it works ("source": "live"), a curated static list
    when it doesn't ("source": "fallback") — so the dropdown is never empty
    just because a key isn't set yet or the provider's API hiccuped.

    capability="tts" asks for voice-synthesis models instead of chat models —
    most providers don't offer any (Anthropic has none at all), in which case
    this just returns an empty live list, not an error. There's no curated
    fallback for TTS since, unlike chat, there's no safe "this always exists"
    default to guess at."""
    provider = (provider or "").lower()
    if not api_key or api_key == "sk-****":
        api_key = get_api_key(provider) or ""
    model_filter = _is_tts_model if capability == "tts" else _is_chat_model

    if provider == "gemini":
        result = fetch_gemini_models(api_key)
        if result.get("models"):
            result["models"] = [m for m in result["models"] if model_filter(m)]
    elif provider in _PROVIDER_BASE_URLS:
        base_url, api_type = _PROVIDER_BASE_URLS[provider]
        result = fetch_custom_provider_models(base_url, api_type, api_key)
        if result.get("models"):
            result["models"] = [m for m in result["models"] if model_filter(m)]
    else:
        return {"models": [], "error": f"Unknown provider: {provider}"}

    if result.get("models") or (capability == "tts" and not result.get("error")):
        result["source"] = "live"
        result.setdefault("models", [])
        return result

    fallback = _PROVIDER_FALLBACKS.get(provider, []) if capability == "chat" else []
    return {"models": fallback, "source": "fallback", "error": result.get("error")}


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

# Circuit breaker for think_local(), matching the pattern already used for
# feed_manager.py's mac osascript calls. Without it, every caller that probes
# local inference while Ollama/llama.cpp are both down (e.g. Smart Paste on
# every clipboard transform) pays the full connect-refused + 2s health-check
# tax on every single call. One failure opens the circuit for a cooldown
# window; callers fail straight to None (and their own cloud fallback)
# instead of re-probing.
_LOCAL_UNREACHABLE_UNTIL = 0.0
_LOCAL_CIRCUIT_COOLDOWN = 30  # seconds


def _error_detail(res: dict, status_code: int, provider: str) -> str:
    """Best-effort human/log-readable error string from a provider error body.
    Only used to populate the "error" key on a failure path — the value's exact
    text is never shown to the user (choices[].content carries that), it just
    has to be truthy and non-blank so callers can branch on it."""
    err = res.get("error") if isinstance(res, dict) else None
    if isinstance(err, dict):
        detail = err.get("message") or err.get("type") or ""
    elif err:
        detail = str(err)
    else:
        detail = ""
    return f"{provider} error (HTTP {status_code}): {detail}" if detail else f"{provider} error (HTTP {status_code})"


def resolve_think_text(response: dict, fallback: str) -> str:
    """Pull the reply text out of a think()-shaped response, but only if it's
    an actual completion. think() reports a missing-key/provider failure as a
    200 with an "error" key sitting alongside a well-formed
    choices[].message.content — that content is a human-readable apology
    ("please add your API key..."), not a real transform. A caller like Smart
    Paste that blindly extracts content and hands it back to the OS clipboard
    would silently overwrite the user's data with that apology and report
    success (a real bug, found live) — so callers that can't tell the
    difference between "no error" and "error with borrowed apology text" must
    go through this instead of reading choices[] directly."""
    if response.get("error"):
        return fallback
    text = (response.get("choices") or [{}])[0].get("message", {}).get("content", fallback)
    return text.strip() or fallback


def think_local(prompt, system_override=None, timeout=90, model=None):
    """On-device inference ONLY — tries Ollama first, then llama.cpp.

    Returns the model's text content, or None if no local model is reachable.
    Use this for privacy-critical work (e.g. reading file contents during
    onboarding) that must NEVER touch a cloud provider, regardless of the
    user's configured active_model.

    `model` overrides the user's configured `ollama_model` for this call only —
    for a task like Smart Paste that doesn't need the user's main chat model,
    just a fast small one. Falls back to Ollama's normal "not available" retry
    (whatever else is pulled) exactly like the settings-derived default does.
    """
    global _LOCAL_UNREACHABLE_UNTIL
    if time.time() < _LOCAL_UNREACHABLE_UNTIL:
        return None
    try:
        from settings_manager import load_settings
        settings = load_settings()
    except Exception:
        settings = {}

    system_content = system_override or (
        "You are a precise assistant. Follow the user's formatting instructions exactly."
    )

    def _extract(data: dict) -> str:
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")

    # ── Ollama ───────────────────────────────────────────────────────────────
    # Skip the /api/tags pre-check — attempt the completion directly.
    # ConnectionRefused is instant when Ollama is down; _extract() uses .get()
    # so a malformed error body (no "choices" key) returns "" instead of crashing.
    ollama_url = _safe_local_url(settings.get("ollama_base_url", "http://localhost:11434"), 11434)
    model = model or settings.get("ollama_model", "llama3.2")
    try:
        resp = requests.post(
            f"{ollama_url}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=timeout,
        )
        content = _extract(resp.json())
        if content:
            log.info(f"think_local → Ollama ({model})")
            return content
        if not resp.ok:
            # Model might not be installed — lazy-fetch list and retry with whatever is
            status = get_ollama_status(ollama_url)
            fallback = next((m for m in status.get("models", []) if m != model), None)
            if fallback:
                log.warning(f"think_local: '{model}' not available, retrying with {fallback}")
                resp2 = requests.post(
                    f"{ollama_url}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": fallback,
                        "messages": [
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                    timeout=timeout,
                )
                content = _extract(resp2.json())
                if content:
                    log.info(f"think_local → Ollama ({fallback})")
                    return content
    except Exception as e:
        log.warning(f"think_local Ollama call failed: {e}")

    # ── llama.cpp ──────────────────────────────────────────────────────────────
    llamacpp_url = _safe_local_url(settings.get("llamacpp_base_url", "http://localhost:8080"), 8080)
    try:
        health = requests.get(f"{llamacpp_url}/health", timeout=2)
        if health.status_code == 200:
            model = settings.get("llamacpp_model", "") or "default"
            resp = requests.post(
                f"{llamacpp_url}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=timeout,
            )
            content = _extract(resp.json())
            if content:
                log.info("think_local → llama.cpp")
                return content
    except Exception as e:
        log.debug(f"think_local llama.cpp unavailable: {e}")

    log.info(f"think_local → no local model reachable, backing off {_LOCAL_CIRCUIT_COOLDOWN}s")
    _LOCAL_UNREACHABLE_UNTIL = time.time() + _LOCAL_CIRCUIT_COOLDOWN
    return None


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
    if not _is_local_provider(active_model, settings) and settings.get("privacy_mirror_enabled", True):
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
                    "model": settings.get("openai_model") or "gpt-4o",
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
                    "model": settings.get("anthropic_model") or "claude-3-5-sonnet-20241022",
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
            # An Anthropic error body has no content[].text, so the mapping
            # above silently produces an empty completion. Propagate the real
            # error instead — see resolve_think_text()'s docstring for why a
            # failure MUST be distinguishable by an "error" key rather than by
            # the caller inspecting choices[].
            status = getattr(resp, "status_code", 200)
            if status != 200 or "error" in res:
                mapped_res["error"] = _error_detail(res, status, "Anthropic")
                mapped_res["choices"][0]["message"]["content"] = content or (
                    f"anthropic request failed (HTTP {status})."
                )
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
                return {"error": "ollama timed out",
                        "choices": [{"message": {"content": "ollama timed out — the model might still be loading. try again in a few seconds."}}]}
            except requests.exceptions.ConnectionError:
                log.error("Ollama not reachable — is it running? (ollama serve)")
                return {"error": "ollama unreachable",
                        "choices": [{"message": {"content": "ollama isn't running bro. start it with `ollama serve`."}}]}

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
                return {"error": "llama.cpp timed out",
                        "choices": [{"message": {"content": "llama.cpp timed out — the model might still be loading. try again in a few seconds."}}]}
            except requests.exceptions.ConnectionError:
                log.error("llama.cpp not reachable — is the server running?")
                return {"error": "llama.cpp unreachable",
                        "choices": [{"message": {"content": "llama.cpp server isn't running. start it with `./llama-server -m your_model.gguf`"}}]}

        elif active_model == "Custom":
            profile = get_active_custom_provider(settings)
            custom_url = (profile.get("base_url") or "").strip().rstrip("/") if profile else ""
            custom_model = profile.get("model", "") if profile else ""
            custom_api_type = profile.get("api_type", "openai") if profile else "openai"
            api_key = profile.get("api_key", "") if profile else ""
            if not custom_url:
                log.error("Custom provider has no base URL set!")
                return {"error": "custom provider has no base URL",
                        "choices": [{"message": {"content": "no custom endpoint selected. add or pick one in Settings."}}]}
            log.info(f"Routing think() → Custom {custom_api_type} ({custom_model} @ {custom_url})")
            try:
                if custom_api_type == "anthropic":
                    headers = {"anthropic-version": "2023-06-01", "content-type": "application/json"}
                    if api_key:
                        headers["x-api-key"] = api_key
                    resp = requests.post(
                        f"{custom_url}/v1/messages",
                        headers=headers,
                        json={
                            "model": custom_model,
                            "max_tokens": 1024,
                            "system": system_content,
                            "messages": [{"role": "user", "content": user_content}],
                        },
                        timeout=60,
                    )
                    res = resp.json()
                    content = res.get("content", [{}])[0].get("text", "")
                    mapped = {"choices": [{"message": {"content": content}}]}
                    # Same mapping blind spot as the native Anthropic branch —
                    # an error body yields no content[].text, which must not be
                    # handed back as a successful empty completion.
                    status = getattr(resp, "status_code", 200)
                    if status != 200 or "error" in res:
                        mapped["error"] = _error_detail(res, status, "Custom (anthropic)")
                        mapped["choices"][0]["message"]["content"] = content or (
                            f"custom provider request failed (HTTP {status})."
                        )
                    return mapped
                else:
                    headers = {"Content-Type": "application/json"}
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
                    resp = requests.post(
                        f"{custom_url}/v1/chat/completions",
                        headers=headers,
                        json={
                            "model": custom_model,
                            "messages": [
                                {"role": "system", "content": system_content},
                                {"role": "user", "content": user_content},
                            ],
                            "stream": False,
                        },
                        timeout=60,
                    )
                    return resp.json()
            except requests.exceptions.Timeout:
                log.error("Custom provider timed out.")
                return {"error": "custom provider timed out",
                        "choices": [{"message": {"content": "custom provider timed out."}}]}
            except requests.exceptions.ConnectionError:
                log.error("Custom provider not reachable.")
                return {"error": f"custom provider unreachable at {custom_url}",
                        "choices": [{"message": {"content": f"couldn't reach the custom provider at {custom_url}."}}]}

        elif active_model == "Gemini_Flash":
            api_key = get_api_key("gemini")
            if not api_key:
                log.error("Gemini API key missing!")
                return {"error": "Gemini API key not set",
                        "choices": [{"message": {"content": "Gemini API key not set. Add it in Settings or set GEMINI_API_KEY env var."}}]}
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
                return {"error": f"Gemini returned non-JSON (HTTP {resp.status_code})",
                        "choices": [{"message": {"content": f"Gemini returned non-JSON (HTTP {resp.status_code})"}}]}
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
                # Was hardcoded to llama-4-scout, which 404s — so every image
                # request failed outright. Fall back to the text chain when no
                # Groq vision model is reachable: a text-only answer beats an error.
                models_to_try = [GROQ_VISION_MODEL] if GROQ_VISION_MODEL else list(GROQ_FALLBACK_CHAIN)
            else:
                with _groq_lb_lock:
                    idx = _groq_lb_state["current_idx"]
                models_to_try = GROQ_FALLBACK_CHAIN[idx:] + GROQ_FALLBACK_CHAIN[:idx]
                pinned = settings.get("groq_model")
                if pinned:
                    # Try the user's pinned model first, then fall back to the
                    # existing reliability chain if it fails — preserves
                    # today's robustness for anyone who doesn't set this.
                    models_to_try = [pinned] + [m for m in models_to_try if m != pinned]

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
_STREAM_CONTROL_PREFIXES = (
    "[SYSTEM:", "[API ERROR", "[Error", "[Anthropic", "[Gemini", "[Ollama",
    "[[PRIVACY]]", "[[TOOL]]", "[[TOOL_RESULT]]",
)


def _is_stream_control(tok) -> bool:
    return isinstance(tok, str) and tok.lstrip().startswith(_STREAM_CONTROL_PREFIXES)


# Tool output echoed into the chat is for the user's eyes, not the model's —
# keep it readable rather than dumping a multi-megabyte blob into the UI.
_TOOL_ECHO_MAX_CHARS = 4000


def _tool_start_sentinel(func_name: str, args: dict) -> str:
    """One-shot ``[[TOOL]]{...}`` sentinel announcing a tool call *with its
    actual arguments* — the exact code for run_python, the exact command for
    run_shell. The older ``[SYSTEM: Executing X]`` marker carried only a
    name, so the UI could say "using: run shell" but could never show what
    was about to run. core.py turns this into a `tool_call` event and a
    persisted chat block."""
    import json as _json
    try:
        payload = _json.dumps({"name": func_name, "args": args})
    except Exception:
        payload = _json.dumps({"name": func_name, "args": {}})
    return "[[TOOL]]" + payload


def _tool_result_sentinel(func_name: str, result) -> str:
    import json as _json
    text = str(result)
    truncated = len(text) > _TOOL_ECHO_MAX_CHARS
    if truncated:
        text = text[:_TOOL_ECHO_MAX_CHARS] + f"\n...[truncated, {len(str(result)) - _TOOL_ECHO_MAX_CHARS} more chars]"
    return "[[TOOL_RESULT]]" + _json.dumps({
        "name": func_name, "output": text, "truncated": truncated,
    })


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
            from context_manager import build_history
            raw_history = get_session_messages(session_id)
            history = build_history(raw_history, active_model, _is_local_provider(active_model, settings))
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
    is_local_route = _is_local_provider(active_model, settings)
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
    pinned_groq_model = None

    if active_model == "OpenAI_GPT_4o":
        api_key = get_api_key("openai")
        url = "https://api.openai.com/v1/chat/completions"
        model_name = settings.get("openai_model") or "gpt-4o"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif active_model == "Anthropic_Claude_3":
        api_key = get_api_key("anthropic")
        url = "https://api.anthropic.com/v1/messages"
        model_name = settings.get("anthropic_model") or "claude-3-5-sonnet-20241022"
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
        log.info(f"Routing think_stream() → Ollama ({model_name} @ {ollama_url})")
    elif active_model == "LlamaCpp_Local":
        llamacpp_url = _safe_local_url(settings.get("llamacpp_base_url", "http://localhost:8080"), 8080)
        model_name = settings.get("llamacpp_model", "") or "default"
        url = f"{llamacpp_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = "llamacpp"  # sentinel — llama.cpp needs no real key
        log.info(f"Routing think_stream() → llama.cpp ({model_name} @ {llamacpp_url})")
    elif active_model == "Custom":
        profile = get_active_custom_provider(settings)
        custom_url = (profile.get("base_url") or "").strip().rstrip("/") if profile else ""
        model_name = profile.get("model", "") if profile else ""
        custom_api_type = profile.get("api_type", "openai") if profile else "openai"
        api_key = profile.get("api_key", "") if profile else ""
        if custom_api_type == "anthropic":
            # Falls through to the Anthropic streaming branch below, which
            # only relies on url/headers/model_name (already generic) — no
            # separate handling needed for a custom Anthropic-compatible host.
            url = f"{custom_url}/v1/messages"
            headers = {"anthropic-version": "2023-06-01", "content-type": "application/json"}
            if api_key:
                headers["x-api-key"] = api_key
            api_key = api_key or "custom"  # sentinel: some custom hosts need no key
        else:
            url = f"{custom_url}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            api_key = api_key or "custom"  # sentinel — same role as Ollama/LlamaCpp's above
        log.info(f"Routing think_stream() → Custom {custom_api_type} ({model_name} @ {custom_url})")
    elif active_model == "Gemini_Flash":
        api_key = get_api_key("gemini")
        gemini_model = settings.get("gemini_model", "gemini-2.0-flash")
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        model_name = gemini_model
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        log.info(f"Routing think_stream() → Gemini ({model_name})")
    else:
        api_key = get_api_key("groq")
        url = "https://api.groq.com/openai/v1/chat/completions"
        pinned_groq_model = settings.get("groq_model") or None
        if images_b64:
            # See GROQ_VISION_MODEL — llama-4-scout was hardcoded here and 404s.
            model_name = GROQ_VISION_MODEL or GROQ_FALLBACK_CHAIN[0]
        else:
            with _groq_lb_lock:
                model_name = pinned_groq_model or GROQ_FALLBACK_CHAIN[_groq_lb_state["current_idx"]]
        headers = {"Authorization": f"Bearer {api_key}"}

    if not api_key:
        yield "Sorry, cannot process this request without AI. Please add your API key in Settings."
        return

    # Ollama/LlamaCpp/Custom-openai and Gemini used to fast-path here straight
    # to plain streaming with no tools param at all — meaning run_python,
    # web_search, save_note etc. were entirely unreachable on those
    # providers regardless of settings. They all speak the same
    # OpenAI-compatible tools/tool_calls wire format OpenAI_GPT_4o already
    # uses successfully in the loop below (a non-Groq provider proven to
    # work there today), so they now fall through into it instead of
    # returning early. If a specific self-hosted model doesn't actually
    # support function-calling, the request may come back as an error
    # rather than silently degrading to plain text — a real but accepted
    # tradeoff for giving every provider genuine tool access.

    _active_custom_profile = get_active_custom_provider(settings) if active_model == "Custom" else None
    custom_uses_anthropic = bool(_active_custom_profile and _active_custom_profile.get("api_type") == "anthropic")
    # run_python/run_shell stay out of what's offered to the model entirely
    # when code execution is disabled — not just "gated behind a permission
    # prompt", genuinely absent from the tool list the model can even see.
    # Filtered once and reused for both the request payload and the
    # tool-name validation set below, so a disabled setting can't be
    # bypassed by the model hallucinating a call anyway.
    active_tool_definitions = TOOL_DEFINITIONS
    if not settings.get("code_execution_enabled"):
        active_tool_definitions = [
            td for td in TOOL_DEFINITIONS
            if td["function"]["name"] not in ("run_python", "run_shell")
        ]
    try:
        # Only genuinely Anthropic-shaped providers (native or Custom-anthropic)
        # need the separate Anthropic Messages-API branch below — every other
        # provider (including Gemini's OpenAI-compatible endpoint, Ollama,
        # LlamaCpp, and Custom-openai) speaks the same tools/tool_calls format
        # this loop already sends.
        if active_model != "Anthropic_Claude_3" and not custom_uses_anthropic:
            max_steps = 5
            for step in range(max_steps):
                tried_groq = set()
                recovered_400 = False
                for _retry in range(len(GROQ_FALLBACK_CHAIN) + 2):
                    payload = {"model": model_name, "messages": messages}
                    if not _tools_known_unsupported(url, model_name):
                        payload["tools"] = active_tool_definitions
                        payload["tool_choice"] = "auto"
                    resp = requests.post(url, headers=headers, json=payload, timeout=60)

                    # The provider can't do tool calling. Remember it and send
                    # the same turn again as a plain completion — the model
                    # loses its tools but the user gets an answer, which beats
                    # a raw 400 pasted into the chat.
                    if (resp.status_code == 400 and "tools" in payload
                            and _rejects_tools(resp.text)):
                        _remember_tools_unsupported(url, model_name)
                        log.warning(
                            f"{model_name} rejected tool calling — continuing without tools "
                            f"for this provider ({resp.text[:120]})")
                        continue

                    # Too much conversation for this model's window. Drop the
                    # oldest turn and try again rather than losing the message
                    # — a long chat should degrade to less history, not to
                    # "Sorry, something went wrong."
                    if resp.status_code == 400 and _context_too_long(resp.text):
                        if _drop_oldest_turn(messages):
                            log.warning(
                                f"{model_name} context exceeded — retrying with "
                                f"{len(messages)} messages")
                            continue
                        # Nothing left to trim: the system prompt plus this one
                        # message already overflows, so this model can never
                        # answer. Say which model, and that it's a settings
                        # problem — "try again" would be false advice.
                        log.error(f"{model_name} cannot fit Primnox's prompt even with no history")
                        yield ("[MODEL TOO SMALL] " + model_name)
                        return

                    if resp.status_code == 429:
                        if "groq.com" in url and (model_name in GROQ_FALLBACK_CHAIN or model_name == pinned_groq_model):
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
                                    if "groq.com" in url and (model_name in GROQ_FALLBACK_CHAIN or model_name == pinned_groq_model):
                                        # rotate_groq_model() only reads/advances the global
                                        # rotation index — safe to call even when model_name
                                        # is a pinned model outside GROQ_FALLBACK_CHAIN, unlike
                                        # the old GROQ_FALLBACK_CHAIN.index(model_name) approach
                                        # this replaced (which raised ValueError for a pinned
                                        # model not in the chain).
                                        next_model = rotate_groq_model()
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
                    log.info(f"LLM decided to use {len(tool_calls)} tools (Step {step+1}).", extra={"session_id": session_id})
                    
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
                    
                    _valid_tool_names = {td["function"]["name"] for td in active_tool_definitions}
                    for tool_call in tool_calls:
                        func_name = tool_call.get("function", {}).get("name")
                        if func_name not in _valid_tool_names:
                            log.warning(f"LLM requested unknown tool '{func_name}' — skipping")
                            continue
                        try:
                            args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                        except Exception:
                            args = {}

                        log.info(f"Executing tool {func_name}...", extra={"session_id": session_id, "tool": func_name})
                        yield _tool_start_sentinel(func_name, args)
                        result = execute_tool(func_name, args, session_id=session_id)
                        yield _tool_result_sentinel(func_name, result)

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
                    if "groq.com" in url and (model_name in GROQ_FALLBACK_CHAIN or model_name == pinned_groq_model):
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
            # Anthropic Messages API — native Anthropic_Claude_3 and
            # Custom-anthropic share this branch. Anthropic requires the
            # system prompt in its own "system" field, and messages must
            # only contain role=user/assistant (no system).
            #
            # Tool-calling here mirrors the Groq/OpenAI loop's own structure
            # (non-streaming requests while tool calls might still be
            # happening, one streaming request only for the genuine final
            # answer) rather than accumulating tool_use blocks across a live
            # SSE stream — Anthropic's input_json_delta chunks would need to
            # be buffered per content-block index before they're valid JSON,
            # which adds real complexity for no behavioral difference from
            # the non-streaming shape used everywhere else in this function.
            anthropic_messages = [m for m in messages if m["role"] != "system"]
            anthropic_tools = [
                {
                    "name": td["function"]["name"],
                    "description": td["function"]["description"],
                    "input_schema": td["function"]["parameters"],
                }
                for td in active_tool_definitions
            ]

            max_steps = 5
            for step in range(max_steps):
                resp = requests.post(
                    url,
                    headers=headers,
                    json={
                        "model": model_name,
                        "messages": anthropic_messages,
                        "system": system_content,
                        "tools": anthropic_tools,
                        "max_tokens": 1024,
                    },
                    timeout=60,
                )
                if resp.status_code != 200:
                    yield f"[Anthropic error {resp.status_code}]: {resp.text[:200]}"
                    return

                data = resp.json()
                content_blocks = data.get("content", [])
                tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]

                if data.get("stop_reason") == "tool_use" and tool_use_blocks:
                    log.info(f"LLM decided to use {len(tool_use_blocks)} tools (Step {step+1}).", extra={"session_id": session_id})
                    # The assistant turn must be echoed back verbatim (text +
                    # tool_use blocks together) — Anthropic ties tool_result
                    # blocks to a specific prior tool_use id, so the history
                    # has to carry the exact block Anthropic itself produced.
                    anthropic_messages.append({"role": "assistant", "content": content_blocks})

                    tool_result_content = []
                    for block in tool_use_blocks:
                        func_name = block.get("name")
                        tool_input = block.get("input", {})
                        yield _tool_start_sentinel(func_name, tool_input)
                        result = execute_tool(func_name, tool_input, session_id=session_id)
                        yield _tool_result_sentinel(func_name, result)

                        tool_content = str(result)
                        if sess is not None:
                            tool_content = sess.scrub(tool_content)
                            _scrub_box["map"] = sess.mapping

                        tool_result_content.append({
                            "type": "tool_result",
                            "tool_use_id": block.get("id"),
                            "content": tool_content,
                        })

                    anthropic_messages.append({"role": "user", "content": tool_result_content})

                    if step == max_steps - 1:
                        log.warning("Max steps reached, forcing final response.")
                        break
                    continue
                else:
                    # No tool use — this response IS the final answer.
                    text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
                    for word in text.split(" "):
                        yield word + " "
                    return

            # Hit max_steps with a tool call still pending — force one more,
            # tool-less, streaming pass so the user gets a real answer
            # instead of nothing.
            resp_stream = requests.post(
                url,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": anthropic_messages,
                    "system": system_content,
                    "stream": True,
                    "max_tokens": 1024,
                },
                stream=True,
                timeout=60,
            )
            if resp_stream.status_code != 200:
                yield f"[Anthropic error {resp_stream.status_code}]: {resp_stream.text[:200]}"
                return
            for line in resp_stream.iter_lines():
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

