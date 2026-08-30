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
    # The single most destructive label on technical text, and it had no gate
    # at all — so it ran at the 0.40 default and shredded anything tabular.
    #
    # Measured on a markdown table of model specs, every one of these was
    # KEPT and replaced with a placeholder before the text reached the model:
    #   ' | ~' 0.857   'BERT' 0.686   ' MB' 0.697   ' GB' 0.694
    #   'a-v3 | 184M |' 0.812         ' Apache 2.0' 0.932
    # Pasting one comparison table produced 33 redactions and the reply came
    # back citing invented numbers, because the model was reading around
    # thirty-three holes. `AMOUNT` in the same paste was correctly dropped —
    # it had a gate. This label just never got one.
    #
    # 0.99 rather than 0.90 because the separation is at the very top of the
    # range and it is unusually clean: real user-agent strings score exactly
    # 1.0 ("Mozilla/5.0 (Windows NT 10.0...)" and the iPhone equivalent both
    # 1.000), while the worst technical false positive measured is 0.961
    # ('torch==2.4.0 numpy>=1.26'). Nothing real is lost at this gate.
    "USERAGENT": 0.99,
    # Measured live, 2026-08-30: asked to generate a real PPTX/PDF, the model
    # wrote ordinary reportlab/pptx code, and re-scrubbing that code on the
    # next step (same mechanism as the assistant's-own-output problem
    # documented at _is_internal_id_fragment) shredded it as IPV6 at 0.85–0.89
    # confidence — comfortably above the 0.80 default gate, so this had no
    # protection at all until now:
    #   'HexColor("#1F2A44"'        0.865   'leftMargin=0.9 * inch'   0.852
    #   'topMargin=0.85 * inch'     0.892   a bare 'Margin'           0.877
    # Fourteen of sixteen redactions across two ordinary code-generation
    # turns were this one label. It is not free even though rehydration
    # restores the real code before it runs (confirmed: execution succeeded
    # both times) — the model reads its OWN mangled code back on the next
    # step and reasons from holes, the same failure this file already
    # documents for AMOUNT above. Gate at 0.90, the same round number used
    # for every other ungated label above — the highest spurious score
    # measured is 0.892, comfortably under it.
    "IPV6": 0.90,
    # Measured live, 2026-08-30: asked "what's the risk rating on the zircon
    # falcon project again?" (a project codename, not an address), the
    # model's OWN CURRENT message — not resent history, the live turn — got
    # "zircon falcon" tagged STREET at 0.70. The user's question then read
    # as "what's the risk rating on the §STREET_1§ project", and the model,
    # unable to connect a street placeholder to the "Zircon-Falcon project"
    # named in its (unscrubbed, system-role) memory context, stopped to ask
    # a clarifying question instead of just answering — the turn the user
    # was already directly asking about, broken by the layer meant to be
    # invisible when nothing sensitive is actually there.
    #   'zircon falcon' (spurious)        0.7013
    #   'Baker Street' / 'Maple Avenue' /
    #   'Sunset Boulevard' / 'Elm Street' (real)   0.9994-0.9997
    # Separation is as clean as USERAGENT's — 0.90 sits well clear on both
    # sides, so it stays the standard gate rather than reaching for 0.99.
    "STREET": 0.90,
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

