#!/usr/bin/env python3
"""Privacy Mirror benchmark — measures what the product thesis rests on.

Primnox's core claim is "scrub locally, reason in the cloud". That claim has
never been measured, so this is the first number attached to it.

Metrics, per the threat model that actually matters:

  LEAK RATE   share of PII items that survive scrubbing and would reach the
              cloud provider verbatim. This is the number that matters — a leak
              is unrecoverable, an over-redaction is merely annoying.
  RECALL      share of PII items redacted (1 - leak rate, per item).
  PRECISION   share of redactions that were real PII. Low precision means the model
              is shredding ordinary text, which degrades answer quality.
  ROUNDTRIP   whether rehydration restores the original text exactly. A failure
              here means the user sees corrupted output.

Run:  ./.venv/bin/python bench_scrubber.py
"""
from __future__ import annotations
import re, sys, time, json

# (text, [pii substrings that MUST be redacted], [substrings that must SURVIVE])
CORPUS: list[tuple[str, list[str], list[str]]] = [
    # ── direct identifiers ────────────────────────────────────────────────
    # Fictional throughout — a PII benchmark must never carry real PII itself.
    ("My name is Marcus Vetrov and my email is marcus.vetrov@example.net",
     ["Marcus", "Vetrov", "marcus.vetrov@example.net"], ["email"]),
    ("Contact me at +91 98765 43210 or on john.doe@example.co.uk",
     ["+91 98765 43210", "john.doe@example.co.uk"], ["Contact"]),
    ("Ship it to 221B Baker Street, London, NW1 6XE",
     ["221B", "Baker Street", "London", "NW1 6XE"], ["Ship it to"]),
    ("My SSN is 123-45-6789 and my DOB is 12/03/1998",
     ["123-45-6789", "12/03/1998"], ["SSN"]),

    # ── financial ─────────────────────────────────────────────────────────
    ("Card 4111 1111 1111 1111 exp 04/27 cvv 921",
     ["4111 1111 1111 1111"], ["exp"]),
    ("Wire it to IBAN GB33BUKB20201555555555 please",
     ["GB33BUKB20201555555555"], ["Wire it to"]),

    # ── secrets / infra ───────────────────────────────────────────────────
    ("export API_KEY=sk_live_51H8xQ2eZvKYlo2CabcdefghijklmnopQ",
     ["sk_live_51H8xQ2eZvKYlo2CabcdefghijklmnopQ"], ["export"]),
    ("ssh into 192.168.1.104 with password hunter2murmur99",
     ["192.168.1.104"], ["ssh into"]),
    ("The server at 10.0.0.53 keeps refusing connections",
     ["10.0.0.53"], ["refusing connections"]),

    # ── mixed prose (the realistic case) ───────────────────────────────────
    ("Hey, I'm Sarah Chen from Acme Corp — can you draft a reply to "
     "mike@acme.io about the Q3 numbers?",
     ["Sarah", "Chen", "mike@acme.io"], ["draft a reply", "Q3 numbers"]),
    ("Book a meeting with Dr. Patel at St Mary's Hospital on Tuesday",
     ["Patel"], ["Book a meeting", "Tuesday"]),

    # ── negative controls: NO pii, nothing should be redacted ─────────────
    ("Explain the difference between a mutex and a semaphore", [],
     ["mutex", "semaphore", "difference"]),
    ("Write a python function that reverses a linked list", [],
     ["python", "linked list", "reverses"]),
    ("What is the time complexity of quicksort in the worst case?", [],
     ["quicksort", "time complexity", "worst case"]),
    ("Summarise the main arguments for and against rent control", [],
     ["rent control", "arguments"]),
    ("Fix this error: TypeError cannot read property map of undefined", [],
     ["TypeError", "undefined", "map"]),
]

PLACEHOLDER = re.compile(r'§[A-Z_]+_\d+§|\[REDACTED[^\]]*\]|<[A-Z_]+_\d+>')


def main() -> int:
    import privacy_mirror as pm

    print("Loading PII model (DeBERTa NER)…", flush=True)
    t0 = time.time()
    pm.start_model_loading()
    ready = pm.ensure_model_ready(timeout=180.0)
    load_s = time.time() - t0
    print(f"model_status={pm.model_status()}  ready={ready}  load={load_s:.1f}s\n")
    if not ready:
        print("!! Model not ready — the numbers below reflect the REGEX FALLBACK only.")
        print("   That is the path used during the first seconds after launch.\n")

    total_pii = caught_pii = 0
    leaks: list[tuple[str, str]] = []
    false_pos: list[tuple[str, str]] = []
    roundtrip_fail: list[str] = []

    for text, must_redact, must_survive in CORPUS:
        session = pm.ScrubSession()
        scrubbed = session.scrub(text)

        for item in must_redact:
            total_pii += 1
            if item.lower() in scrubbed.lower():
                leaks.append((item, scrubbed))
            else:
                caught_pii += 1

        for item in must_survive:
            if item.lower() not in scrubbed.lower():
                false_pos.append((item, scrubbed))

        # Rehydration must reproduce the input exactly.
        if session.rehydrate(scrubbed) != text:
            roundtrip_fail.append(text)

    leaked = len(leaks)
    recall = caught_pii / total_pii if total_pii else 1.0
    leak_rate = leaked / total_pii if total_pii else 0.0

    print("=" * 68)
    print(f"{'PII items':<22}{total_pii}")
    print(f"{'redacted':<22}{caught_pii}")
    print(f"{'LEAKED':<22}{leaked}")
    print(f"{'recall':<22}{recall:6.1%}")
    print(f"{'LEAK RATE':<22}{leak_rate:6.1%}")
    print(f"{'over-redactions':<22}{len(false_pos)}")
    print(f"{'rehydration failures':<22}{len(roundtrip_fail)} / {len(CORPUS)}")
    print("=" * 68)

    if leaks:
        print("\nLEAKED (would reach the cloud verbatim):")
        for item, out in leaks:
            print(f"  ✗ {item!r}\n      -> {out[:95]}")
    if false_pos:
        print("\nOVER-REDACTED (ordinary text destroyed):")
        for item, out in false_pos[:12]:
            print(f"  ! {item!r}\n      -> {out[:95]}")
    if roundtrip_fail:
        print("\nREHYDRATION FAILURES (user sees corrupted output):")
        for t in roundtrip_fail[:6]:
            print(f"  ✗ {t[:80]}")

    return 1 if leaked else 0


if __name__ == "__main__":
    sys.exit(main())
