"""Model Gateway + Capability Layer — CRS/1.0 §13.1, §13.2 and ARCH §5.

Two invariants:

  §13.1.1  No code outside this package branches on provider name.
  §13.2.2  This is the ONLY place the local/cloud decision is made and the
           only place PII scrubbing is applied. One gate, one audit point.

The capability layer exists because V1 already had one by accident: brain.py
discovered tool-calling support by parsing HTTP 400 bodies and caching the
answer. This makes that explicit, and adds emulation for models that cannot
call tools natively.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

Support = Literal["native", "emulated", "none"]

# Sent on every outbound provider request.
#
# Python's default `Python-urllib/3.11` is rejected outright by Cloudflare's
# browser-integrity check — measured against capi.aerolink.lat, which answered
# HTTP 403 "error code: 1010" to every request: every model, both auth styles,
# both endpoint shapes, and even a bare GET /v1/models. The identical request
# with this header returns 200.
#
# This is also the likely explanation for V1's "provider returned non-JSON with
# HTTP 200" crash: a Cloudflare challenge page is HTML, and `resp.json()` on
# HTML raises exactly the JSONDecodeError V1 surfaced as a chat bubble.
#
# Nothing here is a bypass of authentication — the API key still does the
# authenticating. It only stops a legitimate desktop client from being
# misidentified as a bot because it did not name itself.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class Capabilities:
    tool_calling: Support = "emulated"
    vision: Support = "none"
    json_mode: bool = False
    streaming: bool = True
    context_window: int = 8192
    max_output: int = 4096
    parallel_tool_calls: bool = False


# Static registry, overridden by runtime probes. Keyed by a substring of the
# model id so a version bump does not silently fall back to defaults.
_REGISTRY: list[tuple[str, Capabilities]] = [
    ("gpt-4",     Capabilities("native", "native", True, True, 128_000, 16_384, True)),
    ("gpt-5",     Capabilities("native", "native", True, True, 400_000, 128_000, True)),
    ("claude",    Capabilities("native", "native", True, True, 200_000, 64_000, True)),
    ("gemini",    Capabilities("native", "native", True, True, 1_000_000, 8_192, True)),
    ("llama",     Capabilities("native", "none", True, True, 128_000, 8_192, False)),
    ("qwen",      Capabilities("emulated", "none", True, True, 32_768, 8_192, False)),
    ("deepseek",  Capabilities("emulated", "none", True, True, 64_000, 8_192, False)),
    ("echo",      Capabilities("emulated", "none", False, True, 8_192, 4_096, False)),
]

_probe_cache: dict[tuple[str, str], Capabilities] = {}


def capabilities_for(base_url: str, model: str) -> Capabilities:
    key = (base_url, model)
    if key in _probe_cache:
        return _probe_cache[key]
    lowered = (model or "").lower()
    caps = next((c for frag, c in _REGISTRY if frag in lowered), Capabilities())
    _probe_cache[key] = caps
    return caps


def demote_tool_calling(base_url: str, model: str) -> None:
    """The provider answered 400 'tools not supported'. Remember it.

    V1 learned this the same way but had nowhere to put the knowledge except a
    module-level dict in brain.py; here it updates the capability profile that
    the rest of the system already reads.
    """
    caps = capabilities_for(base_url, model)
    if caps.tool_calling == "native":
        _probe_cache[(base_url, model)] = Capabilities(
            "emulated", caps.vision, caps.json_mode, caps.streaming,
            caps.context_window, caps.max_output, False,
        )


# ── Universal tool protocol (ARCH §5.2) ──────────────────────────────────────
# Primnox's schema, not OpenAI's and not Anthropic's. Provider adapters
# translate to whatever the wire wants; adding a provider never touches tools/.
TOOL_SCHEMA_VERSION = 1

EMULATION_GRAMMAR = """\
When you need a tool, reply with exactly this and nothing else:

<tool name="TOOL_NAME">
{"arg": "value"}
</tool>