# Measured 2026-08-30: "what's the capital of australia" scrubbed "australia"
# as STATE (no confidence gate exists for that label — it falls through to
# the 0.40 default), and the model, holding only a placeholder, guessed it
# must mean a US state and asked "which one, California or Texas?" — an
# ordinary geography question failed outright.
#
# This is NOT the same shape as the greeting/FIRSTNAME problem above, and the
# argument against a vocabulary fix there does not transfer here. A greeting
# is "every interjection and loanword in every language a user might type" —
# genuinely unbounded, no authority publishes the list, it grows with every
# language anyone tries. A country is a UN member state or one of a handful
# of well-known non-member territories: a finite, stable, OFFICIALLY
# ENUMERATED set that does not grow between conversations. This list finishes.
#
# Unconditional like _NEVER_SCRUB above, not gated to the STATE label: a
# country name mislabelled CITY or LOCATION would break the same way, and a
# country is not sensitive personal data under any label the model might
# reach for.
_COUNTRY_NAMES = {
    "afghanistan", "albania", "algeria", "andorra", "angola",
    "antigua and barbuda", "argentina", "armenia", "australia", "austria",
    "azerbaijan", "bahamas", "bahrain", "bangladesh", "barbados", "belarus",
    "belgium", "belize", "benin", "bhutan", "bolivia",
    "bosnia and herzegovina", "botswana", "brazil", "brunei", "bulgaria",
    "burkina faso", "burundi", "cambodia", "cameroon", "canada",
    "cape verde", "central african republic", "chad", "chile", "china",
    "colombia", "comoros", "costa rica", "croatia", "cuba", "cyprus",
    "czechia", "czech republic", "denmark", "djibouti", "dominica",
    "dominican republic", "ecuador", "egypt", "el salvador",
    "equatorial guinea", "eritrea", "estonia", "eswatini", "ethiopia",
    "fiji", "finland", "france", "gabon", "gambia", "georgia", "germany",
    "ghana", "greece", "grenada", "guatemala", "guinea", "guinea-bissau",
    "guyana", "haiti", "honduras", "hungary", "iceland", "india",
    "indonesia", "iran", "iraq", "ireland", "israel", "italy", "jamaica",
    "japan", "jordan", "kazakhstan", "kenya", "kiribati", "kosovo",
    "kuwait", "kyrgyzstan", "laos", "latvia", "lebanon", "lesotho",
    "liberia", "libya", "liechtenstein", "lithuania", "luxembourg",
    "madagascar", "malawi", "malaysia", "maldives", "mali", "malta",
    "marshall islands", "mauritania", "mauritius", "mexico", "micronesia",
    "moldova", "monaco", "mongolia", "montenegro", "morocco", "mozambique",
    "myanmar", "namibia", "nauru", "nepal", "netherlands", "new zealand",
    "nicaragua", "niger", "nigeria", "north korea", "north macedonia",
    "norway", "oman", "pakistan", "palau", "palestine", "panama",
    "papua new guinea", "paraguay", "peru", "philippines", "poland",
    "portugal", "qatar", "romania", "russia", "rwanda",
    "saint kitts and nevis", "saint lucia",
    "saint vincent and the grenadines", "samoa", "san marino",
    "sao tome and principe", "saudi arabia", "senegal", "serbia",
    "seychelles", "sierra leone", "singapore", "slovakia", "slovenia",
    "solomon islands", "somalia", "south africa", "south korea",
    "south sudan", "spain", "sri lanka", "sudan", "suriname", "sweden",
    "switzerland", "syria", "taiwan", "tajikistan", "tanzania", "thailand",
    "timor-leste", "togo", "tonga", "trinidad and tobago", "tunisia",
    "turkey", "turkmenistan", "tuvalu", "uganda", "ukraine",
    "united arab emirates", "united kingdom", "united states", "uruguay",
    "uzbekistan", "vanuatu", "vatican city", "venezuela", "vietnam",
    "yemen", "zambia", "zimbabwe",
    # Short/common forms real people actually type, alongside the formal
    # name above. Deliberately NOT "us" or "uk" — both are common enough as
    # ordinary English words (the pronoun "us", the fragment "uk" inside
    # other tokens) that exempting the bare two letters risks more than the
    # country abbreviation is worth; "usa" and "uae" don't have that problem.
    "usa", "uae", "ivory coast", "cote d'ivoire",
    "democratic republic of congo", "republic of congo", "congo",
    "burma", "holland",
}

# Measured 2026-08-30, the same afternoon as the country list above: "write
# an essay about the history of the roman empire" scrubbed "roman empire" as
# STATE too, and the model asked whether it meant a US state. A historical
# empire is a different, wider category than a sovereign country — there is
# no UN list to lean on, and a genuinely complete set (every empire, kingdom,
# caliphate, dynasty a student might ask about) is not bounded the way
# _COUNTRY_NAMES is. This is deliberately NOT that: it is the handful most
# likely to come up in an ordinary conversation or homework question, not an
# attempt at completeness — closer in spirit to the greeting list this file
# argues against than to the country list above, kept small on purpose.
# Widen it if a specific miss is measured, the same way the country list grew
# from one real failure; don't pre-populate it further from a history
# syllabus.
_HISTORICAL_POLITY_NAMES = {
    "roman empire", "byzantine empire", "ottoman empire", "british empire",
    "persian empire", "mongol empire", "holy roman empire",
    "austro-hungarian empire", "russian empire", "han dynasty",
    "ming dynasty", "qing dynasty", "aztec empire", "inca empire",
    "ancient rome", "ancient greece", "ancient egypt",
}

