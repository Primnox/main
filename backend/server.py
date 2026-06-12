# backend/server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, BackgroundTasks, HTTPException, File, UploadFile, Form
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from core import PrimnoxCore
from logger import get_logger, get_log_buffer
import uvicorn
import asyncio
import json
import threading
import re
import logging
import os
from observer import start_clipboard_monitor, clear_clipboard_data, register_observer_callback
from pathlib import Path
import shutil
import sys

# ── One-time DB migration: move databases from install dir → AppData ──────────
def _migrate_dbs_to_appdata():
    """
    Pre-0.0.10 databases lived next to the exe and were wiped on every update.
    On first run after an update, copy them to AppData if they aren't there yet.
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return
    dest_dir = Path(appdata) / "primnox_extension"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Candidate source locations: next to __file__ and next to the frozen exe
    candidates: list[Path] = [Path(__file__).parent]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent)

    for db_name in ("memory.db", "chat.db"):
        dest = dest_dir / db_name
        if dest.exists():
            continue  # already in AppData — nothing to do
        for src_dir in candidates:
            src = src_dir / db_name
            if src.exists() and src != dest:
                try:
                    shutil.copy2(src, dest)
                    log_migration = get_logger("migration")
                    log_migration.info(f"Migrated {db_name}: {src} → {dest}")
                except Exception as exc:
                    get_logger("migration").warning(f"Could not migrate {db_name}: {exc}")
                break

app = FastAPI()

# ── Feedback delivery ─────────────────────────────────────────────────────────
# Paste your Discord webhook URL here. Create one in:
# Discord channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL
FEEDBACK_DISCORD_WEBHOOK = os.getenv("FEEDBACK_WEBHOOK", "")

# Zero-Trust Security Middleware
logger = logging.getLogger("primnox_firewall")

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Absolute Ingress IP check
    client_host = request.client.host if request.client else None
    if client_host not in ["127.0.0.1", "localhost", "::1"]:
        logger.critical(f"SECURITY BREACH ATTEMPT: Ingress from {client_host}. Dropping connection.")
        raise HTTPException(status_code=403, detail="Offline-First Doctrine Violation. Connection Terminated.")

    # Host header check
    host_header = request.headers.get("host", "").lower()
    host_clean = re.sub(r':\d+$', '', host_header)
    if host_clean not in ["localhost", "127.0.0.1", "[::1]", "::1"]:
        logger.critical(f"SECURITY BREACH ATTEMPT: Host header '{host_header}' invalid. Dropping.")
        raise HTTPException(status_code=403, detail="Offline-First Doctrine Violation. Host header invalid.")

    response = await call_next(request)
    
    if "Server" in response.headers:
        del response.headers["Server"]
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173", "app://."],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

log = get_logger("server")
_migrate_dbs_to_appdata()   # must run before any DB module initialises
core = PrimnoxCore()
clients = set()
loop = None

def broadcast(event_type, data):
    """
    Sovereign V2: Thread-safe broadcast for frontend compatibility.
    Uses run_coroutine_threadsafe to bridge sync callback -> async WS.
    """
    global loop
    if not loop: return
    
    log.debug(f"Broadcasting event: {event_type}")
    message = json.dumps({"type": event_type, "data": data})
    
    async def send_to_all():
        for ws in list(clients):
            try:
                await ws.send_text(message)
            except Exception:
                clients.discard(ws)
                
    asyncio.run_coroutine_threadsafe(send_to_all(), loop)

core.register_broadcast_callback(broadcast)

# ── Wire reminders to the WS broadcast so a fired reminder reaches the frontend ─
# Without this the reminder loop marks reminders 'fired' but the callback is None,
# so the desktop Notification (usePrimnox handles 'reminder_triggered') never fires.
try:
    import reminder_manager
    reminder_manager.set_callback(broadcast)
except Exception as _e:
    log.warning(f"Reminder callback wiring skipped: {_e}")

# ── Auto-start backup scheduler if previously configured ──────────────────────
try:
    from backup_manager import backup_manager as _bm
    _bm._auto_start()
except Exception as _e:
    log.warning(f"Backup auto-start skipped: {_e}")

# ── Ensure local events table exists ─────────────────────────────────────────
try:
    from event_manager import init_events_table as _init_events
    _init_events()
except Exception as _e:
    log.warning(f"Events table init skipped: {_e}")

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("WebSocket client connected")
    clients.add(ws)
    try:
        # Send initial states to client immediately
        await ws.send_text(json.dumps({"type": "mic_state", "data": {"muted": core.mic_muted}}))
        await ws.send_text(json.dumps({"type": "incognito_changed", "data": {"active": core.incognito}}))
        await ws.send_text(json.dumps({"type": "settings_updated", "data": core.settings}))
        while True:
            await ws.receive_text()
            await ws.send_text(json.dumps({"type": "pong", "data": {}}))
    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
        clients.discard(ws)

@app.post("/message")
async def post_message(request: Request, background_tasks: BackgroundTasks):
    content_type = request.headers.get("content-type", "")

    # ── JSON path (no files attached) ────────────────────────────────────
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        text = body.get("text", "")
        session_id = body.get("sessionId", "current")
        log.info(f"Received message: {text[:50]}...")
        background_tasks.add_task(core.handle_text_input, text, session_id=session_id)
        return {"status": "ok"}

    # ── Multipart path (files attached) ──────────────────────────────────
    if "multipart/form-data" in content_type:
        import tempfile, os, io
        form = await request.form()
        text = form.get("text", "")
        session_id = form.get("sessionId", "current")
        uploaded_files = form.getlist("files")

        extracted_parts = []
        for uf in uploaded_files:
            if not hasattr(uf, "read"):
                continue
            filename = getattr(uf, "filename", "unknown")
            content = await uf.read()
            lower = filename.lower()

            try:
                if lower.endswith(".pdf"):
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(content))
                    pdf_text = "\n".join(p.extract_text() or "" for p in reader.pages)
                    extracted_parts.append(f"[File: {filename}]\n{pdf_text[:8000]}")

                elif lower.endswith((".pptx", ".ppt")):
                    from pptx import Presentation
                    prs = Presentation(io.BytesIO(content))
                    slides_text = []
                    for slide in prs.slides:
                        for shape in slide.shapes:
                            if hasattr(shape, "text"):
                                slides_text.append(shape.text)
                    extracted_parts.append(f"[File: {filename}]\n{chr(10).join(slides_text)[:8000]}")

                elif lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
                    # Save image to temp file, let vision skills handle it later
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1])
                    tmp.write(content)
                    tmp.close()
                    extracted_parts.append(f"[Image attached: {filename} saved to {tmp.name}]")

                elif lower.endswith((".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".tsx", ".html", ".css", ".log", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh", ".bat", ".sql", ".rs", ".go", ".java", ".c", ".cpp", ".h", ".rb")):
                    file_text = content.decode("utf-8", errors="replace")
                    extracted_parts.append(f"[File: {filename}]\n```\n{file_text[:8000]}\n```")

                else:
                    # Unknown file type — save to temp and mention it
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1])
                    tmp.write(content)
                    tmp.close()
                    extracted_parts.append(f"[File attached: {filename} ({len(content)} bytes, saved to {tmp.name})]")

            except Exception as e:
                log.warning(f"Failed to extract content from {filename}: {e}")
                extracted_parts.append(f"[File: {filename} — extraction failed: {e}]")

        # Build the final message with file contents injected
        full_text = text
        if extracted_parts:
            full_text = (text + "\n\n" + "\n\n".join(extracted_parts)).strip()

        log.info(f"Received message with {len(uploaded_files)} file(s): {text[:50]}...")
        background_tasks.add_task(core.handle_text_input, full_text, session_id=session_id)
        return {"status": "ok", "files_processed": len(uploaded_files)}

    raise HTTPException(status_code=400, detail="Unsupported content type")

@app.get("/api/chats")
async def get_chats():
    from chat_manager import get_all_sessions
    return get_all_sessions()

@app.post("/api/chats")
async def post_chat():
    from chat_manager import create_session
    session = create_session()
    return session

@app.get("/api/chats/{session_id}")
async def get_chat_messages(session_id: str):
    from chat_manager import get_session_messages
    return get_session_messages(session_id)

@app.put("/api/chats/{session_id}")
async def put_chat(session_id: str, request: Request):
    from chat_manager import update_session
    body = await request.json()
    title = body.get("title")
    is_pinned = body.get("isPinned")
    folder_id = body.get("folderId")
    update_session(session_id, title=title, is_pinned=is_pinned, folder_id=folder_id)
    return {"status": "ok"}

@app.delete("/api/chats/{session_id}")
async def delete_chat(session_id: str):
    from chat_manager import delete_session
    delete_session(session_id)
    return {"status": "ok"}

@app.post("/api/folders")
async def create_folder_api(request: Request):
    """Create a new chat folder. Body: {title}"""
    from chat_manager import create_folder
    body = await request.json()
    title = body.get("title", "New Folder").strip() or "New Folder"
    folder = create_folder(title)
    return folder

@app.delete("/api/folders/{folder_id}")
async def delete_folder_api(folder_id: str):
    """Delete a chat folder (chats are moved out, not deleted)."""
    from chat_manager import delete_folder
    ok = delete_folder(folder_id)
    return {"status": "ok" if ok else "not_found"}

@app.post("/api/chats/{session_id}/auto_assign")
async def auto_assign_chat(session_id: str):
    from chat_manager import get_session_messages, update_session, get_db
    from brain import think

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, title FROM folders')
    folders = [{"id": r["id"], "title": r["title"]} for r in c.fetchall()]
    conn.close()

    if not folders:
        return {"status": "no_folders"}

    msgs = get_session_messages(session_id)[-20:]
    chat_text = "\n".join([f"{m['speaker']}: {m['text']}" for m in msgs])

    valid_ids   = [f["id"]    for f in folders]
    folder_list = "\n".join([f"{f['title']}  →  {f['id']}" for f in folders])

    prompt = (
        f"Pick the MOST relevant folder for this chat. "
        f"Reply with ONLY the exact ID from the list — no explanation, no quotes.\n\n"
        f"Folders:\n{folder_list}\n\nChat:\n{chat_text}"
    )

    try:
        result    = think(prompt)
        choices   = result.get("choices") or []
        raw       = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
        # Strip any accidental surrounding quotes the LLM sometimes adds
        chosen_id = raw.strip('"\'')
    except Exception as e:
        log.warning(f"auto_assign LLM call failed: {e}")
        return {"status": "error", "reason": str(e)}

    if chosen_id in valid_ids:
        update_session(session_id, folder_id=chosen_id)
        log.info(f"Auto-assigned chat {session_id} → folder {chosen_id}")
        return {"status": "ok", "folder_id": chosen_id}

    # LLM returned garbage — log it so we can improve the prompt later
    log.warning(f"auto_assign returned invalid id '{chosen_id}' (valid: {valid_ids})")
    return {"status": "failed", "reason": "model returned invalid folder id", "raw": raw}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.0.7-alpha"}


@app.get("/api/status")
async def get_status():
    """Rich status report: all subsystem states, DB sizes, model, feed state."""
    import datetime
    from memory import list_memories
    from notes_manager import get_notes
    from reminder_manager import list_reminders
    from skills.skill_router import list_skills
    from settings_manager import get_appdata_dir

    appdata = get_appdata_dir()

    # DB file sizes
    db_sizes = {}
    for db_name in ("memory.db", "chat.db"):
        p = appdata / db_name
        db_sizes[db_name] = p.stat().st_size // 1024 if p.exists() else 0  # KB

    # Last backup
    last_backup_name = None
    backups_dir = appdata / "backups"
    if backups_dir.exists():
        recent = sorted(backups_dir.glob("backup_*.zip"), reverse=True)
        if recent:
            last_backup_name = recent[0].name

    # Feed activity
    feed_len = len(core.feed.history)
    active_window = core.feed.active_window_title or "Unknown"

    # Counts
    try: mem_count = len(list_memories())
    except Exception: mem_count = 0
    try: notes_count = len(get_notes())
    except Exception: notes_count = 0
    try: reminders_count = len(list_reminders())
    except Exception: reminders_count = 0
    try: skills_count = len(list_skills())
    except Exception: skills_count = 0

    return {
        "status": "ok",
        "version": "0.0.7-alpha",
        "timestamp": datetime.datetime.now().isoformat(),
        "active_window": active_window,
        "feed_events": feed_len,
        "mic_muted": core.mic_muted,
        "incognito": core.incognito,
        "active_model": core.settings.get("active_model", "Groq_Llama_3"),
        "has_api_key": bool(core.settings.get("groq_api_key") or core.settings.get("openai_api_key") or core.settings.get("anthropic_api_key")),
        "memories_count": mem_count,
        "notes_count": notes_count,
        "reminders_count": reminders_count,
        "skills_count": skills_count,
        "db_sizes_kb": db_sizes,
        "last_backup": last_backup_name,
    }

@app.get("/api/dashboard")
async def get_dashboard():
    import datetime
    from notes_manager import get_notes
    from memory import list_memories
    from reminder_manager import list_reminders
    from skills.skill_router import list_skills

    # Feed data — ambient + window events
    history = list(core.feed.history[-25:])
    ambient_events = [h for h in core.feed.history if "Ambient:" in h]
    # Rough word count from ambient chunks (strip timestamp + label)
    words_heard = 0
    for e in ambient_events:
        parts = e.split("Ambient:", 1)
        if len(parts) > 1:
            words_heard += len(parts[1].split())

    # Current focus
    active_window = core.feed.active_window_title or "Unknown"
    active_process = core.feed.active_process_name or "Unknown"

    # Meetings from disk
    meetings_dir = Path.home() / "Documents" / "Primnox" / "Meetings"
    meetings = []
    if meetings_dir.exists():
        for d in sorted(meetings_dir.iterdir(), reverse=True)[:5]:
            if not d.is_dir():
                continue
            summary_file = d / "summary.txt"
            has_summary = summary_file.exists()
            preview = None
            if has_summary:
                try:
                    preview = summary_file.read_text(encoding="utf-8")[:250]
                except Exception:
                    pass
            # Try to parse a date from the folder name (format: YYYYMMDD_HHMMSS_AppName)
            folder_date = None
            try:
                folder_date = datetime.datetime.strptime(d.name[:15], "%Y%m%d_%H%M%S").date()
            except Exception:
                pass
            meetings.append({
                "name": d.name,
                "has_summary": has_summary,
                "summary_preview": preview,
                "date": folder_date.isoformat() if folder_date else None,
                "is_today": folder_date == datetime.date.today() if folder_date else False,
            })

    # Counts
    try:
        notes_count = len(get_notes())
    except Exception:
        notes_count = 0
    try:
        memories_count = len(list_memories())
    except Exception:
        memories_count = 0

    # Pending reminders
    try:
        reminders = list_reminders()
        reminders_count = len(reminders)
    except Exception:
        reminders = []
        reminders_count = 0

    # Last backup info
    last_backup = None
    try:
        from settings_manager import get_appdata_dir
        backups_dir = get_appdata_dir() / "backups"
        if backups_dir.exists():
            recent = sorted(backups_dir.glob("backup_*.zip"), reverse=True)
            if recent:
                bp = recent[0]
                last_backup = {
                    "filename": bp.name,
                    "size_kb": bp.stat().st_size // 1024,
                    "timestamp": bp.stat().st_mtime,
                }
    except Exception:
        pass

    # Registered skills count
    try:
        skills_count = len(list_skills())
    except Exception:
        skills_count = 0

    # Flag whether the primary AI key is configured (don't expose the key itself)
    has_api_key = bool(core.settings.get("groq_api_key") or
                       core.settings.get("openai_api_key") or
                       core.settings.get("anthropic_api_key"))

    return {
        "active_window": active_window,
        "active_process": active_process,
        "feed_history": history,
        "ambient_count": len(ambient_events),
        "words_heard_today": max(0, words_heard),
        "meetings": meetings,
        "notes_count": notes_count,
        "memories_count": memories_count,
        "has_api_key": has_api_key,
        "reminders_count": reminders_count,
        "reminders": reminders,
        "last_backup": last_backup,
        "skills_count": skills_count,
    }

@app.get("/api/ollama/status")
async def ollama_status():
    """Returns Ollama running status + list of installed models."""
    from brain import get_ollama_status
    from settings_manager import load_settings
    s = load_settings()
    base_url = s.get("ollama_base_url", "http://localhost:11434")
    return get_ollama_status(base_url)

@app.get("/api/profile")
async def get_profile():
    """Return the current user emotion + learning profile."""
    from settings_manager import load_settings
    s = load_settings()
    return {
        "mood": s.get("current_mood"),
        "onboarding_profile": s.get("onboarding_profile", {}),
        "onboarding_completed": s.get("onboarding_completed", False),
    }


@app.post("/api/daily_brief")
async def post_daily_brief(background_tasks: BackgroundTasks):
    """Trigger daily debrief via DailyBriefSkill — result is broadcast via WS."""
    def _run_brief():
        from notes_manager import get_notes
        from skills.skill_router import route_skill
        notes_count = 0
        try:
            notes_count = len(get_notes())
        except Exception:
            pass
        result = route_skill(
            user_message="daily brief",
            metadata={
                "notes_count": notes_count,
                "feed_history": list(core.feed.history[-100:]),
            }
        )
        brief_text = result.get("output_text") or "Daily brief unavailable."
        broadcast("daily_debrief", {"debrief": brief_text})

    background_tasks.add_task(_run_brief)
    return {"status": "generating"}

@app.post("/api/error_explain")
async def explain_error(request: Request):
    """Feed an error string to the dynamic island error handler and return a structured payload."""
    from brain import think
    from system_prompts import ERROR_HANDLER_PROMPT
    body = await request.json()
    error_message = body.get("error_message", "")
    context = body.get("context", "")
    prompt = f"Error: {error_message}" + (f"\nContext: {context}" if context else "")
    try:
        response = think(prompt, system_override=ERROR_HANDLER_PROMPT)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Strip markdown fences if the model wrapped its response anyway
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        payload = json.loads(content)
        return payload
    except Exception as e:
        log = get_logger("error_explain")
        log.error(f"error_explain failed: {e}")
        return {
            "summary": f"something broke and i can't even explain it properly: {str(e)[:80]}",
            "fix": "check the logs bro",
            "hover_text": "click to copy the fix"
        }


@app.post("/api/media/control")
async def media_control(request: Request):
    """Send a playback command (play_pause / next / prev / stop) to whatever
    app is currently registered with Windows SMTC.
    Uses the same persistent SMTC event loop as feed_manager so the Windows
    Runtime COM apartment stays stable."""
    try:
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as _M
        import asyncio as _aio
        from feed_manager import _get_smtc_loop
    except ImportError:
        return {"success": False, "error": "winsdk not available"}

    body   = await request.json()
    action = body.get("action", "")

    async def _do():
        mgr     = await _M.request_async()
        session = mgr.get_current_session()
        if not session:
            return False
        if action == "play_pause": await session.try_toggle_play_pause_async()
        elif action == "next":     await session.try_skip_next_async()
        elif action == "prev":     await session.try_skip_previous_async()
        elif action == "stop":     await session.try_stop_async()
        else: return False
        return True

    try:
        future = _aio.run_coroutine_threadsafe(_do(), _get_smtc_loop())
        ok = await asyncio.to_thread(lambda: future.result(timeout=4))
        return {"success": ok}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/calendar/events")
async def get_calendar_events(days: int = 7):
    """Legacy iCal endpoint kept for backwards compatibility."""
    try:
        from skills.calendar_skill import CalendarIslandSkill
        skill  = CalendarIslandSkill()
        events = skill._fetch_events()
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) + timedelta(days=days)
        events = [e for e in events if e.start <= cutoff]
        return {"events": [e.to_dict() for e in events], "count": len(events)}
    except Exception as e:
        return {"events": [], "count": 0, "error": str(e)}


# ── Local calendar CRUD ────────────────────────────────────────────────────────

@app.get("/api/events")
async def api_list_events(start: str = "", end: str = ""):
    from event_manager import list_events
    return {"events": list_events(start or None, end or None)}


@app.post("/api/events")
async def api_create_event(request: Request):
    data = await request.json()
    if not data.get("title") or not data.get("start_dt") or not data.get("end_dt"):
        raise HTTPException(status_code=400, detail="title, start_dt, end_dt are required")
    from event_manager import create_event
    return create_event(data)


@app.put("/api/events/{event_id}")
async def api_update_event(event_id: str, request: Request):
    data = await request.json()
    from event_manager import update_event
    updated = update_event(event_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Event not found")
    return updated


@app.delete("/api/events/{event_id}")
async def api_delete_event(event_id: str):
    from event_manager import delete_event
    if not delete_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    return {"success": True}


@app.post("/api/events/parse-nl")
async def api_parse_nl_event(request: Request):
    """Parse a natural-language event description into a structured event dict."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    from brain import think
    from datetime import datetime as _dt
    today_str = _dt.now().strftime("%A, %B %d, %Y at %H:%M")
    prompt = (
        f'Today is {today_str}.\n\n'
        'Parse the following natural-language event description into a JSON object '
        'with these exact fields (no other text, no markdown fences):\n'
        '  title        (string)\n'
        '  start_dt     (ISO 8601 local datetime, e.g. "2026-06-12T14:00:00")\n'
        '  end_dt       (ISO 8601 local datetime; assume 1 h if not specified)\n'
        '  all_day      (boolean)\n'
        '  location     (string, empty if not mentioned)\n'
        '  description  (string, empty if not mentioned)\n'
        '  color        ("#6366f1" as default)\n\n'
        f'Input: "{text}"\n\n'
        'Respond with ONLY the JSON object.'
    )
    try:
        response = await asyncio.to_thread(think, prompt)
        content = (response.get("choices", [{}])[0]
                           .get("message", {})
                           .get("content", "")).strip()
        # Strip markdown code fences if model wraps output
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        import json as _json
        parsed = _json.loads(content)
        return {"event": parsed}
    except Exception as e:
        log.error(f"NL event parse failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/smart_paste")
