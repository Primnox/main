# backend/privacy_mirror.py
"""
Privacy Mirror — PII redaction layer for Primnox.

Primary: ai4privacy/deberta-v3-base-pii  (50+ entity types, local inference)
Fallback: regex patterns (instant, used until model finishes loading)

The model is lazy-loaded in a background thread on first import so startup
is never blocked. `redact_text()` is always safe to call — it uses whichever
engine is ready at the time.
"""

from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path
from typing import Optional

from logger import get_logger

log = get_logger("privacy")

# ── Regex fallback ─────────────────────────────────────────────────────────────

_REGEX_PATTERNS: dict[str, str] = {
    "EMAIL":       r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "IPV4":        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    "CREDIT_CARD": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    "API_KEY":     r'(?:api_key|secret|password|token|key)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{16,})["\']?',
    "GENERIC_KEY": r'\b[a-zA-Z0-9]{32,}\b',
}

def _regex_redact(text: str) -> str:
    if not text:
        return text
    count = 0
    for label, pattern in _REGEX_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            count += len(matches)
            if label == "API_KEY":
                text = re.sub(pattern, lambda m: m.group(0).replace(m.group(1), "[REDACTED]"), text)
            else:
                text = re.sub(pattern, f"[{label}]", text)
    if count:
        log.debug(f"regex redacted {count} items")
    return text


# ── DeBERTa model (lazy, background) ──────────────────────────────────────────

_MODEL_ID = "Isotonic/deberta-v3-base_finetuned_ai4privacy_v2"
_CACHE_DIR = None  # uses HF default (~/.cache/huggingface)

_pipeline = None          # transformers NER pipeline, set when ready
_model_loading = False
_model_failed = False
_load_lock = threading.Lock()

# Entity types the model returns that we want to redact.
# The model uses IOB2 tags: B-LABEL / I-LABEL  (begin / inside)
# Full label list: https://huggingface.co/ai4privacy/deberta-v3-base-pii
_REDACT_LABELS = {
    "ACCOUNTNAME", "ACCOUNTNUMBER", "AGE", "AMOUNT",
    "BIC", "BITCOINADDRESS", "BUILDINGNUMBER",
    "CITY", "COMPANYNAME", "COUNTY",
    "CREDITCARDCVV", "CREDITCARDISSUER", "CREDITCARDNUMBER",
    "DATE", "DOB", "EMAIL", "ETHEREUMADDRESS", "EYECOLOR",
    "FIRSTNAME", "GENDER", "HEIGHT", "IBAN",
    "IP", "IPV4", "IPV6",
    "JOBAREA", "JOBTITLE", "JOBTYPE",
    "LASTNAME", "LITECOINADDRESS", "MAC", "MASKEDNUMBER",
    "MIDDLENAME", "NEARBYGPSCOORDINATE",
    "PASSWORD", "PHONEIMEI", "PHONENUMBER", "PIN", "PREFIX",
    "SECONDARYADDRESS", "SEX", "SSN", "STATE", "STREET",
    "TIME", "URL", "USERAGENT", "USERNAME",
    "VEHICLEVIN", "VEHICLEVRM", "ZIPCODE",
}


def _resolve_model_source() -> str:
    """Prefer a bundled/local copy of the model (no network, no startup-leak
    window); fall back to the HF hub id so dev runs still work.

    - Frozen build: PyInstaller extracts datas under sys._MEIPASS → models/pii.
    - Dev run: backend/models/pii (populated by fetch_pii_model.py).
    - Otherwise: the HF id, which transformers downloads on first use.
    """
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / "models" / "pii")
        candidates.append(Path(sys.executable).resolve().parent / "models" / "pii")
    candidates.append(Path(__file__).resolve().parent / "models" / "pii")
    for path in candidates:
        if (path / "config.json").exists():
            log.info(f"Using bundled PII model at {path}")
            return str(path)
    log.info("No bundled PII model found — falling back to HF download")
    return _MODEL_ID