# NO GREETING LIST LIVES HERE, AND ONE SHOULD NOT BE ADDED.
#
# The model labels "namaste" FIRSTNAME. The obvious patch is to list it, and
# that patch does not terminate — measured against this model, all of these
# are confident false positives too:
#
#   namaste 0.999   shukriya 0.999   dhanyavaad 0.998   yaar 0.995
#   hiya 0.999      bhai 0.994       salaam 0.934       ciao 0.999
#   hola 0.993      aloha 0.967      arigato 0.999      howdy 0.991
#
# That is one afternoon of guessing in two languages. The set is every
# greeting, interjection and loanword in every language a user might type,
# which is not a set anybody finishes enumerating.
#
# The two cheaper fixes do not work either, and it is worth recording why so
# they are not re-attempted:
#
#   A SCORE GATE CANNOT SEPARATE THEM. The spurious hits score 0.99+, which
#   is exactly where the real names score — "aniketh" 0.999, "priya" 0.998,
#   "sundar" 1.0. There is no threshold between the two populations because
#   the model is not uncertain; it is confidently wrong.
#
#   CAPITALISATION CANNOT EITHER. "Namaste" is clean while "namaste" is not,
#   which suggests keying on case — but "my name is aniketh" scores 0.999 on
#   a genuine name, and people type their own names in lowercase constantly.
#   Ignoring lowercase names would leak the commonest case of the exact thing
#   this module exists to catch.
#
# What is left is the model itself: this one is English-centric and treats an
# unfamiliar non-English token as a name. The real fix is a multilingual PII
# model, not a vocabulary bolted to an English one. Until then the behaviour
# is over-redaction, which the gate comment above already argues is the safe
# direction to fail in — a scrubbed greeting is rehydrated before the user
# sees the reply.
#
# `_is_word_fragment` below is deliberately NOT this. It removes a structural
# artefact of the tokenizer using a rule, and needs no vocabulary at all.


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
#
# IT IS NOT. That comment was true for English prose and false for everything
# else, because it compares a count of CHARACTERS against a limit measured in
# TOKENS. Measured, 1500 characters produces:
#
#     english prose   333 tokens   ok
#     devanagari     1000 tokens   2x over
#     code           1058 tokens   2x over
#     json           1429 tokens   2.8x over
#
# So the inputs most likely to carry a pasted secret — code, config, API
# payloads — are exactly the ones that overrun the window, and the overrun is
# silent: `_detect_spans` catches the failure, logs one warning and `continue`s
# to the next chunk, leaving only the regex backstop. The backstop has no
# pattern for names or cities, so those leak verbatim with the UI still
# reporting a clean scrub.
#
# Kept as the fallback bound for when the tokenizer is unavailable.
_CHUNK_SIZE = 1500

# Tokens per inference call. 448 of the model's 512 leaves room for the
# special tokens the pipeline adds, and for the overlap below.
_MAX_TOKENS = 448

# Windows overlap so an entity cannot be destroyed by falling across a cut.
# Measured before this existed: an email starting at char 1492 was detected as
# 'ianiketh@gmail.com' — the boundary ate "pan", and the three leading
# characters went to the provider in clear. 64 tokens is longer than any
# single entity this model emits, and the span merge in `_detect_spans`
# already coalesces the duplicates the overlap produces.
_OVERLAP_TOKENS = 64


def _token_windows(text: str) -> "list[tuple[int, str]]":
    """Split `text` into (char_offset, chunk) windows that fit the model.

    Divides on the tokenizer's own count rather than on character length, so
    the window is bounded by the thing the model actually limits. Falls back
    to fixed-size character slicing when no tokenizer is reachable, which is
    the old behaviour and still better than nothing.
    """
    tokenizer = getattr(_pipeline, "tokenizer", None)
    if tokenizer is None:
        return [(i, text[i:i + _CHUNK_SIZE])
                for i in range(0, len(text), _CHUNK_SIZE)]
    try:
        encoded = tokenizer(text, add_special_tokens=False,
                            return_offsets_mapping=True, truncation=False)
        offsets = [o for o in encoded["offset_mapping"] if o[1] > o[0]]
    except Exception:  # pragma: no cover - defensive
        return [(i, text[i:i + _CHUNK_SIZE])
                for i in range(0, len(text), _CHUNK_SIZE)]

    if not offsets:
        return []
    if len(offsets) <= _MAX_TOKENS:
        return [(0, text)]

    windows: list[tuple[int, str]] = []
    step = _MAX_TOKENS - _OVERLAP_TOKENS
    for i in range(0, len(offsets), step):
        piece = offsets[i:i + _MAX_TOKENS]
        if not piece:
            break
        start, end = piece[0][0], piece[-1][1]
        windows.append((start, text[start:end]))
        if i + _MAX_TOKENS >= len(offsets):
            break
    return windows


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