async def smart_paste(request: Request):
    """Transform clipboard content via LLM to fit the current target application."""
    from brain import think
    from system_prompts import SMART_PASTE_PROMPT
    body = await request.json()
    content = body.get("content", "")
    if not content.strip():
        return {"transformed": content}
    try:
        from screen_reader import read_screen
        uia = read_screen()
        target_app = uia.get("window_title", "") if isinstance(uia, dict) else ""
    except Exception:
        target_app = ""
    prompt = f"Target app: {target_app or 'unknown'}\nContent to transform:\n{content}"
    try:
        response = think(prompt, system_override=SMART_PASTE_PROMPT)
        text = response.get("choices", [{}])[0].get("message", {}).get("content", content)
        return {"transformed": text.strip() or content}
    except Exception as e:
        log = get_logger("smart_paste")
        log.error(f"smart_paste failed: {e}")
        return {"transformed": content}


@app.get("/logs")
async def get_logs(limit: int = 200, level: str = "all"):
    return get_log_buffer(limit=limit, level=level)


# ── Backup ─────────────────────────────────────────────────────────────────────

@app.get("/api/backup/status")
async def backup_status():
    from backup_manager import backup_manager
    return backup_manager.status()


@app.post("/api/backup/validate-mnemonic")
async def backup_validate_mnemonic(body: dict):
    """Validate a 12-word phrase against the cached custom wordlist."""
    from backup_manager import validate_mnemonic
    from settings_manager import load_settings
    mnemonic = (body.get("mnemonic") or "").strip()
    if not mnemonic:
        raise HTTPException(400, "mnemonic is required")
    wordlist = load_settings().get("backup_wordlist", [])
    if not wordlist:
        raise HTTPException(400, "Wordlist not loaded — complete onboarding first")
    valid, err = validate_mnemonic(mnemonic, wordlist)
    return {"valid": valid, "error": err}


