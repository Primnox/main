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

import itertools
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Literal

from . import failures, health, routing

log = logging.getLogger("primnox2.routing.gateway")


def _temperature() -> float:
    """The configured sampling temperature.

    Imported late, like the other settings reads in this module, because the
    settings package pulls the model catalogue back in.
    """
    from ..settings import tunables
    return float(tunables.get("models.temperature"))

Support = Literal["native", "emulated", "none"]

# Loopback in its three spellings. ONE definition, because "is this local"
# decides both whether the payload is scrubbed and whether the failover chain
# may leave the machine — two answers that must never be able to disagree
# about the same URL. It was duplicated in both provider classes before the
# chain existed, when only the first of those two questions was being asked.
_LOCAL_RE = re.compile(r"https?://(127\.0\.0\.1|localhost|\[::1\])")


def is_local_url(base_url: str) -> bool:
    return bool(_LOCAL_RE.match(base_url or ""))


# A localhost ADDRESS is not a localhost DESTINATION. OmniRoute, LiteLLM and
# every other gateway of that shape listen on 127.0.0.1 and forward to a cloud
# provider a millisecond later — so the URL heuristic above, used alone, would
# answer "local" and skip the Privacy Mirror for a prompt that is about to
# leave the machine. The catalogue's `kind` is the authority when it is known;
# the heuristic is the fallback for an endpoint nobody has classified.
ON_DEVICE_KINDS = frozenset({"ollama", "local"})
OFF_DEVICE_KINDS = frozenset({"cloud", "gateway"})


def on_device_for(kind: str, base_url: str) -> bool:
    if kind in ON_DEVICE_KINDS:
        return True
    if kind in OFF_DEVICE_KINDS:
        return False
    return is_local_url(base_url)