def _load_model() -> None:
    global _pipeline, _model_loading, _model_failed
    try:
        model_src = _resolve_model_source()
        log.info(f"Loading PII model ({model_src})…")
        from transformers import pipeline as hf_pipeline
        import torch

        device = 0 if torch.cuda.is_available() else -1
        _pipeline = hf_pipeline(
            "token-classification",
            model=model_src,
            aggregation_strategy="simple",  # merges B/I tokens → one span
            device=device,
        )
        # Weights ship as fp16 on disk (~370 MB). On CPU, upcast to fp32 in RAM —
        # CPU fp16 compute is poorly supported / slow. Disk stays small, inference
        # stays fast. On GPU we leave fp16 (faster, lower VRAM). Done via an in-place
        # cast rather than the (version-dependent) dtype kwarg.
        if device == -1:
            _pipeline.model.float()
        log.info(f"PII model ready (device={'cuda' if device == 0 else 'cpu'})")
    except Exception as exc:
        _model_failed = True
        log.warning(f"PII model failed to load, using regex fallback: {exc}")
    finally:
        _model_loading = False


def _ensure_model_loading() -> None:
    global _model_loading
    with _load_lock:
        if _pipeline is None and not _model_loading and not _model_failed:
            _model_loading = True
            t = threading.Thread(target=_load_model, daemon=True, name="pii-model-loader")
            t.start()


# Model is NOT loaded at import time — call start_model_loading() when the user
# enables Privacy Shield in settings.


# ── Main redaction API ─────────────────────────────────────────────────────────

# Max chars to send per inference call — model has a 512-token limit.
# 1500 chars is a safe upper bound for 512 tokens in mixed text.
_CHUNK_SIZE = 1500


def _model_redact(text: str) -> str:
    """Run DeBERTa PII detection and replace detected spans with labels."""
    if not text:
        return text

    # Process in chunks to stay within model token limits
    chunks: list[str] = []
    for i in range(0, len(text), _CHUNK_SIZE):
        chunk = text[i : i + _CHUNK_SIZE]
        try:
            entities = _pipeline(chunk)  # type: ignore[misc]
        except Exception as exc:
            log.warning(f"PII model inference error: {exc}")
            chunks.append(_regex_redact(chunk))
            continue

        # Build redacted chunk by replacing spans from right to left
        # (so offsets stay valid as we shorten the string)
        filtered = [
            e for e in entities
            if e.get("entity_group", "").upper() in _REDACT_LABELS
            and e.get("score", 0) >= 0.80
        ]
        filtered.sort(key=lambda e: e["start"], reverse=True)

        # Snapshot leading chars from the original string before any mutation
        span_prefixes = {
            ent["start"]: " " if chunk[ent["start"]:ent["start"]+1] == " " else ""
            for ent in filtered
        }
        chunk_chars = list(chunk)
        for ent in filtered:
            label = ent["entity_group"].upper()
            start, end = ent["start"], ent["end"]
            prefix = span_prefixes[start]
            chunk_chars[start:end] = list(f"{prefix}[{label}]")

        chunks.append("".join(chunk_chars))

    redacted = "".join(chunks)
    # Also catch anything the model might have missed (API keys, generic hashes)
    redacted = _regex_redact(redacted)
    return redacted


def redact_text(text: str) -> str:
    """
    Redact PII from text.  Uses the DeBERTa model when it's loaded,
    otherwise falls back to regex patterns.
    """
    if not text:
        return text

    if _pipeline is not None:
        return _model_redact(text)

    # Model still loading — use regex and log once
    if _model_loading:
        log.debug("PII model not ready yet, using regex fallback")
    return _regex_redact(text)


def start_model_loading() -> None:
    """Call this when the user enables Privacy Shield in settings."""
    _ensure_model_loading()