@app.post("/api/backup/setup")
async def backup_setup(body: dict):
    """Configure backup provider and activate the scheduler."""
    from backup_manager import backup_manager, validate_mnemonic
    from settings_manager import load_settings, save_settings

    mnemonic       = (body.get("mnemonic") or "").strip()
    provider       = body.get("provider", "s3")
    provider_cfg   = body.get("provider_config", {})
    interval_hours = int(float(body.get("interval_hours", 24)))

    if not mnemonic:
        raise HTTPException(400, "mnemonic is required")

    # Validation is mandatory: the wordlist checksum is the only thing that catches
    # a typo'd phrase. Skipping it would silently store a key that can never be
    # reproduced from the user's real mnemonic, making the backup unrecoverable.
    wordlist = load_settings().get("backup_wordlist", [])
    if not wordlist:
        raise HTTPException(400, "Wordlist not loaded — generate a mnemonic first")
    valid, err = validate_mnemonic(mnemonic, wordlist)
    if not valid:
        raise HTTPException(400, f"Invalid mnemonic: {err}")

    try:
        backup_manager.setup(mnemonic, provider, provider_cfg, interval_hours)
    except Exception as e:
        raise HTTPException(500, str(e))

    return {"ok": True, "message": f"Backup configured — syncing every {interval_hours}h"}


