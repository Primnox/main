# Primnox Social Video Factory 🎬

Faceless, on-brand vertical videos for Primnox — **you write a script, it produces the rest.**

One script in → a finished `1080×1920` video (AI voiceover + word-synced captions + Primnox
branding) **and** a copy-paste caption pack for **TikTok / Reels / Shorts / X / LinkedIn** out.
You post.

No camera, no face, no paid APIs. Voiceover is [edge-tts](https://github.com/rany2/edge-tts)
(free Microsoft neural voices); video is rendered with [Remotion](https://remotion.dev).

---

## TL;DR

```bash
# 1. Write a script  ->  content/scripts/my-clip.md   (copy example.md)
# 2. Make the video:
npm run make -- my-clip
# 3. Grab the files:
#      out/my-clip.mp4            <- upload this
#      out/my-clip.captions.md    <- copy the caption for each platform
```

That's it. Everything below is detail.

---

## One-time setup

Already done in this repo, but if you clone fresh:

```bash
cd social-automation
npm install
pip install edge-tts        # free TTS, no API key
```

Requires Node 18+, Python 3.9+, and FFmpeg on PATH (Remotion bundles its own too).

---

## Writing a script

Scripts live in `content/scripts/<slug>.md`. Copy [`example.md`](content/scripts/example.md).

```markdown
---
title: Your AI is selling you out          # overlay/caption-pack title
voice: en-US-AndrewNeural                  # see "Voices" below
handle: "@primnox"
link: primnox.github.io
hashtags_extra: [localfirst, dataprivacy]  # added on top of the base set
music: ""                                  # optional file in public/music/
---

[hook] Your AI assistant reads everything you type.

And most of them ship it straight to a server you will never see.

Primnox flips that. A small model on your machine scrubs your data first.

[cta] Primnox. The AI that actually gives a damn.
```

Rules:

- **Blank line = a new beat.** Each paragraph becomes its own caption segment.
- **`[hook]`** marks the opener (also used as the first line of every caption).
- **`[cta]`** marks the closer (shown big on the end card).
- The whole body is what gets spoken. Keep it tight — **20–35s (≈55–90 words)** is the sweet
  spot for short-form. Write like you talk.

Front-matter is optional; sensible defaults live in `tools/generate.py`.

---

## Commands

| Command | What it does |
|---|---|
| `npm run make -- <slug>` | Full pipeline: voiceover + captions + **render mp4** + caption pack. |
| `npm run generate -- <slug>` | Just the assets (voiceover, captions, caption pack) — no render. |
| `npm run dev` | Open Remotion Studio to preview/tweak `<slug>` visually (set the slug in the props panel). |

Outputs land in:

- `out/<slug>.mp4` — the video to upload
- `out/<slug>.captions.md` — captions + hashtags per platform
- `public/render/<slug>/` — intermediate assets (voiceover, captions JSON); safe to delete/regenerate

---

## Voices

`edge-tts` voices are free. Set `voice:` in the front-matter. Good picks for Primnox:

| Voice | Vibe |
|---|---|
| `en-US-AndrewNeural` | Warm, modern, confident (default) |
| `en-US-BrianNeural` | Casual, friendly |
| `en-US-AvaNeural` | Natural, upbeat female |
| `en-US-EmmaNeural` | Soft, approachable female |
| `en-GB-RyanNeural` | British, crisp |

Full list: `python -m edge_tts --list-voices`.

> Caption timing is anchored to edge-tts **sentence** boundaries, and word timings are
> interpolated within each sentence — accurate enough that highlighting tracks the voice
> closely. Keep sentences punchy and it stays tight.

---

## Music (optional)

Drop a royalty-free track in `public/music/` (e.g. `public/music/ambient.mp3`) and set
`music: ambient.mp3` in the script. It mixes in low under the voice. **Don't commit copyrighted
audio** — `public/music/` is gitignored. Sources: YouTube Audio Library, Pixabay, Uppbeat.

---

## Customizing the look

All brand tokens (Primnox colors + fonts) are in [`src/theme.ts`](src/theme.ts):
bg `#070707`, lavender `#c3c0ff`, warm `#ffb695`, green `#34d399`; Syne / DM Sans / JetBrains Mono.

Visual pieces, each editable on its own:

- `src/components/Background.tsx` — animated gradient + grid
- `src/components/Captions.tsx` — TikTok-style captions + word highlight
- `src/components/Watermark.tsx` — logo + handle lockup
- `src/components/Outro.tsx` — end card (logo + CTA + link)
- `src/components/ProgressBar.tsx` — bottom progress bar
- `src/Video.tsx` — how it's all composed

Run `npm run dev` to preview changes live before rendering.

---

## How it works

```
content/scripts/<slug>.md
        │  tools/generate.py  (parse -> edge-tts -> word timings)
        v
public/render/<slug>/{audio.mp3, captions.json, meta.json, props.json}
        │  Remotion render (src/Video.tsx, calculateMetadata reads the JSON)
        v
out/<slug>.mp4   +   out/<slug>.captions.md
```

Duration, captions, hook and CTA are all derived from the script automatically — change the
script, re-run `npm run make`, get a new video.