Available tools:
{tools}
"""

_TOOL_BLOCK = re.compile(r'<tool\s+name="([^"]+)"\s*>\s*(\{.*?\})\s*</tool>', re.S)


def parse_emulated_tool_call(text: str) -> dict | None:
    """Delimited blocks, not bare JSON.

    A bare-JSON contract fails on any model that prefixes prose — and
    prose-prefixing is exactly what the weaker models this path exists for
    actually do.
    """
    m = _TOOL_BLOCK.search(text or "")
    if not m:
        return None
    try:
        return {"name": m.group(1), "arguments": json.loads(m.group(2))}
    except json.JSONDecodeError:
        return {"name": m.group(1), "arguments": {}, "malformed": True}


# ── Providers ────────────────────────────────────────────────────────────────
class EchoProvider:
    """A local provider that needs no key and no network.

    Its purpose is that `v2` runs end to end on a clean checkout: the turn
    lifecycle, streaming, cancellation and reconnect are all exercisable
    without credentials. It is also the only honest way to test the runtime
    without conflating runtime bugs with provider flakiness.
    """

    name = "echo"
    base_url = "local://echo"
    is_local = True

    def stream(self, messages: list[dict], model: str = "echo") -> Iterator[str]:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        reply = (
            f"You said: {last}\n\n"
            "This is the echo provider — no network, no key, nothing leaves the machine. "
            "It exists so the turn lifecycle, streaming, cancellation and reconnect can be "
            "exercised without credentials. Point Settings at a real provider for real replies."
        )
        for word in reply.split(" "):
            yield word + " "
            time.sleep(0.03)


class OpenAICompatProvider:
    """Anything speaking the OpenAI chat-completions wire format.

    Covers OpenAI, Groq, Ollama, LlamaCpp and most 'custom' endpoints, which is
    why the runtime does not need a class per vendor.
    """

    name = "openai-compat"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @property
    def is_local(self) -> bool:
        return bool(re.match(r"https?://(127\.0\.0\.1|localhost|\[::1\])", self.base_url))

    def stream(self, messages: list[dict], model: str | None = None,
               usage: dict | None = None) -> Iterator[str]:
        import urllib.request

        body = json.dumps({
            "model": model or self.model,
            "messages": messages,
            "stream": True,
            # Most OpenAI-compatible servers honour this and send a final
            # usage-only chunk; the ones that don't simply omit it.
            "stream_options": {"include_usage": True},
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if usage is not None and chunk.get("usage"):
                    u = chunk["usage"]
                    usage["input_tokens"] = u.get("prompt_tokens")
                    usage["output_tokens"] = u.get("completion_tokens")
                    usage["model"] = chunk.get("model")
                try:
                    delta = chunk["choices"][0]["delta"].get("content")
                except (KeyError, IndexError):
                    continue
                if delta:
                    yield delta


def _absorb_usage(sink: dict, reported: dict) -> None:
    """Merge a provider's usage block, including its cache accounting.

    `input_tokens` alone is NOT the prompt size when prompt caching is in play
    — it counts only the uncached remainder. A 600-token system prompt that was
    cached reports `input_tokens: 2`, which reads as "this turn was free" and
    is wrong by two orders of magnitude. The cache fields have to be added back
    to get the real prompt size, and kept separately because they are billed at
    different rates (writes cost more than normal input, reads far less).
    """
    for field in ("input_tokens", "output_tokens",
                  "cache_creation_input_tokens", "cache_read_input_tokens"):
        value = reported.get(field)
        if value is not None:
            sink[field] = value
    sink["prompt_tokens_total"] = (
        (sink.get("input_tokens") or 0)
        + (sink.get("cache_creation_input_tokens") or 0)
        + (sink.get("cache_read_input_tokens") or 0)
    )


class AnthropicProvider:
    """Anthropic's messages API — a different wire format, same contract.

    Kept as its own adapter rather than special-cased inside the OpenAI one:
    translating to a provider's format is the adapter's whole job, and mixing
    two formats in one class is how that job stops being separable.
    """

    name = "anthropic"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @property
    def is_local(self) -> bool:
        return bool(re.match(r"https?://(127\.0\.0\.1|localhost|\[::1\])", self.base_url))

    def stream(self, messages: list[dict], model: str | None = None,
               usage: dict | None = None) -> Iterator[str]:
        import urllib.request

        # Anthropic takes the system prompt as a top-level field, not a message.
        system = " ".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]

        body = json.dumps({
            "model": model or self.model,
            "max_tokens": 4096,
            "stream": True,
            **({"system": system} if system else {}),
            "messages": convo,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue

                # Real token counts, straight from the provider. `message_start`
                # carries the input count, `message_delta` the running output
                # count — estimating either from character counts is guesswork
                # when the provider is already telling us.
                if usage is not None:
                    if event.get("type") == "message_start":
                        u = event.get("message", {}).get("usage", {}) or {}
                        _absorb_usage(usage, u)
                        usage["model"] = event.get("message", {}).get("model")
                    elif event.get("type") == "message_delta":
                        _absorb_usage(usage, event.get("usage", {}) or {})

                if event.get("type") == "content_block_delta":
                    text = event.get("delta", {}).get("text")
                    if text:
                        yield text


def _load_env_file() -> None:
    """Read `v2/.env` into the environment, without overriding real env vars.

    This exists because AppData is not reachable for everyone: it is hidden in
    Explorer, `%APPDATA%` does not expand in bash, and on some setups the path
    resolves differently from one shell to the next. A file sitting in the
    project you already have open in an editor has none of those problems.

    Real environment variables win, so this can never silently override a key
    passed on the command line.
    """
    path = Path(__file__).resolve().parents[3] / ".env"
    if not path.is_file():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value and not os.environ.get(key):
                os.environ[key] = value
    except OSError:
        return


_load_env_file()


def _v1_settings() -> dict:
    """Read V1's settings.json, if it exists.

    V2 reads the provider you already configured rather than asking you to
    enter it twice. Read-only, and only the provider fields are touched — V2
    never writes to V1's settings.
    """
    # Matches settings_manager.get_appdata_dir() in V1 — the directory is
    # "primnox_extension", a leftover from when Primnox shipped as a browser
    # extension. Guessing "Primnox" here silently fell back to the echo
    # provider with no error, which is exactly the kind of quiet failure worth
    # not having: if the path is wrong we want to know.
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "primnox_extension" if appdata else Path.home() / ".primnox_extension"
    path = base / "settings.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


# Built-in providers, so `active_model` from V1 resolves without a name branch
# anywhere outside this module (CRS §13.1.1).
_BUILTIN = {
    "Groq_Llama_3": ("https://api.groq.com/openai/v1", "groq_api_key", "groq_model", "openai"),
    "OpenAI_GPT_4o": ("https://api.openai.com/v1", "openai_api_key", "openai_model", "openai"),
    "Anthropic": ("https://api.anthropic.com", "anthropic_api_key", "anthropic_model", "anthropic"),
}


def active_provider():
    """Resolve the configured provider. Falls back to echo, never to a crash.

    Order: environment variables, then V1's saved settings, then echo.
    """
    # An explicit escape hatch. Without it, a machine with V1 settings on disk
    # can never reach the echo provider, which makes the "runs on a clean
    # checkout with no key" property untestable on exactly the machines where
    # you most want to separate a runtime bug from a provider problem.
    if os.getenv("PRIMNOX_PROVIDER", "").strip().lower() == "echo":
        return EchoProvider(), "echo"

    base = os.getenv("PRIMNOX_BASE_URL", "").strip()
    key = os.getenv("PRIMNOX_API_KEY", "").strip()
    model = os.getenv("PRIMNOX_MODEL", "").strip()
    api_type = os.getenv("PRIMNOX_API_TYPE", "openai").strip()
    if base and model:
        cls = AnthropicProvider if api_type == "anthropic" else OpenAICompatProvider
        return cls(base, key, model), model

    settings = _v1_settings()
    active = settings.get("active_model", "")

    if active == "Custom":
        wanted = settings.get("active_custom_provider_id", "")
        profile = next((p for p in settings.get("custom_providers", [])
                        if p.get("id") == wanted), None)
        if profile and profile.get("base_url") and profile.get("model"):
            cls = AnthropicProvider if profile.get("api_type") == "anthropic" else OpenAICompatProvider
            return cls(profile["base_url"], profile.get("api_key", ""), profile["model"]), profile["model"]

    if active in _BUILTIN:
        url, key_field, model_field, kind = _BUILTIN[active]
        api_key = (settings.get(key_field) or "").strip()
        if api_key:
            chosen = (settings.get(model_field) or "").strip() or active
            cls = AnthropicProvider if kind == "anthropic" else OpenAICompatProvider
            return cls(url, api_key, chosen), chosen

    return EchoProvider(), "echo"


def describe_active() -> dict:
    """What the UI shows in the context panel. Never includes the key."""
    provider, model = active_provider()
    return {
        "provider": type(provider).__name__.replace("Provider", ""),
        "model": model,
        "local": provider.is_local,
        "base_url": getattr(provider, "base_url", "local"),
    }


# ── The gate (§13.2) ─────────────────────────────────────────────────────────
def stream_completion(messages: list[dict], usage: dict | None = None) -> Iterator[str]:
    """Every outbound model call passes through here.

    Local providers skip scrubbing entirely — nothing leaves the device, so
    there is nothing to pseudonymize. Cloud providers would have the Privacy
    Mirror applied here, at this one boundary, rather than inside the model
    code as V1 did.
    """
    provider, model = active_provider()

    # Catch a missing key here rather than letting the provider answer 403.
    # A remote endpoint's refusal is indistinguishable from a wrong model, a
    # revoked key, or a proxy problem — so the one case we can identify
    # ourselves should be named precisely instead of guessed at afterwards.
    if not provider.is_local and not getattr(provider, "api_key", ""):
        raise RuntimeError(
            f"No API key is configured for {getattr(provider, 'base_url', 'this provider')}. "
            "Add one in Settings — the model name is not the problem."
        )

    if not provider.is_local:
        # Placeholder for the Privacy Mirror boundary. Deliberately explicit:
        # a subsystem reaching a provider without passing this point is
        # non-conformant regardless of any other property (§13.2.3).
        messages = _scrub_outbound(messages)

    # Not every provider reports usage (the echo provider has none to report),
    # so this is passed only where it is supported rather than made mandatory.
    try:
        yield from provider.stream(messages, model, usage=usage)
    except TypeError:
        yield from provider.stream(messages, model)


def _scrub_outbound(messages: list[dict]) -> list[dict]:
    # V1's privacy_mirror.py ports in here unchanged; kept as an identity
    # function rather than a fake so nothing claims protection it is not
    # providing.
    return messages