@app.post("/api/backup/now")
async def backup_now(body: dict, background_tasks: BackgroundTasks):
    """Trigger an immediate backup. Mnemonic optional if already unlocked."""
    from backup_manager import backup_manager
    mnemonic = (body.get("mnemonic") or "").strip() or None

    def _run():
        try:
            filename = backup_manager.backup_now(mnemonic)
            log.info(f"Manual backup done: {filename}")
        except Exception as e:
            log.error(f"Manual backup failed: {e}")

    background_tasks.add_task(_run)
    return {"ok": True, "message": "Backup started in background"}


@app.get("/api/backup/list")
async def backup_list():
    from backup_manager import backup_manager
    backups = await asyncio.to_thread(backup_manager.list_backups)
    return {"backups": backups}


@app.post("/api/backup/restore")
async def backup_restore(body: dict):
    """Download + decrypt + restore a named backup. Runs synchronously so errors propagate."""
    from backup_manager import backup_manager
    filename = body.get("filename", "").strip()
    mnemonic = (body.get("mnemonic") or "").strip()
    if not filename:
        raise HTTPException(400, "filename is required")
    if not mnemonic:
        raise HTTPException(400, "mnemonic is required")

    try:
        await asyncio.to_thread(backup_manager.restore, filename, mnemonic)
    except Exception as e:
        log.error(f"Restore failed: {e}")
        raise HTTPException(500, str(e))

    return {"ok": True, "message": "Restore complete — restart Primnox for changes to take effect"}


@app.delete("/api/backup/{filename}")
async def backup_delete(filename: str):
    import re as _re
    if not _re.fullmatch(r'[A-Za-z0-9_\-]+\.prx', filename):
        raise HTTPException(400, "Invalid backup filename")
    from backup_manager import backup_manager
    try:
        await asyncio.to_thread(backup_manager.delete_backup, filename)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/backup/test-connection")
async def backup_test_connection():
    from backup_manager import backup_manager
    ok = await asyncio.to_thread(backup_manager.test_connection)
    return {"ok": ok, "message": "Connected" if ok else "Connection failed — check credentials"}


@app.post("/api/backup/disable")
async def backup_disable():
    from backup_manager import backup_manager
    backup_manager.disable()
    return {"ok": True}


@app.post("/api/backup/wordlist")
async def backup_store_wordlist(body: dict):
    """
    Store the custom Primnox wordlist (fetched from seed.primnox.com during onboarding).
    Expects: {"wordlist": ["word1", "word2", ...]}  — exactly 2048 words.
    """
    from settings_manager import load_settings, save_settings
    wordlist = body.get("wordlist", [])
    if len(wordlist) != 2048:
        raise HTTPException(400, f"Wordlist must have 2048 words, got {len(wordlist)}")
    s = load_settings()
    s["backup_wordlist"] = wordlist
    save_settings(s)
    return {"ok": True}


@app.post("/api/backup/generate-mnemonic")
async def backup_generate_mnemonic():
    """
    Generate a fresh 12-word BIP-39-style mnemonic.

    Uses the stored custom Primnox wordlist if available (see POST /api/backup/wordlist).
    Falls back to fetching from seed.primnox.com, then to the BIP-39 English wordlist
    from the canonical GitHub source. The fetched list is cached to settings so subsequent
    calls work offline.
    """
    from backup_manager import generate_mnemonic
    from settings_manager import load_settings, save_settings

    s = load_settings()
    wordlist: list[str] = s.get("backup_wordlist", [])

    if len(wordlist) != 2048:
        # Try to fetch and cache from remote sources
        fetched: list[str] = []
        urls = [
            "https://seed.primnox.com/wordlist.txt",
            "https://raw.githubusercontent.com/trezor/python-mnemonic/master/src/mnemonic/wordlist/english.txt",
        ]
        for url in urls:
            try:
                import httpx
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    r = await client.get(url, timeout=8)
                if r.status_code == 200:
                    words = [w.strip() for w in r.text.splitlines()
                             if w.strip() and not w.startswith("#")]
                    if len(words) >= 2048:
                        fetched = words[:2048]
                        break
            except Exception:
                continue

        if len(fetched) == 2048:
            wordlist = fetched
            s["backup_wordlist"] = wordlist
            save_settings(s)
        else:
            raise HTTPException(
                503,
                "Wordlist unavailable — visit seed.primnox.com or check your internet connection",
            )

    try:
        phrase = generate_mnemonic(wordlist)
        return {"mnemonic": phrase}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/notes")
