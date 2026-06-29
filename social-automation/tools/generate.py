#!/usr/bin/env python
"""Primnox social video factory — script -> voiceover + word-synced captions + caption pack.

Usage:
    python tools/generate.py <slug>

Reads:  content/scripts/<slug>.md
Writes: public/render/<slug>/audio.mp3      (edge-tts voiceover, free, no API key)
        public/render/<slug>/captions.json  (Remotion Caption[] with word-level timing)
        public/render/<slug>/meta.json       (title, hook, cta, duration, ...)
        public/render/<slug>/props.json      ({"slug": ...} for `remotion render`)
        out/<slug>.captions.md               (copy-paste caption pack for every platform)

The Remotion side reads meta.json + captions.json to render the video.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "content" / "scripts"
RENDER = ROOT / "public" / "render"
OUT = ROOT / "out"

# Defaults (override per-script in front-matter)
DEFAULTS = {
    "voice": "en-US-AndrewNeural",   # warm, modern male. See README for alternatives.
    "title": "Primnox",
    "link": "primnox.github.io",
    "handle": "@primnox",
    "music": "",                     # filename in public/music/ (optional)
    "rate": "+6%",                   # slightly punchy for short-form
    "pitch": "+0Hz",
}

# Hashtags appended to every platform on top of any `hashtags_extra` from the script.
BASE_TAGS = [
    "Primnox", "privacy", "privacyfirst", "localAI", "ownyourdata",
    "AItools", "buildinpublic", "indiehacker", "techtok",
]


# --------------------------------------------------------------------------- #
# Script parsing
# --------------------------------------------------------------------------- #
def parse_script(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    meta = dict(DEFAULTS)
    body = raw

    # Front-matter between leading `---` fences
    fm = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)
    if fm:
        for line in fm.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            if val.startswith("[") and val.endswith("]"):
                meta[key] = [v.strip().lstrip("#") for v in val[1:-1].split(",") if v.strip()]
            else:
                meta[key] = val.strip().strip('"').strip("'")
        body = fm.group(2)

    # Body -> blocks (blank-line separated). Each block is a caption "beat".
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]

    hook, cta = "", ""
    spoken_blocks = []
    for b in blocks:
        tag = re.match(r"^\[(\w+)\]\s*(.*)$", b, re.DOTALL)
        text = b
        label = ""
        if tag:
            label = tag.group(1).lower()
            text = tag.group(2).strip()
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if label == "hook" and not hook:
            hook = text
        if label == "cta":
            cta = text
        spoken_blocks.append(text)

    if not hook and spoken_blocks:
        hook = spoken_blocks[0]
    if not cta and spoken_blocks:
        cta = spoken_blocks[-1]

    # Narration the TTS will speak: every block, each ended with sentence punctuation
    # so edge-tts inserts natural pauses between beats.
    def punct(t: str) -> str:
        return t if t[-1] in ".!?:" else t + "."
    narration = " ".join(punct(b) for b in spoken_blocks)

    meta["hook"] = hook
    meta["cta"] = cta
    meta["narration"] = narration
    meta["blocks"] = spoken_blocks
    return meta


# --------------------------------------------------------------------------- #
# Text-to-speech + word-level captions (edge-tts, free)
# --------------------------------------------------------------------------- #
def _split_sentence(text: str, start_ms: float, dur_ms: float):
    """Spread a sentence's words across its [start, start+dur] window, weighted by
    word length. edge-tts only reports sentence-level timing now, so this anchors
    every word to a real sentence boundary and interpolates within it."""
    words = text.split()
    if not words:
        return []
    weights = [len(w) + 1 for w in words]  # +1 ≈ inter-word gap
    total = sum(weights)
    out, acc = [], 0.0
    for w, weight in zip(words, weights):
        w_start = start_ms + dur_ms * (acc / total)
        acc += weight
        w_end = start_ms + dur_ms * (acc / total)
        out.append({
            "text": " " + w,                      # leading space (whitespace-sensitive)
            "startMs": round(w_start),
            "endMs": round(w_end),
            "timestampMs": round((w_start + w_end) / 2),
            "confidence": 1,
        })
    return out


async def synth(text: str, voice: str, rate: str, pitch: str):
    """Return (mp3_bytes, captions) where captions is a Remotion Caption[]."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    audio = bytearray()
    captions = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "SentenceBoundary":
            start_ms = chunk["offset"] / 10000.0   # 100ns units -> ms
            dur_ms = chunk["duration"] / 10000.0
            captions.extend(_split_sentence(chunk["text"], start_ms, dur_ms))
    return bytes(audio), captions