def ensure_model_ready(timeout: float = 6.0) -> bool:
    """Close the startup leak window for a single cloud call: make sure the PII
    model is loaded *before* we scrub an outbound payload. Kicks off loading if it
    hasn't started, then blocks up to `timeout` seconds for it to become ready.

    Returns True if the model is ready, False if it's still loading or failed —
    in which case the caller proceeds with the regex backstop (so emails / IPs /
    cards / keys are still caught, just not names/addresses until the model lands).
    The wait only ever happens while the model is mid-load; once ready it returns
    instantly.
    """
    if _pipeline is not None:
        return True
    if _model_failed:
        return False
    _ensure_model_loading()
    import time as _t
    deadline = _t.time() + max(0.0, timeout)
    while _t.time() < deadline:
        if _pipeline is not None:
            return True
        if _model_failed:
            return False
        _t.sleep(0.15)
    return _pipeline is not None


def is_model_ready() -> bool:
    """True once the DeBERTa model has finished loading."""
    return _pipeline is not None


def model_status() -> str:
    if _pipeline is not None:
        return "ready"
    if _model_failed:
        return "failed"
    if _model_loading:
        return "loading"
    return "not_started"


# ── Reversible scrubbing (pseudonymization) ─────────────────────────────────────
#
# Unlike redact_text() (one-way, destroys the value), a ScrubSession replaces each
# PII value with a STABLE placeholder (§LABEL_n§) and keeps a local map so the
# model's reply can be de-anonymized before the user sees it. The same original
# always maps to the same placeholder within a session, so the cloud model sees
# consistent tokens and rehydration is unambiguous.
#
# This is the engine behind the cloud-boundary privacy gate in brain.py and the
# in-chat "privacy thinking" reveal: the map (originals + placeholders) never
# leaves the device — it powers both the un-redaction and the UI diff.

# Plausible partial-placeholder at the end of a stream chunk (e.g. "§EMAIL_1"
# before its closing §). Held back until the rest of the placeholder arrives.
_PARTIAL_PLACEHOLDER_RE = re.compile(r"§[A-Z]*_?\d*$")


def _detect_spans(text: str) -> list[dict]:
    """Return non-overlapping PII spans [{start, end, label, text}] for `text`,
    using the DeBERTa model when ready, always backstopped by regex."""
    spans: list[dict] = []

    if _pipeline is not None:
        for i in range(0, len(text), _CHUNK_SIZE):
            chunk = text[i : i + _CHUNK_SIZE]
            try:
                entities = _pipeline(chunk)  # type: ignore[misc]
            except Exception as exc:
                log.warning(f"PII model inference error: {exc}")
                continue
            for e in entities:
                if e.get("entity_group", "").upper() in _REDACT_LABELS and e.get("score", 0) >= 0.80:
                    s, en = i + e["start"], i + e["end"]
                    spans.append({"start": s, "end": en, "label": e["entity_group"].upper(), "text": text[s:en]})

    # Regex backstop (also runs while the model loads — closes the startup gap
    # for the patterns it covers).
    for label, pattern in _REGEX_PATTERNS.items():
        for m in re.finditer(pattern, text):
            if label == "API_KEY" and m.groups():
                s, en = m.start(1), m.end(1)
            else:
                s, en = m.start(), m.end()
            spans.append({"start": s, "end": en, "label": label, "text": text[s:en]})

    if not spans:
        return []

    # The SentencePiece tokenizer emits subword fragments (e.g. "A"/"nike"/"th"
    # all FIRSTNAME), so coalesce contiguous/overlapping same-label spans into one
    # whole entity; for overlapping *different* labels, keep the first and clip the
    # rest. Then trim surrounding whitespace so placeholders don't swallow spaces.
    spans.sort(key=lambda x: (x["start"], -(x["end"])))
    merged: list[dict] = []
    for sp in spans:
        if merged and sp["start"] <= merged[-1]["end"]:
            prev = merged[-1]
            if sp["label"] == prev["label"]:
                prev["end"] = max(prev["end"], sp["end"])  # extend the entity
                continue
            if sp["end"] <= prev["end"]:
                continue  # fully covered by a different label — drop
            sp = {"start": prev["end"], "end": sp["end"], "label": sp["label"]}  # clip
        merged.append({"start": sp["start"], "end": sp["end"], "label": sp["label"]})

    out: list[dict] = []
    for sp in merged:
        s, en = sp["start"], sp["end"]
        while s < en and text[s].isspace():
            s += 1
        while en > s and text[en - 1].isspace():
            en -= 1
        if s < en:
            out.append({"start": s, "end": en, "label": sp["label"], "text": text[s:en]})
    return out