async def get_notes():
    from notes_manager import get_notes
    return get_notes()

@app.get("/api/graph")
async def get_graph():
    from notes_manager import get_db
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, title, project, parent_id FROM notes ORDER BY id ASC")
    rows = c.fetchall()
    
    nodes = []
    links = []
    
    workspaces = set()
    for r in rows:
        workspaces.add(r["project"] or "General")
        
    for ws in workspaces:
        nodes.append({
            "id": f"ws_{ws}",
            "name": ws,
            "group": 0,
            "val": 5, # Larger node for workspace
            "type": "workspace"
        })
        
    for r in rows:
        n_id = r["id"]
        title = r["title"] or "Untitled"
        project = r["project"] or "General"
        parent_id = r["parent_id"]
        
        nodes.append({
            "id": n_id,
            "name": title,
            "group": 1,
            "val": 2,
            "type": "note"
        })
        
        if parent_id is not None:
            # Link to parent note
            links.append({"source": n_id, "target": parent_id})
        else:
            # Link to workspace
            links.append({"source": n_id, "target": f"ws_{project}"})
            
    conn.close()
    return {"nodes": nodes, "links": links}

@app.post("/notes/update")
async def post_notes_update(request: Request, background_tasks: BackgroundTasks):
    from notes_manager import update_note, add_note
    body = await request.json()
    index = body.get("index")
    title = body.get("title", "Untitled")
    text = body.get("text", "")
    project = body.get("project", "General")
    parent_id = body.get("parent_id", None)
    
    if index is not None and index > 0:
        success = update_note(index, title, text, project=project, parent_id=parent_id)
        if not success:
            note = add_note(text, title=title, project=project, parent_id=parent_id)
            index = note["id"]
    else:
        note = add_note(text, title=title, project=project, parent_id=parent_id)
        index = note["id"]
        
    def _summarize():
        from notes_manager import get_db
        from brain import think
        import json
        if len(text) < 50: return
        res = think(f"Extract exactly 3 short key bullet points from this text:\n\n{text}\n\nFormat as a JSON array of strings ONLY. No markdown, no explanation.")
        try:
            content = res.get("choices", [{}])[0].get("message", {}).get("content", "[]")
            import re
            arr_str = re.search(r'\[.*\]', content, re.DOTALL)
            if arr_str:
                kp = json.loads(arr_str.group())
                conn = get_db()
                c = conn.cursor()
                if index is not None and index > 0:
                    c.execute("UPDATE notes SET key_points=? WHERE id=?", (json.dumps(kp), index))
                    conn.commit()
                conn.close()
        except Exception as e:
            log.error(f"Auto-summarize failed: {e}")

    background_tasks.add_task(_summarize)
    broadcast("note_added", {})
    return {"success": True, "id": index}

@app.post("/api/notes/generate-batch")
async def generate_batch_notes(
    files: List[UploadFile] = File(...),
    prompt: Optional[str] = Form(None),
    project: str = Form("General"),
    mode: str = Form("separate")
):
    import base64
    from brain import think
    from notes_manager import add_note
    import json
    
    parsed_files = []
    
    # Fail-Fast Parsing Loop
    for f in files:
        content = await f.read()
        filename = f.filename.lower()
        
        try:
            if filename.endswith(".pdf"):
                import io
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(content))
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                if not text.strip():
                    raise ValueError("No text could be extracted from PDF.")
                parsed_files.append({"type": "text", "content": text[:12000], "name": f.filename})
                
            elif filename.endswith((".pptx", ".ppt")):
                import io
                from pptx import Presentation
                prs = Presentation(io.BytesIO(content))
                text = ""
                for i, slide in enumerate(prs.slides):
                    text += f"--- Slide {i+1} ---\n"
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            text += shape.text + "\n"
                if not text.strip():
                    raise ValueError("No text could be extracted from Presentation.")
                parsed_files.append({"type": "text", "content": text[:12000], "name": f.filename})
                
            elif filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
                b64 = base64.b64encode(content).decode('utf-8')
                parsed_files.append({"type": "image", "content": b64, "name": f.filename})
                
            elif filename.endswith((".txt", ".md", ".csv", ".json")):
                text = content.decode('utf-8', errors='ignore')
                parsed_files.append({"type": "text", "content": text[:12000], "name": f.filename})
                
            else:
                raise ValueError(f"Unsupported file type: {filename}")
        except Exception as e:
            return {"success": False, "error": str(e), "failed_file": f.filename}
            
    system_instruction = 'You are an AI Note Generator. Respond ONLY with raw valid JSON in this exact format: {"title": "A short summary title", "body": "The detailed markdown notes..."}. Do NOT include markdown code blocks around the JSON.'
    
    if mode == "separate":
        for pf in parsed_files:
            if pf["type"] == "text":
                ctx = f"File Name: {pf['name']}\nContent:\n{pf['content']}"
                res = think(prompt or "Generate comprehensive notes for this document.", context=ctx + "\n\n" + system_instruction)
            else:
                ctx = f"File Name: {pf['name']}\nAnalyze this image and generate notes."
                res = think(prompt or ctx, context=system_instruction, image_base64=pf['content'])
                
            try:
                content_str = res.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                content_str = content_str.strip()
                if content_str.startswith("```json"):
                    content_str = content_str[7:]
                if content_str.endswith("```"):
                    content_str = content_str[:-3]
                    
                note_data = json.loads(content_str.strip())
                add_note(note_data.get("body", "Failed to extract body."), title=note_data.get("title", pf["name"]), project=project)
            except Exception as e:
                log.error(f"Failed to parse JSON for {pf['name']}: {e}")
                add_note(f"Failed to generate structured notes. Raw output:\n{res}", title=pf["name"], project=project)
    else:
        combined_text = ""
        images = []
        for pf in parsed_files:
            if pf["type"] == "text":
                combined_text += f"\n\n--- File: {pf['name']} ---\n{pf['content']}"
            else:
                images.append(pf['content'])
                
        img_b64 = images[0] if images else None
        
        ctx = f"You are synthesizing multiple sources into one cohesive note.\n{combined_text}\n\n{system_instruction}"
        res = think(prompt or "Generate a unified, comprehensive note combining these sources.", context=ctx, image_base64=img_b64)
        
        try:
            content_str = res.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            content_str = content_str.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
                
            note_data = json.loads(content_str.strip())
            add_note(note_data.get("body", "Failed to extract body."), title=note_data.get("title", "Combined Notes"), project=project)
        except Exception as e:
            log.error(f"Failed to parse JSON for combined notes: {e}")
            add_note(f"Failed to generate structured notes. Raw output:\n{res}", title="Combined Notes", project=project)

    broadcast("note_added", {})
    return {"success": True}

