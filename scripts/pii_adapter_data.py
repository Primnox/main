"""Build a romanised-Hindi PII corpus for the privacy-mirror adapter.

WHY THIS EXISTS. The shipped detector labels `namaste` FIRSTNAME at 0.999 —
and `shukriya`, `dhanyavaad`, `yaar`, `bhai`, `arigato` with it. It is an
English-first model, and an unfamiliar Latin-script token looks like a name to
it. None of the fixes that do not require training work:

  a word list      does not terminate — the set is every greeting, interjection
                   and loanword in every language a user might type
  a score gate     cannot separate them — the false positives score 0.99+, the
                   same place real names score
  a capital letter cannot either — "my name is aniketh" is lowercase and real

What is left is teaching the model, and the tokenizer already permits it:
measured, Devanagari, Japanese and Chinese all tokenize with ZERO [UNK]. The
vocabulary can represent these words; the weights just have no idea what they
are.

WHY TRANSLITERATION RATHER THAN A HAND-WRITTEN CORPUS. ai4privacy ships Hindi
PII data, but in Devanagari — and the failures are romanised Hindi in LATIN
script, which no public dataset declares (there is `hi`, there is no
`hi-Latn`). The rows are unusually well suited to closing that gap: the PII
values are ALREADY Latin ("Nerio Uluçesme", "PL@outlook.com") while the
surrounding sentence is Devanagari. So transliterating only the context, and
leaving the PII exactly as it is, produces precisely the shape the model gets
wrong: a real Latin-script name surrounded by romanised Hindi that is not one.

The spans survive because the substitution is done segment by segment and the
offsets are recomputed from the rebuilt string, never carried over.

Usage:
    python scripts/pii_adapter_data.py --rows 6000 --out data/pii_adapter.jsonl
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# ai4privacy's label names -> the shipped model's. Anything absent from this
# map is a label the model has no head for; a row containing one is DROPPED
# rather than relabelled O, because teaching "this is not PII" about real PII
# is the one mistake this corpus must not make.
LABEL_MAP = {
    "GIVENNAME": "FIRSTNAME", "SURNAME": "LASTNAME", "MIDDLENAME": "MIDDLENAME",
    "TITLE": "PREFIX", "CITY": "CITY", "STREET": "STREET", "STATE": "STATE",
    "COUNTY": "COUNTY", "ZIPCODE": "ZIPCODE", "BUILDINGNUM": "BUILDINGNUMBER",
    "SECONDARYADDRESS": "SECONDARYADDRESS", "EMAIL": "EMAIL",
    "TELEPHONENUM": "PHONENUMBER", "USERNAME": "USERNAME", "PASSWORD": "PASSWORD",
    "DATE": "DATE", "TIME": "TIME", "DOB": "DOB", "AGE": "AGE", "GENDER": "GENDER",
    "SEX": "SEX", "IDCARDNUM": "IDCARD", "SOCIALNUM": "SSN", "TAXNUM": "TAXNUM",
    "ACCOUNTNUM": "ACCOUNTNUMBER", "ACCOUNTNAME": "ACCOUNTNAME",
    "CREDITCARDNUMBER": "CREDITCARDNUMBER", "CREDITCARDCVV": "CREDITCARDCVV",
    "CREDITCARDISSUER": "CREDITCARDISSUER", "IP": "IP", "IPV4": "IPV4",
    "IPV6": "IPV6", "MAC": "MAC", "URL": "URL", "COMPANYNAME": "COMPANYNAME",
    "JOBTITLE": "JOBTITLE", "JOBAREA": "JOBAREA", "JOBTYPE": "JOBTYPE",
    "CURRENCY": "CURRENCY", "AMOUNT": "AMOUNT", "PIN": "PIN", "BIC": "BIC",
    "IBAN": "IBAN", "EYECOLOR": "EYECOLOR", "HEIGHT": "HEIGHT",
    "VEHICLEVIN": "VEHICLEVIN", "VEHICLEVRM": "VEHICLEVRM",
}

# ── romanisation ──────────────────────────────────────────────────────────────
# ITRANS marks long vowels with capitals ("yAra", "bhAI", "dhanyavAda"), which
# is a transliteration convention and not how anybody types. Two variants are
# emitted per sentence rather than one "correct" spelling, because the spread
# is the point: real users write both "yar" and "yaar", and an adapter trained
# on a single spelling learns that spelling instead of the language.
_LONG = {"A": "aa", "I": "ii", "U": "uu", "R^i": "ri", "R^I": "rii",
         "lR^i": "lri", "E": "e", "O": "o"}
_RETRO = {"T": "t", "Th": "th", "D": "d", "Dh": "dh", "N": "n", "S": "sh",
          "Sh": "sh", "M": "n", "H": "h", "~n": "n", "~N": "n", "ch": "ch"}


def _casualise(text: str, *, doubled: bool) -> str:
    """ITRANS output -> something a person would actually type."""
    for src, dst in _LONG.items():
        text = text.replace(src, dst if doubled else dst[0])
    for src, dst in _RETRO.items():
        text = text.replace(src, dst)
    text = text.lower()
    text = re.sub(r"([aeiou])\1{2,}", r"\1\1", text)   # no aaa
    text = text.replace("aai", "ai").replace("aau", "au")
    # Final-schwa deletion. Hindi drops it and romanisation follows: the ITRANS
    # for यार is "yAra", and nobody writes the trailing a.
    text = re.sub(r"(?<=[bcdfghjklmnpqrstvwxyz])a\b", "", text)
    return text


def romanise(text: str, *, doubled: bool) -> str:
    return _casualise(transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS),
                      doubled=doubled)


# ── hard negatives ────────────────────────────────────────────────────────────
# The words measured as false positives, plus a wider set of the same KIND, in
# contexts that vary the position and the neighbours. These are the specific
# failures; the transliterated corpus above is what generalises beyond them.
HARD_NEGATIVES = [
    "namaste", "namaskar", "shukriya", "dhanyavaad", "yaar", "bhai", "behen",
    "acha", "theek hai", "arre", "chalo", "bas", "kya", "haan", "nahi",
    "arigato", "konnichiwa", "sayonara", "ciao", "hola", "gracias", "merci",
    "salaam", "shalom", "aloha", "hiya", "howdy", "sup", "oye", "abey",
    "matlab", "waise", "phir", "bilkul", "zaroor", "shabash", "wah",
]

NEGATIVE_TEMPLATES = [
    "{w}, how are you today?",
    "{w} — can you help me with this?",
    "just wanted to say {w}",
    "{w} {w}, that worked perfectly",
    "ok {w}, let's move on",
    "I said {w} and nothing happened",
    "{w}! this is exactly what I needed",
    "hey, {w}. quick question about the build",
    "he replied {w} and closed the ticket",
    "{w} for the help yesterday",
]

# Names must survive the training that teaches greetings are not names, so the
# same templates are emitted with real given names and a FIRSTNAME label. Short
# ones are deliberate: "Li", "Xi", "Wu" and "Bo" are the cases a naive
# length-based rule would leak.
POSITIVE_NAMES = [
    "Aniketh", "Priya", "Rahul", "Sundar", "Meera", "Arjun", "Kavya",
    "Li", "Xi", "Wu", "Bo", "Jo", "Al", "Ed",
    "Aditya", "Ishaan", "Ananya", "Rohan", "Neha", "Vikram", "Sneha",
]

POSITIVE_TEMPLATES = [
    "my name is {w}",
    "{w} sent me the report yesterday",
    "please cc {w} on that thread",
    "I spoke to {w} about the migration",
    "{w} is joining the call at four",
    "ask {w} to review the change",
    "this was {w}'s idea originally",
]


def _synthetic(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    for word in HARD_NEGATIVES:
        for template in rng.sample(NEGATIVE_TEMPLATES, k=4):
            text = template.format(w=word)
            rows.append({"text": text, "spans": [], "kind": "hard_negative"})
    for name in POSITIVE_NAMES:
        for template in rng.sample(POSITIVE_TEMPLATES, k=4):
            text = template.format(w=name)
            start = text.index(name)
            rows.append({"text": text,
                         "spans": [{"start": start, "end": start + len(name),
                                    "label": "FIRSTNAME"}],
                         "kind": "name_positive"})
    # A greeting IMMEDIATELY before a real name is the case most likely to be
    # broken by teaching greetings are safe: the model must keep the name.
    for word in HARD_NEGATIVES[:14]:
        for name in rng.sample(POSITIVE_NAMES, k=2):
            text = f"{word} {name}, are we still on for tomorrow?"
            start = text.index(name)
            rows.append({"text": text,
                         "spans": [{"start": start, "end": start + len(name),
                                    "label": "FIRSTNAME"}],
                         "kind": "greeting_then_name"})
    return rows


def _transliterated_row(row: dict, *, doubled: bool) -> dict | None:
    """Romanise the Devanagari context, keep the PII values byte-for-byte."""
    text = row.get("source_text") or ""
    mask = row.get("privacy_mask") or []
    if isinstance(mask, str):
        try:
            mask = json.loads(mask.replace("'", '"'))
        except Exception:
            return None
    if not text or not mask:
        return None

    spans = sorted(({"start": int(m["start"]), "end": int(m["end"]),
                     "label": LABEL_MAP.get(str(m["label"]).upper())}
                    for m in mask), key=lambda s: s["start"])
    if any(s["label"] is None for s in spans):
        return None  # unmappable label — see LABEL_MAP

    out: list[str] = []
    new_spans: list[dict] = []
    cursor = 0
    for span in spans:
        gap = text[cursor:span["start"]]
        out.append(romanise(gap, doubled=doubled) if DEVANAGARI.search(gap) else gap)
        start = sum(len(p) for p in out)
        value = text[span["start"]:span["end"]]
        out.append(value)
        new_spans.append({"start": start, "end": start + len(value),
                          "label": span["label"], "value": value})
        cursor = span["end"]
    tail = text[cursor:]
    out.append(romanise(tail, doubled=doubled) if DEVANAGARI.search(tail) else tail)

    rebuilt = "".join(out)
    # Every recomputed span must still cut out exactly the value it was built
    # from. A corpus whose offsets have slipped is worse than no corpus: it
    # trains the model to redact the character before a name and leave the
    # name, which is the failure this whole exercise is trying to remove.
    for span in new_spans:
        if rebuilt[span["start"]:span["end"]] != span["value"]:
            return None
        del span["value"]
    return {"text": rebuilt, "spans": new_spans, "kind": "translit"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=6000, help="Hindi rows to scan for")
    ap.add_argument("--out", default="data/pii_adapter.jsonl")
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    from datasets import load_dataset
    stream = load_dataset("ai4privacy/open-pii-masking-500k-ai4privacy",
                          split="train", streaming=True)

    rows: list[dict] = []
    scanned = kept = 0
    for record in stream:
        scanned += 1
        if str(record.get("language", "")).lower() != "hi":
            if scanned > 400_000:
                break
            continue
        for doubled in (False, True):
            built = _transliterated_row(record, doubled=doubled)
            if built:
                rows.append(built)
                kept += 1
        if kept >= args.rows:
            break
        if scanned % 25_000 == 0:
            print(f"  scanned {scanned:,} rows, kept {kept:,}", flush=True)

    synthetic = _synthetic(rng)
    rows.extend(synthetic)
    rng.shuffle(rows)

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    from collections import Counter
    kinds = Counter(r["kind"] for r in rows)
    print()
    print("wrote %d rows -> %s" % (len(rows), out_path))
    for kind, n in kinds.most_common():
        print("   %-18s %d" % (kind, n))
    print()
    print("samples:")
    for r in rows[:4]:
        print("   [%s] %r" % (r["kind"], r["text"][:110]))
        for s in r["spans"][:3]:
            print("        %-12s %r" % (s["label"], r["text"][s["start"]:s["end"]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
