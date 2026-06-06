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
from observer import start_clipboard_monitor, clear_clipboard_data, register_observer_callback

app = FastAPI()

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
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
        
    text = body.get("text", "")
    session_id = body.get("sessionId", "current")
    log.info(f"Received message: {text[:50]}...")
    # Use BackgroundTasks to prevent blocking the async loop
    background_tasks.add_task(core.handle_text_input, text, session_id=session_id)
    return {"status": "ok"}

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

@app.post("/api/chats/{session_id}/auto_assign")
async def auto_assign_chat(session_id: str):
    from chat_manager import get_session_messages, update_session, get_db
    from brain import think
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, title FROM folders')
    folders = [{"id": r["id"], "title": r["title"]} for r in c.fetchall()]
    conn.close()
    
    msgs = get_session_messages(session_id)[-20:]
    chat_text = "\n".join([f"{m['speaker']}: {m['text']}" for m in msgs])
    
    folder_list = "\n".join([f"- ID: {f['id']}, Name: {f['title']}" for f in folders])
    
    prompt = f"Analyze the following chat and assign it to the most relevant folder from the list below. Return ONLY the exact folder ID string and nothing else.\n\nFolders:\n{folder_list}\n\nChat:\n{chat_text}"
    
    result = think(prompt)
    chosen_id = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    
    if chosen_id in [f["id"] for f in folders]:
        update_session(session_id, folder_id=chosen_id)
        return {"status": "ok", "folder_id": chosen_id}
        
    return {"status": "failed", "reason": "AI did not return a valid folder id", "raw": chosen_id}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.0.7-alpha"}

@app.get("/api/dashboard")
async def get_dashboard():
    from pathlib import Path
    import datetime
    from notes_manager import get_notes
    from memory import list_memories

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
            meetings.append({
                "name": d.name,
                "has_summary": has_summary,
                "summary_preview": preview
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
    }

@app.get("/api/ollama/status")
async def ollama_status():
    """Returns Ollama running status + list of installed models."""
    from brain import get_ollama_status
    from settings_manager import load_settings
    s = load_settings()
    base_url = s.get("ollama_base_url", "http://localhost:11434")
    return get_ollama_status(base_url)

@app.post("/api/daily_brief")
async def post_daily_brief(background_tasks: BackgroundTasks):
    """Trigger daily debrief generation — result is broadcast via WS."""
    background_tasks.add_task(core.feed.generate_daily_debrief)
    return {"status": "generating"}

@app.get("/logs")
async def get_logs(limit: int = 200, level: str = "all"):
    return get_log_buffer(limit=limit, level=level)

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

@app.post("/tasks/{id}/complete")
async def complete_task(id: int):
    from notes_manager import complete_task
    return {"success": complete_task(id)}

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
        # Extract JSON if it contains markdown formatting
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
            
        llm_data = json.loads(response)
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
    log.info("Primnox Startup Complete - Event loop and clipboard monitor initialized.")

@app.post("/api/feedback")
async def receive_feedback(request: Request):
    import time
    from pathlib import Path
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    category = body.get("category", "General")
    content = body.get("content", "")
    contact = body.get("contact", "")

    log.info(f"User Feedback Received [{category}]: {content}")
    feedback_file = Path(__file__).parent / "feedback.json"

    feedback_entry = {
        "timestamp": time.time(),
        "category": category,
        "content": content,
        "contact": contact
    }

    try:
        if feedback_file.exists():
            with open(feedback_file, "r") as f:
                data = json.load(f)
        else:
            data = []
        data.append(feedback_entry)
        with open(feedback_file, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error(f"Failed to save feedback: {e}")

    return {"status": "ok"}

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