@app.post("/api/generate")
async def post_generate(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    prompt = body.get("prompt", "")
    from brain import think
    result = think(prompt)
    return result

@app.delete("/notes/{index}")
async def delete_notes(index: int):
    from notes_manager import delete_note
    success = delete_note(index)
    broadcast("note_added", {}) # tell frontend to reload notes
    return {"success": success}

@app.post("/notes/pin")
async def post_notes_pin(request: Request):
    from notes_manager import toggle_pin_note
    body = await request.json()
    index = body.get("id")
    pinned = body.get("pinned", True)
    if index is not None:
        success = toggle_pin_note(index, pinned)
        broadcast("note_added", {})
        return {"success": success}
    return {"success": False, "error": "Missing id"}

@app.post("/notes/export")
async def export_notes():
    from notes_manager import get_notes
    import time
    from pathlib import Path
    
    notes = get_notes()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    export_path = Path.home() / "Documents" / "Primnox" / f"export_{timestamp}.md"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(export_path, "w", encoding="utf-8") as f:
        f.write("# Primnox Notes Export\n\n")
        for i, note in enumerate(notes):
            f.write(f"## Node {i}\n{note}\n\n")
            
    return {"success": True, "path": str(export_path)}

@app.get("/tasks")
async def get_tasks():
    from notes_manager import get_tasks
    return get_tasks()

@app.post("/tasks")
async def create_task(request: Request):
    """Create a new task. Body: {text, priority?, due_date?}"""
    from notes_manager import add_task
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    priority = body.get("priority", "normal")
    due_date = body.get("due_date")
    task = add_task(text, priority=priority, due_date=due_date)
    broadcast("task_added", {"text": text})
    return {"success": True, "task": task}

@app.post("/tasks/{id}/complete")
async def complete_task(id: int):
    from notes_manager import complete_task
    return {"success": complete_task(id)}

@app.delete("/tasks/{id}")
async def delete_task_endpoint(id: int):
    from notes_manager import delete_task
    ok = delete_task(id)
    if ok:
        broadcast("task_added", {})  # refresh frontend task list
    return {"success": ok}

@app.get("/memory")
async def get_memory():
    from memory import get_memory
    return get_memory()

@app.delete("/memory/{key}")
async def delete_memory(key: str):
    from memory import delete_memory
    delete_memory(key)
    return {"success": True}

@app.get("/conversations")
async def get_conversations():
    from notes_manager import get_conversations
    return get_conversations()

@app.get("/api/onboarding/scan")
async def scan_onboarding():
    import os
    from pathlib import Path
    import getpass
    import json
    from brain import think
    
    projects = []
    skills = set()
    
    home_dir = Path.home()
    
    # Aggressive ignore list to prevent freezing and junk data
    ignore_dirs = {
        'AppData', 'Application Data', 'Local Settings', 'Cookies', 
        'Recent', 'SendTo', 'Start Menu', 'NetHood', 'PrintHood', 
        'Templates', 'node_modules', 'venv', '.venv', '.git', 
        'dist', 'build', '__pycache__', '.cache', '.cargo', 
        '.rustup', '.npm', '.vscode', 'Downloads', 'Music', 
        'Pictures', 'Videos', 'Documents', 'Desktop', 'Public',
        'Saved Games', 'Favorites', 'Contacts', 'Searches', 'Links',
        'OneDrive'
    }

    try:
        for root, dirs, files in os.walk(str(home_dir)):
            # Mutate dirs in-place to skip heavy or hidden folders
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith('.')]
            
            # Don't go deeper than 4 levels from home directory
            depth = root.count(os.sep) - str(home_dir).count(os.sep)
            if depth > 4:
                dirs.clear()
                continue
                
            # If we find code files in this directory, consider it a project
            is_project = False
            for f in files:
                if f.endswith(".py"): 
                    skills.add("Python")
                    is_project = True
                elif f.endswith(".ts") or f.endswith(".tsx"): 
                    skills.add("TypeScript")
                    is_project = True
                elif f.endswith(".js") or f.endswith(".jsx"): 
                    skills.add("JavaScript")
                    is_project = True
                elif f.endswith(".rs"): 
                    skills.add("Rust")
                    is_project = True
                elif f.endswith(".go"): 
                    skills.add("Go")
                    is_project = True
                elif f.endswith(".cpp") or f.endswith(".h"): 
                    skills.add("C++")
                    is_project = True
                elif f.endswith(".java"): 
                    skills.add("Java")
                    is_project = True
                elif f.endswith(".cs"): 
                    skills.add("C#")
                    is_project = True
            
            # If it's a project (and not the root home folder itself), add its name
            if is_project and depth > 0:
                folder_name = os.path.basename(root)
                if folder_name not in projects:
                    projects.append(folder_name)
                    
            # Cap the number of projects we extract to save time
            if len(projects) > 30:
                break
    except Exception as e:
        print(f"Scanner error: {e}")
        pass

    projects = projects[:10] if projects else ["Workspace Sandbox"]
    skills = list(skills)[:10] if skills else ["System Administration"]
    
    # Use LLM to infer the rest of the profile dynamically
    prompt = f"Given these projects: {', '.join(projects)} and skills: {', '.join(skills)}, infer 3 topics, 2 communication_styles, and 3 knowledge_areas. Output ONLY valid JSON matching this schema: {{\"topics\": [], \"communication_style\": [], \"knowledge_areas\": []}}"
    try:
        response = think(prompt)
        # think() returns an OpenAI-compatible dict — extract the text content first
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError("Empty LLM response")
        # Strip markdown code fences if the model wrapped the JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        llm_data = json.loads(content)
    except Exception:
        llm_data = {
            "topics": ["Software Development", "System Architecture", "Open Source"],
            "communication_style": ["Direct", "Technical"],
            "knowledge_areas": ["Local Filesystem", "Version Control", "Application Development"]
        }

    return {
        "name": getpass.getuser(),
        "role": "Developer",
        "projects": projects[:5],
        "skills": skills[:5],
        "topics": llm_data.get("topics", [])[:4],
        "communication_style": llm_data.get("communication_style", [])[:3],
        "knowledge_areas": llm_data.get("knowledge_areas", [])[:4]
    }

@app.get("/settings")
async def get_settings():
    from settings_manager import load_settings
    settings = load_settings()
    # Mask API keys for security
    for key in ["groq_api_key", "openai_api_key", "anthropic_api_key"]:
        if settings.get(key):
            settings[key] = "sk-****"
    return settings

@app.post("/generate")
async def post_generate(request: Request):
    from brain import think
    body = await request.json()
    prompt = body.get("prompt", "")
    context = body.get("context", "")
    if not prompt:
        return {"response": ""}
    # Using non-streaming think wrapper if available, or just joining the generator
    from brain import think_stream
    response_chunks = []
    for token in think_stream(prompt, context=context):
        response_chunks.append(token)
    return {"response": "".join(response_chunks)}

@app.post("/settings")
async def post_settings(request: Request):
    from settings_manager import save_settings, load_settings
    body = await request.json()
    
    old_settings = load_settings()
    
    # Merge partial updates with existing settings
    merged = {**old_settings, **body}
    
    # Do not overwrite with masked keys
    for key in ["groq_api_key", "openai_api_key", "anthropic_api_key"]:
        if merged.get(key) == "sk-****":
            merged[key] = old_settings.get(key, "")
            
    save_settings(merged)
    
    # Reload settings in core
    core.settings = load_settings()
    
    # Propagate to VADListener dynamically
    if hasattr(core, "vad") and core.vad:
        core.vad.settings = core.settings
        # Sensitivity: Map higher slider values (0.0 to 1.0) to lower noise thresholds (0.05 to 0.005)
        # So slider at 1.0 -> 0.005 (very sensitive), slider at 0.0 -> 0.05 (not sensitive)
        sensitivity = float(core.settings.get("vad_sensitivity", 0.5))
        core.vad.SILENCE_THRESHOLD = max(0.005, 0.05 - (sensitivity * 0.045))
        log.info(f"VAD sensitivity threshold updated dynamically to: {core.vad.SILENCE_THRESHOLD:.4f}")
        
    broadcast("settings_updated", core.settings)
    return {"success": True}

