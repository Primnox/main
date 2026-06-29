# Primnox v0.1.1 (2026-06-29)

### 🔒 Privacy Mirror — Reversible PII Scrubbing
- Replaced the old one-way redaction with a reversible pseudonymizer: detected PII is swapped for stable `§LABEL_n§` placeholders before a request leaves the device and rehydrated in the reply, so you read real names while the cloud only ever sees de-identified text.
- **Cloud-boundary gating** — scrubbing runs *only* on cloud routes (Groq / OpenAI / Anthropic / Gemini). Local models (Ollama, llama.cpp) receive raw text untouched, since nothing leaves the machine.
- Ships a fp16-packed DeBERTa PII model (`ai4privacy` fine-tune) inside the app, resolved from the PyInstaller bundle / exe dir / `backend/models/pii` and upcast to fp32 on CPU for correctness. Reuses the torch already bundled for YOLO, so the net cost is ~480 MB.
- Subword tokenizer fragments are coalesced so placeholders no longer come out garbled (`§FIRSTNAME_2§§EMAIL_2§…`).
- Streaming-safe: a partial-placeholder-aware rehydrator buffers placeholders that get split across stream chunks.
- **In-chat reveal** — a DeepSeek-style collapsible "Privacy Mirror" block shows exactly what was scrubbed (original → placeholder) for each cloud message.
- `ensure_model_ready()` closes the startup race where early messages could reach the cloud before the model finished loading.

### 🎙️ Meeting Transcription & Audio Fixes
- Added mic + speaker audio capture with WASAPI loopback to ensure full meeting audio context.
- Integrated Whisper transcription directly into the pipeline with size-bounded buffer handling to prevent memory growth.
- Improved the transcription engine via a shared transcriber and scoped port-killing on exit.
- Dropped unused PortAudio DLLs (`sounddevice`) from the Windows build, relying strictly on native Windows audio handling to reduce installer size.

### 💾 Backup Import
- New **Import from File** option in Settings → Backup: restore straight from a local encrypted `.prx` file with your 12-word seed phrase — no cloud provider required.
- `POST /api/backup/import` + `backup_manager.restore_from_bytes()` reuse the existing decrypt/restore pipeline; a wrong seed phrase now surfaces a clear "Wrong seed phrase for this backup" message instead of a raw crypto error.

### 🛡️ App Security & Stability
- Prevented a path traversal vulnerability in the meeting-delete endpoints.
- Added a DNS-rebinding host guard for added local API security.
- Hardened app lifecycle: explicitly frees backend ports on launch and cleanly kills the backend process tree when the UI quits, preventing zombie processes.
- Updated Windows installer CI workflow (`build-windows.yml`) with proper caching, dependency stripping, and automated cross-repo publishing.

### 🎨 Branding
- First real Primnox app icon — monogram "P" + warm node on the dark brand tile. Multi-size `.ico` (16–256) wired into the Windows exe, taskbar, system tray, and the NSIS installer/uninstaller dialogs.

### 🧹 Housekeeping
- Added `social-automation` module.
- Stopped tracking nested `__pycache__` bytecode and broadened `.gitignore` (recursive `**/__pycache__`, `*.orig`, dev screenshots).
