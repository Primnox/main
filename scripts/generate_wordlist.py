#!/usr/bin/env python3
"""
Generate website/wordlist.txt from the canonical BIP-39 English wordlist.
Run once before deploying seed.primnox.com:

    python scripts/generate_wordlist.py
"""
import sys
import urllib.request
from pathlib import Path

FALLBACK_URL = (
    "https://raw.githubusercontent.com/trezor/python-mnemonic"
    "/master/src/mnemonic/wordlist/english.txt"
)

OUT_PATH = Path(__file__).parent.parent / "website" / "wordlist.txt"


def load_words() -> list[str]:
    try:
        from mnemonic import Mnemonic
        words = Mnemonic("english").wordlist
        print("Source: mnemonic library")
        return list(words)
    except ImportError:
        pass

    print(f"mnemonic not installed — fetching from {FALLBACK_URL}")
    with urllib.request.urlopen(FALLBACK_URL, timeout=10) as r:
        raw = r.read().decode("utf-8")
    return [w.strip() for w in raw.splitlines() if w.strip() and not w.startswith("#")]


def main() -> None:
    words = load_words()
    if len(words) != 2048:
        print(f"ERROR: expected 2048 words, got {len(words)}", file=sys.stderr)
        sys.exit(1)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(words) + "\n", encoding="utf-8")
    print(f"OK: {len(words)} words -> {OUT_PATH}")


if __name__ == "__main__":
    main()