@app.get("/voices")
async def get_voices():
    from voice_id import get_profiles
    return get_profiles()

@app.post("/voices/enroll")
async def enroll_voice(request: Request):
    from voice_id import enroll_speaker
    body = await request.json()
    wav_path = body.get("wav_path")
    name = body.get("name")
    if not wav_path or not name:
        raise HTTPException(status_code=400, detail="wav_path and name required")
    enroll_speaker(wav_path, name)
    return {"success": True}

@app.delete("/voices/{name}")
async def delete_voice(name: str):
    from voice_id import delete_profile
    delete_profile(name)
    return {"success": True}

@app.post("/clipboard/clear")
async def post_clear_clipboard():
    clear_clipboard_data()
    # Reset state to idle in the frontend
    broadcast("state", {"value": "idle"})
    return {"success": True}

@app.post("/mic/toggle")
async def toggle_mic_endpoint():
    muted = core.toggle_mic()
    return {"muted": muted}

@app.post("/incognito/toggle")
async def toggle_incognito_endpoint():
    active = core.toggle_incognito()
    return {"active": active}

@app.on_event("startup")
async def startup_event():
    global loop
    loop = asyncio.get_running_loop()
    # Register observer callback for notifications
    register_observer_callback(broadcast)
    # Start the clipboard monitor task in the background
    asyncio.create_task(start_clipboard_monitor())
    # Start auto-cleanup scheduler (runs once at startup + every 24h)
    from cleanup_manager import start_cleanup_scheduler
    await asyncio.to_thread(start_cleanup_scheduler)
    log.info("Primnox Startup Complete - Event loop, clipboard monitor and cleanup scheduler initialized.")


@app.post("/api/cleanup")
async def trigger_cleanup():
    """Manually trigger a cleanup pass. Returns what was deleted."""
    from cleanup_manager import run_cleanup
    result = await asyncio.to_thread(run_cleanup)
    return result


@app.get("/api/storage")
async def storage_info():
    """Return storage usage for meetings, memories, TTS cache."""
    import sqlite3
    from cleanup_manager import _meetings_dir
    from memory import DB_PATH
    from pathlib import Path
    import tempfile

    info: dict = {}

    # Meetings
    meetings_dir = _meetings_dir()
    if meetings_dir.exists():
        folders = [f for f in meetings_dir.iterdir() if f.is_dir()]
        total_mb = sum(
            sum(fi.stat().st_size for fi in f.rglob("*") if fi.is_file())
            for f in folders
        ) / (1024 * 1024)
        info["meetings"] = {"count": len(folders), "size_mb": round(total_mb, 1)}
    else:
        info["meetings"] = {"count": 0, "size_mb": 0}

    # Memories
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM memories")
            mem_count = c.fetchone()[0]
        db_size = Path(DB_PATH).stat().st_size / (1024 * 1024) if Path(DB_PATH).exists() else 0
        info["memories"] = {"count": mem_count, "size_mb": round(db_size, 2)}
    except Exception:
        info["memories"] = {"count": 0, "size_mb": 0}

    return info