class ScrubSession:
    """Reversible PII scrubber with a per-session placeholder map."""

    def __init__(self) -> None:
        self._to_placeholder: dict[str, str] = {}   # original  -> §LABEL_n§
        self.to_original: dict[str, str] = {}        # §LABEL_n§ -> original
        self._counters: dict[str, int] = {}
        self.events: list[dict] = []                 # ordered unique reveals

    def _placeholder_for(self, original: str, label: str) -> str:
        existing = self._to_placeholder.get(original)
        if existing:
            return existing
        n = self._counters.get(label, 0) + 1
        self._counters[label] = n
        ph = f"§{label}_{n}§"
        self._to_placeholder[original] = ph
        self.to_original[ph] = original
        self.events.append({"original": original, "placeholder": ph, "label": label})
        return ph

    def scrub(self, text: str) -> str:
        if not text:
            return text
        spans = _detect_spans(text)  # left-to-right (reading order)
        if not spans:
            return text
        # Assign placeholders in reading order so numbering reads naturally…
        for sp in spans:
            self._placeholder_for(sp["text"], sp["label"])
        # …but splice right-to-left so earlier offsets stay valid.
        chars = list(text)
        for sp in sorted(spans, key=lambda x: x["start"], reverse=True):
            chars[sp["start"]:sp["end"]] = list(self._to_placeholder[sp["text"]])
        return "".join(chars)

    def rehydrate(self, text: str) -> str:
        if not text or not self.to_original:
            return text
        # Replace longer placeholders first so §X_10§ isn't clobbered by §X_1§.
        for ph in sorted(self.to_original, key=len, reverse=True):
            if ph in text:
                text = text.replace(ph, self.to_original[ph])
        return text

    @property
    def mapping(self) -> list[dict]:
        """Ordered, unique [{original, placeholder, label}] — for the UI reveal.
        Stays on-device; it's the user's own data shown back to them."""
        return list(self.events)


class StreamRehydrator:
    """Rehydrate placeholders in a streamed token sequence, buffering a trailing
    partial placeholder until the rest of it arrives."""

    def __init__(self, session: ScrubSession) -> None:
        self._s = session
        self._buf = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        out = self._s.rehydrate(self._buf)
        m = _PARTIAL_PLACEHOLDER_RE.search(out)
        if not m:
            self._buf = ""
            return out
        self._buf = out[m.start():]  # hold the possible partial
        return out[: m.start()]

    def flush(self) -> str:
        out = self._s.rehydrate(self._buf)
        self._buf = ""
        return out


# ── CLI smoke test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time

    samples = [
        "Hi, I'm John Smith. Email me at john.smith@example.com or call +1-555-867-5309.",
        "My SSN is 123-45-6789 and my Visa is 4111-1111-1111-1111 (exp 09/26, CVV 123).",
        "Server at 192.168.1.100, MAC 00:1A:2B:3C:4D:5E, token=sk_live_abc123def456ghi789jkl.",
        "Born 14 March 1990, height 5'11\", weight 180 lbs, blood type O+.",
    ]

    print("Waiting for model to load (up to 60 s)…")
    for _ in range(60):
        if is_model_ready():
            break
        time.sleep(1)

    status = model_status()
    print(f"Model status: {status}\n")

    for s in samples:
        print(f"IN : {s}")
        print(f"OUT: {redact_text(s)}\n")
