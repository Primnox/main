# Contributing to Primnox

Thank you — Primnox gets better every time someone files a bug, sketches an
idea, or sends a patch. This guide covers how to help.

## Ground rules

- **Be cool.** Primnox has a personality — sharp, helpful, roasts back, but
  never a jerk. Contributors should match: direct and kind, no gatekeeping.
- **Privacy is the product.** Primnox is local-first and scrubs PII *before*
  anything ever reaches a cloud model (the Privacy Mirror). Any change that
  weakens those guarantees needs a very good reason. When in doubt, keep the
  data on the user's machine.

## Ways to contribute

- **Found a bug?** Open an issue with repro steps, your Windows version, and any
  relevant logs.
- **Have an idea?** Open a discussion or feature-request issue *first* so we can
  shape it before you build it.
- **Want to code?** Comment on an issue to claim it (look for `good first
  issue`), then open a PR.

## Project layout

Primnox is an **Electron + React/TypeScript** frontend talking to a **Python
(FastAPI)** backend.

```
backend/    # FastAPI server, AI routing, skills, Privacy Mirror, memory, DBs
frontend/   # Electron app + React UI (Vite)
```

## Dev setup (Windows)

```bash
# Backend  — serves on http://localhost:4009
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python server.py

# Frontend — Electron dev build
cd frontend
npm install
npm run dev
```

Local inference runs through Ollama / llama.cpp; cloud providers (Groq, OpenAI,
Anthropic, Gemini) are optional and always go through the Privacy Mirror first.

## Pull requests

1. Fork, then branch off `main` (`feat/...` or `fix/...`).
2. Keep each PR focused on one logical change.
3. Make sure touched Python files pass `python -m py_compile`, and that the app
   still launches.
4. Explain *what* changed and *why*. Screenshots or GIFs for UI changes are
   gold.
5. **Sign the CLA** — add the agreement line from [CLA.md](CLA.md) to your first
   PR description. One time only.

## Licensing & the CLA — why we ask

Primnox uses the **Business Source License 1.1**, which automatically converts
to the **GNU AGPL v3.0** on **2029-06-30**. By contributing you agree your work
is licensed under those terms **and** you grant the maintainer the rights in
[CLA.md](CLA.md) — including the right to offer paid commercial licenses.

In plain terms: Primnox is **free for individuals and non-commercial use**, and
no company can use it commercially without a paid license until it becomes fully
open source (AGPL) in 2029. That commercial revenue is what keeps the project
alive. You keep full ownership of your contribution and can reuse it anywhere
else you like.

Thanks for helping build a more private way to use AI. 🛡️