@app.get("/api/meetings")
async def list_meetings():
    """List all meeting recording folders with metadata."""
    from cleanup_manager import _meetings_dir
    from datetime import datetime
    import json

    meetings_dir = _meetings_dir()
    if not meetings_dir.exists():
        return {"meetings": []}

    items = []
    for folder in sorted(meetings_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
        if not folder.is_dir():
            continue
        try:
            files  = list(folder.rglob("*"))
            files  = [f for f in files if f.is_file()]
            size_b = sum(f.stat().st_size for f in files)
            mtime  = datetime.fromtimestamp(folder.stat().st_mtime)

            # Try to read a summary if one exists
            summary_text = ""
            for candidate in ("summary.txt", "summary.md", "transcript.txt"):
                p = folder / candidate
                if p.exists():
                    try:
                        summary_text = p.read_text(encoding="utf-8", errors="replace")[:300]
                    except Exception:
                        pass
                    break

            # Collect audio/video files
            media_exts  = {".mp3", ".wav", ".mp4", ".m4a", ".ogg", ".webm"}
            media_files = [f.name for f in files if f.suffix.lower() in media_exts]

            items.append({
                "name":        folder.name,
                "date":        mtime.isoformat(timespec="seconds"),
                "size_mb":     round(size_b / (1024 * 1024), 2),
                "file_count":  len(files),
                "media_files": media_files,
                "summary":     summary_text,
            })
        except Exception as e:
            log.warning(f"Could not read meeting folder {folder.name}: {e}")

    return {"meetings": items}


@app.delete("/api/meetings/{folder_name}")
async def delete_meeting(folder_name: str):
    """Delete a specific meeting folder by name."""
    import re, shutil
    from cleanup_manager import _meetings_dir

    # Sanitise — only allow folder names that look like meeting names (no path traversal)
    if not re.match(r'^[\w\-\. ]+$', folder_name):
        raise HTTPException(status_code=400, detail="Invalid folder name")

    target = _meetings_dir() / folder_name
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Meeting not found")

    try:
        shutil.rmtree(target)
        log.info(f"Deleted meeting folder on request: {folder_name}")
        return {"deleted": folder_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/feedback")
async def receive_feedback(request: Request, background_tasks: BackgroundTasks):
    import time
    from pathlib import Path
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    category = body.get("category", "General")
    content = body.get("content", "").strip()
    contact = body.get("contact", "").strip()

    if not content:
        raise HTTPException(status_code=400, detail="Feedback content is required")

    log.info(f"User Feedback Received [{category}]: {content}")

    # ── Save locally as backup ────────────────────────────────────────────────
    feedback_file = Path(__file__).parent / "feedback.json"
    feedback_entry = {
        "timestamp": time.time(),
        "category": category,
        "content": content,
        "contact": contact or None
    }
    try:
        data = []
        if feedback_file.exists():
            with open(feedback_file, "r") as f:
                data = json.load(f)
        data.append(feedback_entry)
        with open(feedback_file, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error(f"Failed to save feedback locally: {e}")

    # ── Send to Discord in background (non-blocking) ──────────────────────────
    if FEEDBACK_DISCORD_WEBHOOK:
        background_tasks.add_task(_send_feedback_to_discord, category, content, contact)

    return {"status": "ok"}


def _send_feedback_to_discord(category: str, content: str, contact: str):
    """Send a formatted feedback embed to Discord webhook. Runs in background."""
    import requests as req
    import time

    CATEGORY_COLORS = {
        "Bug":     0xef4444,   # red
        "Feature": 0x6366f1,   # indigo
        "General": 0x3b82f6,   # blue
    }
    CATEGORY_EMOJI = {
        "Bug":     "🐛",
        "Feature": "✨",
        "General": "💬",
    }

    color = CATEGORY_COLORS.get(category, 0x3b82f6)
    emoji = CATEGORY_EMOJI.get(category, "💬")

    fields = []
    if contact:
        fields.append({"name": "Contact", "value": contact, "inline": True})
    fields.append({"name": "Category", "value": f"{emoji} {category}", "inline": True})

    payload = {
        "embeds": [{
            "title": f"{emoji} New Primnox Feedback",
            "description": content,
            "color": color,
            "fields": fields,
            "footer": {"text": "Primnox Feedback System"},
            "timestamp": __import__('datetime').datetime.utcnow().isoformat()
        }]
    }

    try:
        resp = req.post(FEEDBACK_DISCORD_WEBHOOK, json=payload, timeout=10)
        if resp.status_code not in (200, 204):
            log.warning(f"Discord webhook returned {resp.status_code}: {resp.text}")
        else:
            log.info("Feedback delivered to Discord.")
    except Exception as e:
        log.error(f"Failed to send feedback to Discord: {e}")



import threading
from profiler import run_background_profiler

@app.post("/api/profile/analyze")
async def analyze_profile():
    # Run in background to avoid blocking
    threading.Thread(target=run_background_profiler).start()
    return {"status": "started"}


from emotion_agent import run_emotion_analysis

@app.post("/api/emotion/analyze")
async def analyze_emotion():
    threading.Thread(target=run_emotion_analysis).start()
    return {"status": "started"}


# ── Reminders ──────────────────────────────────────────────────────────────────
from reminder_manager import list_reminders, add_reminder as _add_reminder

@app.get("/api/reminders")
async def get_reminders():
    """Return all pending reminders with seconds remaining."""
    return {"reminders": list_reminders()}

@app.post("/api/reminders")
async def create_reminder(request: Request):
    """Manually set a reminder: {message, delay_secs}"""
    body = await request.json()
    message = body.get("message", "reminder")
    delay = int(body.get("delay_secs", 300))
    _add_reminder(message, delay)
    return {"status": "ok", "message": message, "delay_secs": delay}


@app.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str):
    """Cancel a pending reminder by its stable id."""
    from reminder_manager import cancel_reminder_by_id
    ok = cancel_reminder_by_id(reminder_id)
    return {"status": "ok" if ok else "not_found"}


# ── Backup ─────────────────────────────────────────────────────────────────────
@app.post("/api/backup")
async def trigger_backup(background_tasks: BackgroundTasks):
    """
    Zip memory.db + chat.db + settings.json into
    %APPDATA%/primnox_extension/backups/backup_YYYYMMDD_HHMMSS.zip
    and broadcast backup_complete / backup_failed.
    """
    background_tasks.add_task(_run_backup)
    return {"status": "started"}

def _run_backup():
    import zipfile, time as _time
    from settings_manager import get_appdata_dir
    try:
        appdata = get_appdata_dir()
        backups_dir = appdata / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        stamp = _time.strftime("%Y%m%d_%H%M%S")
        zip_path = backups_dir / f"backup_{stamp}.zip"

        files_to_backup = [
            appdata / "memory.db",
            appdata / "chat.db",
            appdata / "settings.json",
        ]

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in files_to_backup:
                if fp.exists():
                    zf.write(fp, fp.name)

        # Keep only the 5 most recent backups
        all_backups = sorted(backups_dir.glob("backup_*.zip"), reverse=True)
        for old in all_backups[5:]:
            try:
                old.unlink()
            except Exception:
                pass

        size_kb = zip_path.stat().st_size // 1024
        log.info(f"Backup complete: {zip_path.name} ({size_kb} KB)")
        broadcast("backup_complete", {"path": str(zip_path), "size_kb": size_kb})
    except Exception as e:
        log.error(f"Backup failed: {e}")
        broadcast("backup_failed", {"error": str(e)})


# ── Skills ─────────────────────────────────────────────────────────────────────

@app.get("/api/skills")
async def get_skills():
    """Return all registered skills with name, description, and trigger words."""
    from skills.skill_router import list_skills
    return {"skills": list_skills()}


# ── Memory search ──────────────────────────────────────────────────────────────

@app.get("/api/memories")
async def get_memories_list():
    """Return all stored memories (non-stale)."""
    from memory import list_memories
    return {"memories": list_memories()}


@app.get("/api/memories/search")
async def search_memories_api(q: str = "", limit: int = 20):
    """Semantic full-text search over stored memories."""
    if not q.strip():
        from memory import list_memories
        return {"memories": list_memories()[:limit], "query": q}
    from memory import search_memories
    results = search_memories(q.strip(), limit=limit)
    return {"memories": results, "query": q}


@app.post("/api/memories")
async def create_memory_api(request: Request):
    """Manually add a memory. Body: {text, category}"""
    from memory import add_memory
    body = await request.json()
    text = body.get("text", "").strip()
    category = body.get("category", "personal")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    ok = add_memory(text, category=category)
    return {"success": ok, "duplicate": not ok}


@app.delete("/api/memories/{key}")
async def delete_memory_api(key: str):
    """Delete a memory by its key."""
    from memory import delete_memory
    delete_memory(key)
    return {"status": "ok"}


# ── Notes search ───────────────────────────────────────────────────────────────

@app.get("/api/notes/search")
async def search_notes_api(q: str = "", limit: int = 20):
    """Full-text search over notes titles and bodies."""
    from notes_manager import search_notes, get_notes
    if not q.strip():
        notes = get_notes()[:limit]
        return {"notes": notes, "query": q}
    results = search_notes(q.strip(), limit=limit)
    return {"notes": results, "query": q}


# ── Research / web search ──────────────────────────────────────────────────────

@app.post("/api/research/deep")
async def deep_research_stream(request: Request):
    """
    Deep multi-round research with full page reading and gap analysis.
    Returns a Server-Sent Events stream of progress + final report.
    Body: { query: str, depth: 1|2|3 }
    """
    from fastapi.responses import StreamingResponse
    body  = await request.json()
    query = body.get("query", "").strip()
    depth = int(body.get("depth", 2))

    if not query:
        return {"error": "No query provided"}

    async def generate():
        try:
            from research_engine import DeepResearchEngine
            engine = DeepResearchEngine(query, depth)
            async for event in engine.run():
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            log.error(f"Deep research error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/research")
async def research_search(q: str = ""):
    """
    Run a DuckDuckGo web search and return structured results for the
    ResearchView frontend. Each result has title, url, body (snippet).
    """
    if not q.strip():
        return {"results": [], "query": q, "summary": ""}

    def _search():
        try:
            from ddgs import DDGS
            ddgs = DDGS()
            return list(ddgs.text(q.strip(), max_results=8))
        except Exception as e:
            log.error(f"Research search failed: {e}")
            return []

    results = await asyncio.to_thread(_search)

    # Ask LLM to produce a one-paragraph synthesis of the results
    summary = ""
    if results:
        def _summarize():
            from brain import think
            snippets = "\n".join(
                f"- {r.get('title', '')}: {r.get('body', '')[:200]}"
                for r in results[:5]
            )
            resp = think(
                f"Synthesize these web search results for the query '{q}' into a 2-3 sentence summary:\n{snippets}",
                system_override=(
                    "You are a research assistant. Write a concise, factual synthesis. "
                    "No preamble, no 'Here is a summary' — just the synthesis."
                )
            )
            return resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        try:
            summary = await asyncio.to_thread(_summarize)
        except Exception as e:
            log.warning(f"Research summarize failed: {e}")

    structured = [
        {
            "title": r.get("title", ""),
            "url": r.get("href", r.get("url", "")),
            "body": r.get("body", "")[:300],
        }
        for r in results
    ]
    return {"results": structured, "query": q, "summary": summary}

if __name__ == "__main__":
    loop_type = "asyncio"
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        loop_type = "uvloop"
        log.info("Forced high-performance event loop policy via uvloop.")
    except ImportError:
        log.info("uvloop not supported on this platform. Falling back to default asyncio loop policy.")

    config = uvicorn.Config(app=app, host="127.0.0.1", port=8000, loop=loop_type)
    server = uvicorn.Server(config)
    
    # Run uvicorn natively, it manages the loop
    server.run()