# Labels where the tokenizer's leftovers show up as "names". Scoped to these
# rather than applied to every label: an ACCOUNTNUMBER or a CREDITCARDNUMBER
# can legitimately sit inside a longer run of digits, and rejecting those for
# not aligning to a word boundary would be a leak.
_NAME_LABELS = {"FIRSTNAME", "LASTNAME", "MIDDLENAME"}


def _is_word_fragment(text: str, start: int, end: int) -> bool:
    """Whether a span is a piece of a word rather than a word.

    The SentencePiece tokenizer splits words into subwords, and the merge step
    above puts the pieces of a real name back together ("A"/"nike"/"th" ->
    "Aniketh"). What it cannot do is notice when the pieces never formed a name
    in the first place: the tail of an ordinary word arrives labelled
    FIRSTNAME, survives the merge alone, and gets redacted.

    Measured: "bye" -> ('e', FIRSTNAME), and "howdy, can you help me?" ->
    ('dy', FIRSTNAME). Neither is reachable from _NEVER_SCRUB, because that
    matches the span's own text and the span is "e", not "bye" — which is the
    argument against fixing this class with a word list at all. There is no
    finite list of words whose last two letters a tokenizer might mislabel.

    A real name occupies a whole word: the character before it and the
    character after it are not letters. A fragment is flanked by the rest of
    its word. That is the whole test, and it needs no vocabulary.

    Length is deliberately NOT the test. "Li", "Xi", "Wu" and "Bo" are real
    names, so a minimum-length rule would leak exactly the short names it was
    meant to be safe around.
    """
    before_is_letter = start > 0 and text[start - 1].isalpha()
    after_is_letter = end < len(text) and text[end].isalpha()
    return before_is_letter or after_is_letter


# Measured 2026-08-30 against a plain-language explanation of TCP slow start
# and a bridge-weight-limit analogy — no PII in either, both technical/teaching
# text. The model confidently (>=0.90, clean of the AGE/AMOUNT-style separation
# problem the comment above documents) mislabelled:
#
#   '1→2→4→8→16'        MAC              (a doubling sequence)
#   '32→33→34→...→48'   MASKEDNUMBER     (the SAME already-gated label —
#                                          the 0.90 gate does not save this)
#   '8.2', '8.'          IPV4            (steps in "8.1, 8.2, 8.3 tons")
#   '[1,2,4,8,16,32]'    NEARBYGPSCOORDINATE
#
# No score gate fixes this: per-label thresholds punish every real detection
# of that label equally, and these already sit above where a real MAC or GPS
# coordinate would. What actually distinguishes them is SHAPE, exactly the
# same argument _is_word_fragment makes: a real MAC is six colon/hyphen-joined
# hex pairs, a real IPv4 is four dot-joined octets, a real GPS pair is two
# comma-joined floats. None of those is a chain of THREE OR MORE numbers
# strung together with →, ->, or a bare comma — that shape is a step
# sequence, a version list, or an index list, in every language this model
# has been fed technical text in. Needs no vocabulary, same as the fragment
# check: it is asking what kind of thing the text next to the span looks
# like, not what language or domain it is in.
_NUMERIC_SEQUENCE_RE = re.compile(
    r'\d+(?:\.\d+)?(?:\s*(?:→|->|,)\s*\d+(?:\.\d+)?){2,}'
)


def _is_numeric_sequence_fragment(text: str, start: int, end: int) -> bool:
    """Whether a span sits inside a 3+-number chain (steps, versions, indices).

    Checked against a window around the span rather than the span alone,
    because the giveaway is the SEPARATOR pattern around it ('→', '->', ',')
    repeating three-plus times — a lone '8.2' cannot tell you that on its own,
    but '8.1, 8.2, 8.3' can.
    """
    window_start = max(0, start - 40)
    window_end = min(len(text), end + 40)
    window = text[window_start:window_end]
    for m in _NUMERIC_SEQUENCE_RE.finditer(window):
        m_start, m_end = window_start + m.start(), window_start + m.end()
        if m_start <= start and end <= m_end:
            return True
    return False


