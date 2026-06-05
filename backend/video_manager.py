import os
import sqlite3
import uuid
import json
import datetime
import threading
import traceback
from pathlib import Path
from audio_analyzer import analyze_audio
from video_analyzer import generate_proxy, analyze_video

# Setup logging
try:
    from logger import log
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("video_manager")

DB_FILE = "chat.db"

# WebSocket callback hook to prevent circular imports
_broadcast_callback = None

def register_broadcast_callback(callback):
    """Registers the WebSocket broadcast function from server.py"""
    global _broadcast_callback
    _broadcast_callback = callback
    log.info("WebSocket broadcast callback registered in video_manager.")

def broadcast_to_websockets(event_type: str, data: dict):
    """Sends a WebSocket event to the frontend UI if registered."""
    if _broadcast_callback:
        try:
            _broadcast_callback(event_type, data)
        except Exception as e:
            log.error(f"Failed to execute WebSocket broadcast callback: {e}")

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_video_db():
    """Initializes the SQLite tables in chat.db for video project persistence."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS video_projects (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_path TEXT NOT NULL,
            proxy_path TEXT NOT NULL,
            status TEXT NOT NULL,
            progress REAL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            settings TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS video_analytics (
            project_id TEXT PRIMARY KEY,
            beats TEXT,
            waveform TEXT,
            silences TEXT,
            motion_vectors TEXT,
            motion_angles TEXT,
            reframe_boxes TEXT,
            pose_trajectories TEXT,
            sample_fps INTEGER,
            duration REAL,
            FOREIGN KEY(project_id) REFERENCES video_projects(id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()
    log.info("Video project database tables initialized successfully.")

def update_project_status(project_id: str, status: str, progress: float, stage: str = None):
    """Updates the project's current status and triggers a WebSocket progress update."""
    conn = get_db()
    conn.execute("UPDATE video_projects SET status = ?, progress = ? WHERE id = ?", (status, progress, project_id))
    conn.commit()
    conn.close()
    
    if stage:
        broadcast_to_websockets("analysis_progress", {
            "project_id": project_id,
            "percentage": int(progress * 100),
            "stage": stage,
            "status": status
        })

def run_async_analysis(project_id: str, source_path: str):
    """Starts the sequential analysis pipeline inside a daemon background thread."""
    def worker():
        try:
            # Step 1: Proxy generation (0.0 to 0.25 progress)
            update_project_status(project_id, "processing", 0.05, "Generating proxy (240p)...")
            proxy_path = generate_proxy(source_path)
            
            conn = get_db()
            conn.execute("UPDATE video_projects SET proxy_path = ? WHERE id = ?", (proxy_path, project_id))
            conn.commit()
            conn.close()
            
            # Step 2: Audio analysis (0.25 to 0.6 progress)
            update_project_status(project_id, "processing", 0.30, "Detecting beats and dialogue silences...")
            audio_results = analyze_audio(source_path)
            
            # Step 3: Video analysis (0.6 to 0.9 progress)
            update_project_status(project_id, "processing", 0.60, "Running OpenCV motion and pose estimation...")
            video_results = analyze_video(proxy_path)
            
            # Step 4: Write to DB (0.9 to 1.0 progress)
            update_project_status(project_id, "processing", 0.90, "Finalizing project database index...")
            
            conn = get_db()
            conn.execute('''
                INSERT OR REPLACE INTO video_analytics 
                (project_id, beats, waveform, silences, motion_vectors, motion_angles, reframe_boxes, pose_trajectories, sample_fps, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                project_id,
                json.dumps(audio_results["beats"]),
                json.dumps(audio_results["waveform"]),
                json.dumps(audio_results["silences"]),
                json.dumps(video_results["motion_vectors"]),
                json.dumps(video_results["motion_angles"]),
                json.dumps(video_results["reframe_boxes"]),
                json.dumps(video_results["pose_trajectories"]),
                video_results["sample_fps"],
                video_results["duration"]
            ))
            conn.commit()
            conn.close()
            
            # Set to completed
            update_project_status(project_id, "completed", 1.0, "Completed")
            log.info(f"Video analysis for project {project_id} completed successfully.")
            
        except Exception as e:
            log.error(f"Video analysis background thread crashed: {traceback.format_exc()}")
            update_project_status(project_id, "failed", 0.0, f"Error: {str(e)}")
            
    threading.Thread(target=worker, daemon=True).start()

def create_project(source_path: str, title: str = None) -> str:
    """Creates a new video project entry and triggers async analytics scanning."""
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source video file not found at: {source_path}")

    project_id = str(uuid.uuid4())
    if not title:
        title = Path(source_path).stem

    # Ensure DB is created
    init_video_db()

    conn = get_db()
    conn.execute('''
        INSERT INTO video_projects (id, title, source_path, proxy_path, status, progress, created_at, settings)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        project_id,
        title,
        source_path,
        "",
        "processing",
        0.0,
        datetime.datetime.now().isoformat(),
        json.dumps({})
    ))
    conn.commit()
    conn.close()

    # Launch background thread
    run_async_analysis(project_id, source_path)
    return project_id

def get_project(project_id: str) -> dict:
    """Fetches a project state and merges its analytical arrays (if analysis is complete)."""
    conn = get_db()
    p = conn.execute("SELECT * FROM video_projects WHERE id = ?", (project_id,)).fetchone()
    if not p:
        conn.close()
        return None
        
    project = dict(p)
    try:
        project["settings"] = json.loads(project["settings"])
    except Exception:
        project["settings"] = {}
        
    # Load analytics
    a = conn.execute("SELECT * FROM video_analytics WHERE project_id = ?", (project_id,)).fetchone()
    if a:
        analytics = dict(a)
        project["analytics"] = {
            "beats": json.loads(analytics["beats"] or "[]"),
            "waveform": json.loads(analytics["waveform"] or "[]"),
            "silences": json.loads(analytics["silences"] or "[]"),
            "motion_vectors": json.loads(analytics["motion_vectors"] or "[]"),
            "motion_angles": json.loads(analytics["motion_angles"] or "[]"),
            "reframe_boxes": json.loads(analytics["reframe_boxes"] or "[]"),
            "pose_trajectories": json.loads(analytics["pose_trajectories"] or "[]"),
            "sample_fps": analytics["sample_fps"],
            "duration": analytics["duration"]
        }
    conn.close()
    return project

def list_projects() -> list:
    """Returns a list of all active video project sessions (excluding heavy analytics data)."""
    # Ensure DB tables are initialized
    init_video_db()
    
    conn = get_db()
    rows = conn.execute("SELECT id, title, source_path, status, progress, created_at FROM video_projects ORDER BY created_at DESC").fetchall()
    projects = [dict(r) for r in rows]
    conn.close()
    return projects

def delete_project(project_id: str):
    """Deletes the project, its database rows, and deletes its temporary 240p proxy file."""
    project = get_project(project_id)
    if project and project.get("proxy_path"):
        try:
            if os.path.exists(project["proxy_path"]):
                os.remove(project["proxy_path"])
                log.info(f"Deleted temporary proxy on disk: {project['proxy_path']}")
        except Exception as e:
            log.warning(f"Could not delete temporary proxy file: {e}")
            
    conn = get_db()
    conn.execute("DELETE FROM video_projects WHERE id = ?", (project_id,))
    conn.execute("DELETE FROM video_analytics WHERE project_id = ?", (project_id,))
    conn.commit()
    conn.close()
    log.info(f"Project {project_id} deleted successfully.")
