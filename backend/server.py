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

from routers import chats, notes, video
app.include_router(chats.router)
app.include_router(notes.router)
app.include_router(video.router)

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
from pubsub import broadcast, broker

core.register_broadcast_callback(broadcast)

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("WebSocket client connected")
    
    queue = broker.subscribe()
    try:
        # Send initial states to client immediately
        await ws.send_text(json.dumps({"type": "mic_state", "data": {"muted": core.mic_muted}}))
        await ws.send_text(json.dumps({"type": "incognito_changed", "data": {"active": core.incognito}}))
        await ws.send_text(json.dumps({"type": "settings_updated", "data": core.settings}))
        
        async def read_from_ws():
            try:
                while True:
                    await ws.receive_text()
                    await ws.send_text(json.dumps({"type": "pong", "data": {}}))
            except WebSocketDisconnect:
                pass
                
        async def write_to_ws():
            try:
                while True:
                    msg = await queue.get()
                    await ws.send_text(msg)
            except WebSocketDisconnect:
                pass
                
        read_task = asyncio.create_task(read_from_ws())
        write_task = asyncio.create_task(write_to_ws())
        
        done, pending = await asyncio.wait(
            [read_task, write_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
            
    except Exception as e:
        log.info(f"WebSocket client disconnected: {e}")
    finally:
        broker.unsubscribe(queue)

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

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.0.2-alpha"}

@app.get("/logs")
async def get_logs(limit: int = 200, level: str = "all"):
    return get_log_buffer(limit=limit, level=level)

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

@app.get("/memory")
async def get_memory():
    from memory import get_memory
    return get_memory()

@app.delete("/memory/{key}")
async def delete_memory(key: str):
    from memory import delete_memory
    delete_memory(key)
    return {"success": True}

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
    broker.set_loop(asyncio.get_running_loop())
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


# ==========================================
# Primnox AI Video Editor API Endpoints
# ==========================================
import video_manager
import ffmpeg_engine

# Initialize database and register WS broadcast callback
video_manager.init_video_db()
video_manager.register_broadcast_callback(broadcast)