# Measured 2026-08-30, live: a create_workspace tool result echoed its own
# handle — 'ws_01a0515b846c7001abba5c4597054345' — into the transcript, and
# on the very next model call that got tagged and scrubbed as IBAN (score
# above the gate: a prefix word then a long alphanumeric run reads enough
# like an account number to fool the model). This is the one false-positive
# class in this file that does not just cost prompt clarity, it breaks a
# feature: update_workspace needs the SAME id back on a later turn, and a
# model that only ever sees §IBAN_1§ has no real id left — it has to
# invent one. Every id primnox2/ids.py and v2/ids.py mint is
# <prefix>_<hex>, a shape ordinary prose does not take by coincidence, so —
# same approach as the numeric-sequence check above — this is matched on
# shape, not by guessing at every entity label that might claim it.
_INTERNAL_ID_RE = re.compile(
    r'\b(?:conv|turn|msg|job|evt|ws|asset|node|edge|clus'
    r'|ent|rel|epi|mem|res|task|art|cred|aud|idx)_[0-9a-f]{16}(?:[0-9a-f]{16})?\b'
)


def _is_internal_id_fragment(text: str, start: int, end: int) -> bool:
    """Whether a span sits inside one of Primnox's own <prefix>_<hex> ids.

    Windowed for the same reason as _is_numeric_sequence_fragment: the model
    sometimes tags only part of the id (the hex tail, say), and the giveaway
    — the <prefix>_ before it — can sit outside a span that short.
    """
    window_start = max(0, start - 40)
    window_end = min(len(text), end + 40)
    window = text[window_start:window_end]
    for m in _INTERNAL_ID_RE.finditer(window):
        m_start, m_end = window_start + m.start(), window_start + m.end()
        if m_start <= start and end <= m_end:
            return True
    return False


# Audited 2026-08-30 against realistic conversation/technical/business text
# looking for the next AMOUNT-shaped defect (an ungated label misfiring on
# ordinary words). Found EYECOLOR and CREDITCARDISSUER both firing at 0.9+ on
# text that is neither — and neither has a usable score gate, unlike IPV6 or
# STREET above: 'the blue theme' (0.996) sits right next to 'my eyes are
# blue' (0.997), and 'Titan' as a project codename (0.923) sits ABOVE the
# real 'Mastercard' (0.567). A confidence threshold here would trade a false
# positive for a false negative — real PII missed — which this file's own
# stated priority says is strictly worse. Both get a DIFFERENT kind of
# check instead, matching what actually distinguishes them.
#
# EYECOLOR: this model tags color words generically, with no apparent
# sensitivity to what the color describes. What a real eye-color mention
# has that a paint job, a car or a UI theme does not is the word "eye"
# somewhere near it — the whole point of the label is that it is ABOUT
# eyes. Anchor-checked, not score-gated, same shape as the numeric-sequence
# and internal-id checks above: ask what is NEXT TO the span, not how
# confident the model was in the span alone.
_EYECOLOR_ANCHOR_RE = re.compile(r'\beyes?\b|\biris(?:es)?\b', re.IGNORECASE)


def _is_unanchored_eyecolor(text: str, start: int, end: int) -> bool:
    """Whether an EYECOLOR span has no "eye(s)"/"iris" nearby.

    Measured: 'she prefers the blue theme', 'paint the wall blue' and 'the
    car is red' all score 0.95-0.996 under this label with nothing eye-
    related in the sentence at all — the model appears to fire on the
    color word alone. 'my eyes are blue' / 'he has brown eyes' / 'her eyes
    are green' all name an eye within a few words, every time.
    """
    window_start = max(0, start - 30)
    window_end = min(len(text), end + 30)
    return not _EYECOLOR_ANCHOR_RE.search(text[window_start:window_end])


# CREDITCARDISSUER: unlike EYECOLOR, this is not a shape problem — it is
# that real card networks are a small, closed, well-known set, the same
# kind of thing that makes the country-names exemption above safe. The
# difference is direction: _COUNTRY_NAMES says "never scrub this text";
# this list says the opposite — CREDITCARDISSUER only means something when
# the matched text actually names one of these, so anything else under
# this label is treated as noise regardless of the model's confidence in
# it. New networks appear rarely enough (this list already covers the
# regional ones — RuPay, Elo, Mir, Troy) that missing one for a few months
# costs far less than "Titan"/"Merlin" reliably scoring as a bank brand.
_KNOWN_CARD_ISSUERS = {
    "visa", "mastercard", "master card", "american express", "amex",
    "discover", "diners club", "jcb", "unionpay", "union pay", "maestro",
    "rupay", "interac", "elo", "hipercard", "cartes bancaires", "verve",
    "troy", "mir", "bc card", "napas", "girocard",
}