# ...and a SECOND question, which is not the same one. "Off-device" decides
# whether the payload is scrubbed; "needs a key" decides whether calling it
# without one is pointless. A gateway is off-device and needs no credential —
# OmniRoute answers on its free tier with nothing configured at all — so
# deriving one answer from the other would make the flagship case unusable
# without pasting in a fake key. Only a direct cloud endpoint needs one.
def requires_key_for(kind: str, base_url: str) -> bool:
    if kind == "cloud":
        return True
    if kind in ON_DEVICE_KINDS or kind == "gateway":
        return False
    return not is_local_url(base_url)

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
    requires_key = False

    def stream(self, messages: list[dict], model: str = "echo", usage: dict | None = None,
               thinking: bool = False, on_thinking: Callable[[str], None] | None = None) -> Iterator[str]:
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

    def __init__(self, base_url: str, api_key: str, model: str,
                 on_device: bool | None = None, needs_key: bool | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        # None means "nobody said" — fall back to the URL heuristic. Set
        # explicitly for a gateway, whose address lies about its destination.
        self._on_device = on_device
        self._needs_key = needs_key

    @property
    def is_local(self) -> bool:
        if self._on_device is not None:
            return self._on_device
        return is_local_url(self.base_url)

    @property
    def requires_key(self) -> bool:
        if self._needs_key is not None:
            return self._needs_key
        return not self.is_local

    def stream(self, messages: list[dict], model: str | None = None,
               usage: dict | None = None, thinking: bool = False,
               on_thinking: Callable[[str], None] | None = None) -> Iterator[str]:
        import urllib.request

        body = json.dumps({
            "model": model or self.model,
            "messages": messages,
            "stream": True,
            # Sent explicitly rather than left to the provider. Omitting it
            # inherits whatever the server prefers -- ~0.8 on Ollama -- and
            # every turn here offers tools, which are structured output that a
            # high temperature actively degrades. See models.temperature.
            #
            # Only on this path: the Anthropic route below enables thinking,
            # and that API requires temperature 1, so pinning it there would
            # trade a real capability for a knob Claude does not need.
            "temperature": _temperature(),
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
                    delta_obj = chunk["choices"][0]["delta"]
                except (KeyError, IndexError):
                    continue
                # No request field turns this on — a reasoning model (DeepSeek-R1,
                # QwQ, and most others behind an OpenAI-compatible endpoint) just
                # includes it unprompted. `thinking`/`on_thinking` are accepted
                # for symmetry with AnthropicProvider so the gateway can call
                # either without branching on provider type, but this path
                # never needs the caller to have asked first.
                reasoning = delta_obj.get("reasoning_content") or delta_obj.get("reasoning")
                if reasoning and on_thinking is not None:
                    on_thinking(reasoning)
                content = delta_obj.get("content")
                if content:
                    yield content


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

# Anthropic's minimum cacheable prefix. Below this the API ignores the marker,
# so sending it is pointless rather than harmful — but checking first keeps the
# request honest about what it is asking for.
MIN_CACHEABLE_TOKENS = 1024


def _cacheable_system(system: str):
    """The system prompt, marked so the provider can cache it between calls.

    This is the single largest saving available to a tool-using turn, and it
    was being left entirely on the table. The prefix — grammar, rules, the
    tool catalogue, memory, the skills index — is ~2,800 tokens and is
    IDENTICAL on every iteration of the tool loop by construction: the
    scheduler builds it once before the loop and the loop only ever appends.
    Measured, an eight-step turn is billed ~36,500 tokens, of which about
    22,300 is that unchanged prefix re-sent seven more times at full price.

    A local model already avoids this for free — llama.cpp and Ollama reuse
    the KV cache on an exact prefix match, which is exactly what an
    append-only message list gives them. A hosted one does not unless asked,
    and Anthropic's way of being asked is a `cache_control` marker on the last
    block that should be cached. Reads then cost about a tenth of an ordinary
    input token.

    The accounting for this already existed — `_merge_usage` sums
    `cache_creation_input_tokens` and `cache_read_input_tokens` and has a
    comment explaining that `input_tokens` alone under-reports when caching is
    in play. Something was written to measure a saving nothing was requesting.

    Returned as a plain string below the threshold, which is also the shape
    every provider that is not Anthropic understands.
    """
    from ..context.service import estimate_tokens

    if estimate_tokens(system) < MIN_CACHEABLE_TOKENS:
        return system
    return [{"type": "text", "text": system,
             "cache_control": {"type": "ephemeral"}}]


def _cacheable_conversation(convo: list[dict]) -> list[dict]:
    """Mark the end of the conversation so the tool loop stops re-buying it.

    `_cacheable_system` caches the preamble, which is the largest single
    block, and stops there — so on an eight-step turn the preamble is read
    back cheaply seven times while every tool result is re-sent at FULL price
    on every step after it. The block that never changes was cached and the
    part that grows was not, which is backwards: the growing part is the one
    being paid for repeatedly.

    Measured on `bench_compaction.py`'s eight-step workload, with the result
    store compacting from the first result:

        system block only              8,226 billed   93.3% under no-cache
        breakpoint at the end of it    6,104 billed   95.0%

    THIS IS ONLY SAFE BECAUSE NOTHING IS EVER REWRITTEN. A prefix cache keys
    on exact bytes, so marking a conversation that gets edited between steps
    would invalidate the whole prefix and buy a cache write it never reads
    back — a loss, not a saving. `observations.Ledger` decides once, at
    append time, and the loop only ever appends; that invariant is what makes
    the breakpoint collectable, and it is why the two mechanisms compound
    instead of cancelling.

    The marker goes on the LAST message rather than a fixed position, because
    the prefix worth caching is everything sent so far and that grows by one
    exchange each step. Anthropic reads the longest cached prefix at or below
    the marker, so last-message placement collects the previous step's write.

    Only from the second message on. A conversation of one message is the
    first call of a turn: there is no earlier prefix to read, and the write
    would be paid by a turn that may never take a second step — which is the
    measured 1% loss at one step that `observations.strategy` already refuses.
    """
    from ..context.service import estimate_tokens

    if len(convo) < 2:
        return convo

    total = sum(estimate_tokens(str(m.get("content", ""))) for m in convo)
    if total < MIN_CACHEABLE_TOKENS:
        # Below the provider's minimum cacheable size the marker is ignored
        # and, on some gateways, charged for anyway. Not worth the request.
        return convo

    marked = list(convo)
    last = dict(marked[-1])
    content = last.get("content")
    if isinstance(content, str):
        last["content"] = [{"type": "text", "text": content,
                            "cache_control": {"type": "ephemeral"}}]
    elif isinstance(content, list) and content:
        blocks = [dict(b) if isinstance(b, dict) else b for b in content]
        if isinstance(blocks[-1], dict):
            blocks[-1]["cache_control"] = {"type": "ephemeral"}
        last["content"] = blocks
    else:
        return convo
    marked[-1] = last
    return marked



class AnthropicProvider:
    """Anthropic's messages API — a different wire format, same contract.

    Kept as its own adapter rather than special-cased inside the OpenAI one:
    translating to a provider's format is the adapter's whole job, and mixing
    two formats in one class is how that job stops being separable.
    """

    name = "anthropic"

    def __init__(self, base_url: str, api_key: str, model: str,
                 on_device: bool | None = None, needs_key: bool | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        # None means "nobody said" — fall back to the URL heuristic. Set
        # explicitly for a gateway, whose address lies about its destination.
        self._on_device = on_device
        self._needs_key = needs_key

    @property
    def is_local(self) -> bool:
        if self._on_device is not None:
            return self._on_device
        return is_local_url(self.base_url)

    @property
    def requires_key(self) -> bool:
        if self._needs_key is not None:
            return self._needs_key
        return not self.is_local

    def stream(self, messages: list[dict], model: str | None = None,
               usage: dict | None = None, thinking: bool = False,
               on_thinking: Callable[[str], None] | None = None) -> Iterator[str]:
        import urllib.request

        # Anthropic takes the system prompt as a top-level field, not a message.
        system = " ".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]

        # Thinking's budget has to come out of max_tokens, not add to it — the
        # API rejects a budget >= max_tokens outright. 4096 total, 1024 of it
        # thinking, leaves 3072 for the actual reply; a smaller total budget
        # here would starve one or the other.
        max_tokens = 4096
        body = json.dumps({
            "model": model or self.model,
            "max_tokens": max_tokens,
            "stream": True,
            **({"system": _cacheable_system(system)} if system else {}),
            "messages": _cacheable_conversation(convo),
            **({"thinking": {"type": "enabled", "budget_tokens": 1024}} if thinking else {}),
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
                    delta = event.get("delta", {})
                    # A thinking block streams as `thinking_delta` (payload
                    # key `thinking`, not `text`) followed eventually by a
                    # `signature_delta` — the signature is only needed to hand
                    # the block back to the API on a later turn, which this
                    # gateway does not do, so it's dropped rather than parsed.
                    if delta.get("type") == "thinking_delta":
                        piece = delta.get("thinking")
                        if piece and on_thinking is not None:
                            on_thinking(piece)
                        continue
                    text = delta.get("text")
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

    The dev-tree-relative path only resolves in a dev checkout — inside a
    frozen build, `__file__` sits somewhere under PyInstaller's per-launch
    extraction temp dir, which has no "three parents up to v2/" to find and
    is wiped on every restart regardless. Next to the installed executable is
    used instead when frozen, same reasoning (and the same fallback shape) as
    privacy/mirror.py's _resolve_model_source() second candidate: writable,
    and still there on the next launch.
    """
    path = (Path(sys.executable).resolve().parent / ".env" if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[3] / ".env")
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
    # Written by settings.models.activate() alongside the URL. Without it the
    # environment round-trip would lose the one fact the URL cannot express:
    # that this localhost port is a gateway to the cloud, not a model on it.
    kind = os.getenv("PRIMNOX_PROVIDER_KIND", "").strip()
    if base and model:
        cls = AnthropicProvider if api_type == "anthropic" else OpenAICompatProvider
        return cls(base, key, model, on_device_for(kind, base),
                   requires_key_for(kind, base)), model

    settings = _v1_settings()
    active = settings.get("active_model", "")

    if active == "Custom":
        wanted = settings.get("active_custom_provider_id", "")
        profile = next((p for p in settings.get("custom_providers", [])
                        if p.get("id") == wanted), None)
        if profile and profile.get("base_url") and profile.get("model"):
            cls = AnthropicProvider if profile.get("api_type") == "anthropic" else OpenAICompatProvider
            kind = str(profile.get("kind") or "")
            return cls(profile["base_url"], profile.get("api_key", ""), profile["model"],
                       on_device_for(kind, profile["base_url"]),
                       requires_key_for(kind, profile["base_url"])), profile["model"]

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
def _failover_attempts() -> int:
    try:
        from ..settings import tunables
        return int(tunables.get("models.failover_attempts"))
    except Exception as exc:                                  # noqa: BLE001
        log.debug("tunables unavailable (%s); failover disabled for this call", exc)
        return 1        # no settings store yet — behave like the old single gate


def _open_stream(provider, messages, model, usage, thinking, on_thinking):
    """Call a provider's stream(), tolerating the older three-argument shape.

    NOTHING HAS BEEN EXECUTED when this returns. A generator function does not
    run its body until the first `next()`, which is precisely why failover has
    to be driven off the first token rather than off this call.
    """
    try:
        return provider.stream(messages, model, usage=usage,
                               thinking=thinking, on_thinking=on_thinking)
    except TypeError:
        log.debug("%s.stream() has the legacy signature; calling it positionally",
                  type(provider).__name__)
        return provider.stream(messages, model)


def stream_completion(messages: list[dict], usage: dict | None = None,
                       scrub_map: list | None = None,
                       on_thinking: Callable[[str], None] | None = None,
                       route: list | None = None) -> Iterator[str]:
    """Every outbound model call passes through here.

    Local providers skip scrubbing entirely — nothing leaves the device, so
    there is nothing to pseudonymize. Cloud providers get the Privacy Mirror
    applied here, at this one boundary — both directions of it: outbound
    messages are pseudonymized before `provider.stream()` ever sees them, and
    the reply is rehydrated before a single token leaves this function. That
    is what makes this the one gate rather than half of one: a caller that
    only saw the scrubbed request and rehydrated the response itself would be
    a second place that could get out of sync with this one.

    `scrub_map` is an output parameter, following the same convention as
    `usage`: the caller (kernel/scheduler.py) passes a list in, and if the
    turn's outbound payload got scrubbed, this function appends the session's
    reveal map to it before returning — which is how the caller learns there
    is something to show without this module needing to know about turns,
    conversations, or the event bus.

    `on_thinking` is a callback rather than a second output parameter like
    `scrub_map`, because thinking arrives incrementally, mid-stream — the
    caller needs each piece as it lands to flush it as its own event, not
    the accumulated whole after this generator is exhausted. `stream_completion`
    itself stays a plain `Iterator[str]` of reply text throughout; thinking is
    always a side channel, never mixed into the yielded stream, so nothing
    that reads this function's return value needs to know it exists.

    `route` is a third output parameter in the same style: one entry per
    provider this turn touched, in order, each saying what happened to it.
    Uninteresting on the happy path; the whole story when a turn failed over,
    which is otherwise invisible to everything downstream.

    FAILOVER COMMITS ON THE FIRST TOKEN. A provider that dies before yielding
    anything can be replaced silently — nothing downstream has seen a byte, so
    nothing has to be taken back. A provider that dies after yielding cannot:
    restarting on another model would splice two half-answers into one reply,
    and neither the user nor the transcript could tell where the seam was. So
    the first token is the point of no return, and a failure after it is
    raised, not routed around.
    """
    # Only Anthropic's wire format needs to be TOLD to think — an
    # unsupported model answers this with a 400 rather than ignoring it, so
    # it is opt-in (see settings/service.py's ALLOWED entry for why there is
    # no safe default). OpenAI-compatible reasoning models need no such flag;
    # they include reasoning_content unprompted, so that provider reads
    # `thinking` from `settings_service` too, but only to decide whether it's
    # worth bothering — it never sends anything different because of it.
    from ..settings import service as settings_service
    thinking = settings_service.get("model.thinking_enabled", "off") == "on"

    policy = failures.FailoverPolicy(max_attempts=_failover_attempts())
    lockout = health.Lockout.resolve()
    attempts: list[dict] = []
    sess = None
    outbound = messages
    scrubbed_for_cloud = False
    tried = 0
    first_failure: failures.Failure | None = None
    first_exception: BaseException | None = None
    turn_started = time.time()

    def note(**entry) -> None:
        attempts.append(entry)
        if route is not None:
            route.append(entry)

    log.debug("turn starting: %d message(s), thinking=%s, budget=%d attempt(s)",
              len(messages), thinking, policy.max_attempts)

    for cand in routing.chain(policy.max_attempts):
        if tried >= policy.max_attempts:
            log.warning("attempt budget of %d exhausted; %s and anything after it "
                        "will not be tried", policy.max_attempts, cand.label)
            note(provider=cand.label, model=cand.model, status="skipped",
                 reason="attempt_budget_exhausted")
            break

        # Catch a missing key here rather than letting the provider answer 403.
        # A remote endpoint's refusal is indistinguishable from a wrong model, a
        # revoked key, or a proxy problem — so the one case we can identify
        # ourselves should be named precisely instead of guessed at afterwards.
        if cand.requires_key and not cand.api_key:
            log.error("%s (%s) has no API key configured", cand.label, cand.model)
            note(provider=cand.label, model=cand.model, status="skipped", reason="no_key")
            if first_exception is None:
                first_exception = RuntimeError(
                    f"No API key is configured for "
                    f"{getattr(cand.provider, 'base_url', 'this provider')}. "
                    "Add one in Settings — the model name is not the problem.")
            continue

        # An open breaker costs nothing to consult and saves a full connect
        # timeout, so it is checked before the attempt is counted: being
        # skipped is not an attempt, and must not consume the turn's budget.
        if health.is_open(cand.key):
            note(provider=cand.label, model=cand.model, status="skipped",
                 reason="circuit_open", opens_in_s=round(health.opens_in_s(cand.key), 1))
            continue

        # Scrubbed once for the whole chain, not once per attempt: every cloud
        # candidate gets the same placeholders, so whichever one answers can be
        # rehydrated from the same session — and a retry does not pay for the
        # scrub again. A local candidate reached from a cloud head is handed
        # the scrubbed payload too; pseudonymized text is never the wrong thing
        # to send somewhere that was already allowed to see the real thing.
        if not cand.is_local and not scrubbed_for_cloud:
            sess, outbound = _scrub_outbound(messages)
            scrubbed_for_cloud = True
            log.debug("outbound payload %s for the cloud leg of this chain",
                      "scrubbed" if sess is not None else "NOT scrubbed (mirror off or failed)")

        tried += 1
        started = time.time()
        log.info("attempt %d/%d -> %s (%s)%s",
                 tried, policy.max_attempts, cand.label, cand.model,
                 " [failover]" if attempts else "")
        try:
            stream = _open_stream(cand.provider, outbound, cand.model,
                                  usage, thinking, on_thinking)
            # The generator body has not run yet. THIS is where the request is
            # actually made, and therefore where a dead provider announces
            # itself — while failover is still free.
            first = next(stream)
        except StopIteration:
            # A clean, empty reply. Not a failure — some models legitimately
            # answer nothing — but there is nothing to yield and nothing to
            # rehydrate either.
            elapsed = (time.time() - started) * 1000
            health.record_success(cand.key, elapsed)
            log.info("%s answered empty in %dms", cand.label, round(elapsed))
            note(provider=cand.label, model=cand.model, status="ok", empty=True,
                 ms=round(elapsed))
            _commit_scrub_map(sess, scrub_map)
            return
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            # Cancellation, not failure. Recording it against the provider
            # would bench a healthy endpoint because the user pressed stop.
            log.info("%s cancelled by the caller after %dms",
                     cand.label, round((time.time() - started) * 1000))
            raise
        except BaseException as exc:                          # noqa: BLE001
            elapsed = (time.time() - started) * 1000
            failure = failures.from_exception(exc, cand.label, cand.model)
            health.record_failure(cand.key, failure, lockout)
            note(provider=cand.label, model=cand.model, status="failed",
                 reason=failure.type, retryable=failure.retryable,
                 error=failure.message[:300], ms=round(elapsed))
            if first_failure is None:
                first_failure, first_exception = failure, exc

            if not failures.should_failover(failure, policy):
                log.error("%s failed with %s and the chain stops here: %s",
                          cand.label, failure.summary, failure.message[:300])
                raise
            log.warning("%s failed with %s after %dms; trying the next provider",
                        cand.label, failure.summary, round(elapsed))
            continue

        elapsed = (time.time() - started) * 1000
        health.record_success(cand.key, elapsed)
        note(provider=cand.label, model=cand.model, status="ok",
             ms=round(elapsed), failed_over=bool(attempts))
        if attempts[:-1]:
            log.warning("FAILED OVER to %s (%s) — first token in %dms, %d earlier "
                        "candidate(s) did not answer",
                        cand.label, cand.model, round(elapsed), len(attempts) - 1)
        else:
            log.info("%s answered, first token in %dms", cand.label, round(elapsed))
        _commit_scrub_map(sess, scrub_map)
        yield from _emit(first, stream, sess)
        log.debug("turn complete in %.1fs via %s",
                  time.time() - turn_started, cand.label)
        return

    # Nothing answered. The FIRST failure is raised rather than the last: it is
    # the one about the provider the user actually chose, and "your Groq key is
    # rejected" is a more useful thing to read than a connection error from the
    # third fallback they have never heard of.
    log.error("no provider answered this turn: %s",
              "; ".join(f"{a['provider']}={a['status']}"
                        f"{'(' + a['reason'] + ')' if a.get('reason') else ''}"
                        for a in attempts) or "no candidates at all")
    if first_exception is None:
        raise RuntimeError(
            "No provider is configured. Add one in Settings — Primnox has "
            "nothing to send this turn to.")
    if len(attempts) <= 1:
        raise first_exception
    label = first_failure.provider if first_failure else "the active provider"
    raise RuntimeError(
        f"All {len(attempts)} providers failed this turn. "
        f"{label}: {first_exception}"
    ) from first_exception


def _commit_scrub_map(sess, scrub_map: list | None) -> None:
    """Publish the reveal map only once a provider has actually committed.

    Extending it per attempt would show the user a privacy reveal for a request
    that was abandoned before it produced a single token.
    """
    if sess is not None and scrub_map is not None:
        scrub_map.extend(sess.mapping)
        log.debug("published a reveal map of %d entry(ies)", len(sess.mapping))


def _emit(first: str, rest: Iterator[str], sess) -> Iterator[str]:
    """Yield the committed stream, rehydrating if the payload was scrubbed."""
    if sess is None:
        yield first
        yield from rest
        return

    from ..privacy.mirror import StreamRehydrator
    rehy = StreamRehydrator(sess)
    # itertools.chain, not `(first, *rest)` — unpacking would drain the entire
    # reply into a tuple before the first token was yielded, turning a
    # streaming gate into a buffering one.
    for tok in itertools.chain((first,), rest):
        out = rehy.feed(tok)
        if out:
            yield out
    tail = rehy.flush()
    if tail:
        yield tail


def _scrub_outbound(messages: list[dict]) -> tuple["ScrubSession | None", list[dict]]:
    """Pseudonymize everything about to leave the device through one
    ScrubSession, so the cloud model sees consistent placeholders for repeated
    values and the reply can be rehydrated unambiguously.

    Returns (session, scrubbed_messages). `session` is None when the feature
    is off or the scrub itself fails — the caller then sends `messages`
    unchanged rather than blocking the turn on a privacy layer that isn't
    working, mirroring V1's own "log and continue unscrubbed" choice at this
    exact boundary.

    The system message is EXEMPT, and that is not a privacy hole: it is the
    prompt Primnox wrote, it contains none of the user's data, and it carries
    the tool syntax the model has to reproduce verbatim. Scrubbing it was
    measured doing real damage — `<run_python>...</run_python>` came back as
    §BIC_1§ (detected as a bank code), `react` as §STATE_1§, a lone `|` as
    §USERAGENT_1§ — so the model was being handed instructions it could no
    longer follow, in exchange for hiding nothing. Every other role still goes
    through the scrubber untouched by this change.
    """
    from ..settings import service as settings_service
    if settings_service.get("privacy.mirror_enabled", "on") != "on":
        return None, messages

    try:
        from ..privacy.mirror import ScrubSession, ensure_model_ready
        # Waits for a cold-start model load so the FIRST cloud message of a
        # session is never sent unscrubbed. Normally instant once the model
        # has loaded once — see ensure_model_ready()'s own docstring.
        ensure_model_ready(timeout=45)
        sess = ScrubSession()
        scrubbed = []
        for m in messages:
            content = m.get("content")
            if isinstance(content, str) and m.get("role") != "system":
                m = {**m, "content": sess.scrub(content)}
            scrubbed.append(m)
        return sess, scrubbed
    except Exception as exc:
        import logging
        logging.getLogger("primnox2.privacy").warning(
            f"Privacy Mirror scrub failed (sending unscrubbed): {exc}")
        return None, messages