# --------------------------------------------------------------------------- #
# Caption pack (copy-paste, per platform)
# --------------------------------------------------------------------------- #
def tags(meta: dict, n: int) -> str:
    extra = meta.get("hashtags_extra") or []
    seen, ordered = set(), []
    for t in list(extra) + BASE_TAGS:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            ordered.append("#" + t)
    return " ".join(ordered[:n])


def caption_pack(meta: dict) -> str:
    hook = meta["hook"]
    cta = meta["cta"]
    link = meta["link"]
    handle = meta["handle"]
    body = " ".join(meta["blocks"][1:-1]) if len(meta["blocks"]) > 2 else cta

    tiktok = f"{hook}\n\n{cta}\nTry it free → {link}\n\n{tags(meta, 5)}"
    insta = f"{hook}\n\n{body}\n\n{cta}\n🔗 {link} (link in bio)\n\n{tags(meta, 12)}"
    x = f"{hook}\n\n{cta}\n→ {link}\n\n{tags(meta, 3)}"
    linkedin = (
        f"{hook}\n\n{body}\n\n{cta}\n\n"
        f"Building it in the open. Try it → {link}\n\n{tags(meta, 3)}"
    )

    return f"""# Caption pack — {meta['title']}

> Generated by the Primnox video factory. Copy-paste per platform. Tweak before posting.
> Handle: {handle} · Link: {link}

---

## TikTok / Reels / Shorts
```
{tiktok}
```

## Instagram (feed / carousel)
```
{insta}
```

## X (Twitter)
```
{x}
```
_({len(x)} characters)_

## LinkedIn
```
{linkedin}
```
"""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "example"
    script = SCRIPTS / f"{slug}.md"
    if not script.exists():
        sys.exit(f"[generate] Script not found: {script}\n"
                 f"           Create it, e.g. content/scripts/{slug}.md")

    print(f"[generate] Parsing {script.relative_to(ROOT)}")
    meta = parse_script(script)
    print(f"[generate] Voice: {meta['voice']}  ·  ~{len(meta['narration'].split())} words")

    print("[generate] Synthesizing voiceover with edge-tts ...")
    audio, captions = asyncio.run(
        synth(meta["narration"], meta["voice"], meta["rate"], meta["pitch"])
    )
    if not captions:
        sys.exit("[generate] No word timings returned — check the voice name / network.")

    duration_sec = captions[-1]["endMs"] / 1000.0

    dest = RENDER / slug
    dest.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    (dest / "audio.mp3").write_bytes(audio)
    (dest / "captions.json").write_text(json.dumps(captions, indent=2), encoding="utf-8")

    out_meta = {
        "slug": slug,
        "title": meta["title"],
        "hook": meta["hook"],
        "cta": meta["cta"],
        "voice": meta["voice"],
        "link": meta["link"],
        "handle": meta["handle"],
        "music": meta.get("music", ""),
        "durationSec": round(duration_sec, 3),
        "wordCount": len(captions),
    }
    (dest / "meta.json").write_text(json.dumps(out_meta, indent=2), encoding="utf-8")
    (dest / "props.json").write_text(json.dumps({"slug": slug}), encoding="utf-8")
    (OUT / f"{slug}.captions.md").write_text(caption_pack(meta), encoding="utf-8")

    print(f"[generate] Voiceover: {duration_sec:0.1f}s  ·  {len(captions)} captions")
    print(f"[generate] Wrote assets -> {dest.relative_to(ROOT)}")
    print(f"[generate] Caption pack -> out/{slug}.captions.md")
    print(f"[generate] Done. Render with:  npm run make -- {slug}")


if __name__ == "__main__":
    main()
