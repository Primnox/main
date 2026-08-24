"""Privacy Mirror — PII redaction layer, ported from V1's backend/privacy_mirror.py.

Primary: ai4privacy/deberta-v3-base-pii  (50+ entity types, local inference)
Fallback: regex patterns (instant, used until the model finishes loading)

The model is lazy-loaded in a background thread on first use so startup is
never blocked. `redact_text()` is always safe to call — it uses whichever
engine is ready at the time. Everything below this docstring is logic-for-logic
the same as V1: the gazetteer, the regex patterns and the per-label confidence
gates all came from measuring real leaks against the model (see the comments
inline), not from a spec, so they are ported rather than re-derived.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger("primnox2.privacy")

# ── Regex fallback ─────────────────────────────────────────────────────────────

# Gazetteer backstop for place names the NER model does not detect.
#
# Measured 2026-08-06: the DeBERTa model reliably tags US locations
# ("San Francisco" 0.999) but produces no span at all for Mumbai, Delhi,
# Chennai or Tokyo, so those leaked verbatim at every confidence threshold.
# That is the worst possible failure for this user base — the model's blind spot
# is exactly the set of cities most likely to appear in their text.
#
# Deliberately excludes names that are also ordinary English words (Reading,
# Nice, Mobile, Bath, Cork), which would over-redact normal prose. Requires an
# exact capitalised match on a word boundary.
_CITY_GAZETTEER = [
    # India
    "Mumbai", "Delhi", "New Delhi", "Bengaluru", "Bangalore", "Hyderabad",
    "Chennai", "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat", "Lucknow",
    "Kanpur", "Nagpur", "Indore", "Bhopal", "Patna", "Vadodara", "Coimbatore",
    "Kochi", "Visakhapatnam", "Bhubaneswar", "Chandigarh", "Guwahati", "Mysuru",
    "Thiruvananthapuram", "Noida", "Gurugram", "Gurgaon",
    # Rest of world
    "Tokyo", "Osaka", "Kyoto", "Beijing", "Shanghai", "Shenzhen", "Guangzhou",
    "Seoul", "Singapore", "Bangkok", "Jakarta", "Manila", "Hanoi", "Dubai",
    "Abu Dhabi", "Doha", "Riyadh", "Karachi", "Lahore", "Islamabad", "Dhaka",
    "Colombo", "Kathmandu", "Tehran", "Istanbul", "Cairo", "Nairobi", "Lagos",
    "Johannesburg", "Cape Town", "Casablanca",
    "Berlin", "Munich", "Hamburg", "Frankfurt", "Vienna", "Zurich", "Geneva",
    "Amsterdam", "Rotterdam", "Brussels", "Copenhagen", "Stockholm", "Oslo",
    "Helsinki", "Warsaw", "Prague", "Budapest", "Bucharest", "Athens",
    "Lisbon", "Porto", "Madrid", "Barcelona", "Valencia", "Seville",
    "Rome", "Milan", "Naples", "Turin", "Venice", "Florence",
    "Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux",
    "London", "Manchester", "Birmingham", "Liverpool", "Leeds", "Glasgow",
    "Edinburgh", "Bristol", "Belfast", "Dublin", "Cardiff",
    "Moscow", "Kyiv", "Kiev", "Minsk", "Tbilisi",
    "Toronto", "Vancouver", "Montreal", "Ottawa", "Calgary",
    "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Auckland",
    "Wellington", "Mexico City", "Guadalajara", "Bogota", "Lima", "Santiago",
    "Buenos Aires", "Montevideo", "Sao Paulo", "Rio de Janeiro", "Brasilia",
]

_REGEX_PATTERNS: dict[str, str] = {
    "EMAIL":       r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "IPV4":        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    "CREDIT_CARD": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    "API_KEY":     r'(?:api_key|secret|password|token|key)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{16,})["\']?',
    "GENERIC_KEY": r'\b[a-zA-Z0-9]{32,}\b',
    # Longest-first so "New Delhi" wins over "Delhi".
    "CITY":        r'\b(?:' + '|'.join(
                       re.escape(c) for c in sorted(_CITY_GAZETTEER, key=len, reverse=True)
                   ) + r')\b',
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

_pipeline = None          # transformers NER pipeline, set when ready
_model_loading = False
_model_failed = False
_load_lock = threading.Lock()

# Entity types the model returns that we want to redact.
# The model uses IOB2 tags: B-LABEL / I-LABEL  (begin / inside)
# Full label list: https://huggingface.co/ai4privacy/deberta-v3-base-pii
# Confidence gate for a model-detected entity.
#
# This was 0.80, chosen as if false positives and false negatives cost the same.
# They do not. A false negative ships real PII to a third-party provider and is
# unrecoverable. A false positive replaces a word with a placeholder that
# ScrubSession.rehydrate() puts back before the user ever sees it — so the user
# pays almost nothing for over-redaction.
#
# Measured at 0.80 (see V1's bench_scrubber.py): "London" scored 0.777,
# "California" 0.757 — both just under the gate, both leaked verbatim.
_NER_MIN_SCORE = 0.40

# Labels that fire on bare integers and therefore need a much higher bar.
#
# Over-redaction is NOT free, despite rehydration: the placeholder is restored
# before the user sees the answer, but the cloud model reasons on the scrubbed
# text. Redacting "exit code 137" to §CREDITCARDCVV§ hides the one token the
# model needed, and it answers worse.
#
# Measured 2026-08-06 — the separation is clean:
#   real  "my cvv is 921 / pin is 4432"     -> 0.99+
#   spurious  "exit code 137"  CVV          -> 0.638
#             "scale replicas to 12"  AGE   -> 0.564
#             "exit code 255"  BUILDINGNUM  -> 0.859
_NER_MIN_SCORE_BY_LABEL: dict[str, float] = {
    "CREDITCARDCVV": 0.90,
    "PIN": 0.90,
    "AGE": 0.90,
    "HEIGHT": 0.90,
    "AMOUNT": 0.90,
    "BUILDINGNUMBER": 0.90,
    "MASKEDNUMBER": 0.90,
}

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
    "URL", "USERAGENT", "USERNAME",
    "VEHICLEVIN", "VEHICLEVRM", "ZIPCODE",
    # NOTE: TIME deliberately excluded — time-of-day isn't PII, the model often
    # echoes it, and an echoed §TIME_n§ that isn't in the map leaks to the user.
}

# Never scrub the app's / assistant's / providers' own identity. These aren't the
# user's PII; scrubbing them strips the model's own context (it stops knowing who
# it is) and floods the reveal with noise (e.g. "Primnox"→FIRSTNAME, "nox"→STATE).
_NEVER_SCRUB = {
    "primnox", "nox", "claude", "anthropic", "groq", "openai", "gpt", "chatgpt",
    "gemini", "google", "ollama", "llama", "mixtral", "qwen", "gemma", "deepseek",
    "ai", "assistant", "user", "system", "bot",
}


def _resolve_model_source() -> str:
    """Prefer a bundled/local copy of the model (no network, no startup-leak
    window); fall back to the HF hub id so dev runs still work — and reuse
    whatever V1 already downloaded, since both backends share one machine's
    HF cache.

    - Frozen build: PyInstaller extracts datas under sys._MEIPASS → models/pii.
    - Dev run: backend/models/pii (not currently populated by anything —
      the HF-hub fallback below is what actually resolves today).
    - Otherwise: the HF id, which transformers downloads (or reuses from
      cache) on first use.
    """
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / "models" / "pii")
        candidates.append(Path(sys.executable).resolve().parent / "models" / "pii")
    candidates.append(Path(__file__).resolve().parents[2] / "models" / "pii")
    for path in candidates:
        if (path / "config.json").exists():
            log.info(f"Using bundled PII model at {path}")
            return str(path)
    log.info("No bundled PII model found — falling back to HF download/cache")
    return _MODEL_ID


def _load_model() -> None:
    global _pipeline, _model_loading, _model_failed
    try:
        model_src = _resolve_model_source()
        log.info(f"Loading PII model ({model_src})…")
        from transformers import (
            AutoModelForTokenClassification, AutoTokenizer, pipeline as hf_pipeline,
        )
        import torch

        device = 0 if torch.cuda.is_available() else -1
        # Weights ship fp16 on disk (~370 MB). CPU fp16 matmul is unsupported and
        # raises "mat1 and mat2 must have the same dtype (Half vs Float)", which
        # silently knocks PII detection down to the regex-only fallback (misses
        # names, phones, etc.). Load the weights AS fp32 up front on CPU (fp16 on
        # GPU for speed) — the dtype is then applied to every weight before the
        # pipeline ever runs.
        load_dtype = torch.float16 if device == 0 else torch.float32
        tok = AutoTokenizer.from_pretrained(model_src)
        try:
            mdl = AutoModelForTokenClassification.from_pretrained(model_src, dtype=load_dtype)
        except TypeError:  # older transformers still uses torch_dtype
            mdl = AutoModelForTokenClassification.from_pretrained(model_src, torch_dtype=load_dtype)
        _pipeline = hf_pipeline(
            "token-classification",
            model=mdl,
            tokenizer=tok,
            aggregation_strategy="simple",  # merges B/I tokens → one span
            device=device,
        )
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


# Model is NOT loaded at import time — call start_model_loading() when the
# feature is actually needed, or let ensure_model_ready() kick it off lazily.


# ── Main redaction API ─────────────────────────────────────────────────────────

# Max chars to send per inference call — model has a 512-token limit.
# 1500 chars is a safe upper bound for 512 tokens in mixed text.
_CHUNK_SIZE = 1500


def _model_redact(text: str) -> str:
    """Run DeBERTa PII detection and replace detected spans with labels.

    Delegates span-finding to _detect_spans() rather than walking the pipeline
    output directly. That matters: the SentencePiece tokenizer splits one entity
    into several subword tokens ("A"/"nike"/"th" are three FIRSTNAME tokens with
    contiguous offsets), and transformers does not reliably merge them back —
    aggregation_strategy="simple" returned them unmerged on 5.14.1. Replacing
    each token separately emitted "[FIRSTNAME][FIRSTNAME][FIRSTNAME]", which not
    only reads badly but leaks the subword-token count of the value being
    hidden. _detect_spans() already coalesces contiguous same-label spans,
    applies the regex backstop, trims whitespace and honours _NEVER_SCRUB.
    """
    if not text:
        return text

    spans = _detect_spans(text)
    if not spans:
        return text

    # Replace right-to-left so earlier offsets stay valid as the string shortens.
    chars = list(text)
    for sp in sorted(spans, key=lambda s: s["start"], reverse=True):
        chars[sp["start"]:sp["end"]] = list(f"[{sp['label']}]")
    return "".join(chars)


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
    """Call this when the feature is enabled (e.g. a settings toggle)."""
    _ensure_model_loading()


def ensure_model_ready(timeout: float = 6.0) -> bool:
    """Close the startup leak window for a single cloud call: make sure the PII
    model is loaded *before* we scrub an outbound payload. Kicks off loading if
    it hasn't started, then blocks up to `timeout` seconds for it to become
    ready.

    Returns True if the model is ready, False if it's still loading or failed —
    in which case the caller proceeds with the regex backstop (so emails / IPs /
    cards / keys are still caught, just not names/addresses until the model
    lands). The wait only ever happens while the model is mid-load; once ready
    it returns instantly.
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
# This is the engine behind the cloud-boundary privacy gate in gateway.py — the
# map (originals + placeholders) never leaves the device.