def _is_unrecognised_card_issuer(text: str, start: int, end: int) -> bool:
    """Whether a CREDITCARDISSUER span's own text is not a real network name.

    Measured: a project codename ('Titan') scored 0.923 under this label —
    higher than the real 'Mastercard' (0.567) — so the score cannot tell
    them apart. The text itself can: 'Titan' is not a card network, no
    matter how confidently it was tagged as one.
    """
    return text[start:end].strip().lower() not in _KNOWN_CARD_ISSUERS


def _detect_spans(text: str) -> list[dict]:
    """Return non-overlapping PII spans [{start, end, label, text}] for `text`,
    using the DeBERTa model when ready, always backstopped by regex."""
    spans: list[dict] = []

    if _pipeline is not None:
        for i, chunk in _token_windows(text):
            try:
                entities = _pipeline(chunk)  # type: ignore[misc]
            except Exception as exc:
                # Still swallowed — a redactor that raises would cost the user
                # their turn — but no longer silent. This branch means the
                # model saw NOTHING for this window and only the regex
                # backstop applies to it, which has no pattern for names or
                # places. That is a leak, and it needs to be greppable.
                log.error("PII MODEL SKIPPED %d chars at offset %d (%s) — "
                          "names and places in this window were NOT redacted",
                          len(chunk), i, exc)
                continue
            # The score is CARRIED, not applied here. Gating a subword piece
            # before the merge below reassembles it decapitates the entity:
            # "pin 4432" arrives as PIN ' 44' (0.948) and PIN '32' (0.875),
            # the 0.90 gate drops the second piece, the merge has nothing left
            # to join, and the redaction covers "44" while "32" goes to the
            # provider in clear. The gate belongs on the whole entity — see
            # `_gate_of` after the merge.
            for e in entities:
                label = e.get("entity_group", "").upper()
                if label in _REDACT_LABELS:
                    s, en = i + e["start"], i + e["end"]
                    spans.append({"start": s, "end": en, "label": label,
                                  "text": text[s:en],
                                  "score": float(e.get("score") or 0.0)})

    # Regex backstop (also runs while the model loads — closes the startup gap
    # for the patterns it covers).
    for label, pattern in _REGEX_PATTERNS.items():
        for m in re.finditer(pattern, text):
            if label == "API_KEY" and m.groups():
                s, en = m.start(1), m.end(1)
            else:
                s, en = m.start(), m.end()
            # Score 1.0: a regex match is deterministic, so it is never the
            # thing a confidence gate should be second-guessing.
            spans.append({"start": s, "end": en, "label": label,
                          "text": text[s:en], "score": 1.0})

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
                # The entity is as confident as its most confident piece. Max
                # rather than mean: a trailing subword is routinely less certain
                # than the token that identified the entity ('44' 0.948 then
                # '32' 0.875), and averaging would let a long tail talk a real
                # detection back down below its gate.
                prev["score"] = max(prev["score"], sp["score"])
                continue
            if sp["end"] <= prev["end"]:
                continue  # fully covered by a different label — drop
            sp = {"start": prev["end"], "end": sp["end"], "label": sp["label"],
                  "score": sp["score"]}  # clip
        merged.append({"start": sp["start"], "end": sp["end"],
                       "label": sp["label"], "score": sp["score"]})

    out: list[dict] = []
    for sp in merged:
        s, en = sp["start"], sp["end"]
        while s < en and text[s].isspace():
            s += 1
        while en > s and text[en - 1].isspace():
            en -= 1
        if s >= en:
            continue
        span_text = text[s:en].strip().lower()
        if (span_text in _NEVER_SCRUB or span_text in _COUNTRY_NAMES
                or span_text in _HISTORICAL_POLITY_NAMES):
            continue
        # The gate, applied to the reassembled entity rather than to the
        # subword pieces it was built from.
        if sp["score"] < _NER_MIN_SCORE_BY_LABEL.get(sp["label"], _NER_MIN_SCORE):
            continue
        if sp["label"] in _NAME_LABELS and _is_word_fragment(text, s, en):
            continue
        if _is_numeric_sequence_fragment(text, s, en):
            continue
        if _is_internal_id_fragment(text, s, en):
            continue
        if sp["label"] == "EYECOLOR" and _is_unanchored_eyecolor(text, s, en):
            continue
        if sp["label"] == "CREDITCARDISSUER" and _is_unrecognised_card_issuer(text, s, en):
            continue
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