# Plausible partial-placeholder at the end of a stream chunk (e.g. "§EMAIL_1"
# before its closing §). Held back until the rest of the placeholder arrives.
_PARTIAL_PLACEHOLDER_RE = re.compile(r"§[A-Z]*_?\d*$")

# Safety nets so a raw placeholder NEVER reaches the user: a complete §LABEL_n§
# we have no mapping for (model echoed/invented it), and a dangling partial left
# at end-of-stream. Both require ≥1 letter so legit "§5" (section 5) is untouched.
_LEFTOVER_PLACEHOLDER_RE = re.compile(r"§[A-Z]+_\d+§")
_DANGLING_PLACEHOLDER_RE = re.compile(r"§[A-Z]+_?\d*$")


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
                label = e.get("entity_group", "").upper()
                gate = _NER_MIN_SCORE_BY_LABEL.get(label, _NER_MIN_SCORE)
                if label in _REDACT_LABELS and e.get("score", 0) >= gate:
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
        if s < en and text[s:en].strip().lower() not in _NEVER_SCRUB:
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
        if not text:
            return text
        # Replace longer placeholders first so §X_10§ isn't clobbered by §X_1§.
        for ph in sorted(self.to_original, key=len, reverse=True):
            if ph in text:
                text = text.replace(ph, self.to_original[ph])
        # Safety net: strip any complete placeholder we couldn't map (the model
        # echoed or invented it) so a raw §...§ token never reaches the user.
        text = _LEFTOVER_PLACEHOLDER_RE.sub("[redacted]", text)
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
        # Drop a dangling partial placeholder left at end-of-stream (rehydrate's
        # full-token sweep won't catch an unterminated one).
        out = _DANGLING_PLACEHOLDER_RE.sub("", out)
        return out
