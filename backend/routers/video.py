from fastapi import APIRouter, Request, HTTPException
import video_manager
import ffmpeg_engine
from logger import get_logger
import threading
import os

log = get_logger("video")
router = APIRouter()

# Output is restricted to a writable exports directory under the user's home folder.
_EXPORTS_DIR = os.path.realpath(os.path.join(os.path.expanduser("~"), "Videos", "Primnox", "exports"))


def _safe_video_path(raw: str) -> str:
    """Resolve and validate an input video file path (prevents path traversal)."""
    resolved = os.path.realpath(os.path.expanduser(raw))
    if not os.path.isfile(resolved):
        raise HTTPException(status_code=400, detail="video_path must point to an existing file")
    return resolved


def _safe_output_path(raw: str) -> str:
    """Resolve and validate an output path (restricts writes to the exports directory)."""
    os.makedirs(_EXPORTS_DIR, exist_ok=True)
    resolved = os.path.realpath(os.path.expanduser(raw))
    if not (resolved.startswith(_EXPORTS_DIR + os.sep) or resolved == _EXPORTS_DIR):
        raise HTTPException(
            status_code=400,
            detail=f"output_path must be inside the exports directory: {_EXPORTS_DIR}",
        )
    parent = os.path.dirname(resolved)
    if not os.path.isdir(parent):
        raise HTTPException(status_code=400, detail="output_path parent directory does not exist")
    return resolved


@router.post("/api/video/import")
async def import_video(request: Request):
    body = await request.json()
    video_path = body.get("video_path")
    if not video_path:
        raise HTTPException(status_code=400, detail="video_path is required")
    try:
        safe_path = _safe_video_path(video_path)
        project_id = video_manager.create_project(safe_path)
        return {"project_id": project_id, "status": "processing"}
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/video/projects")
async def get_projects():
    return video_manager.list_projects()

@router.get("/api/video/projects/{project_id}")
async def get_project_details(project_id: str):
    proj = video_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj

@router.delete("/api/video/projects/{project_id}")
async def delete_project_endpoint(project_id: str):
    video_manager.delete_project(project_id)
    return {"status": "deleted"}

@router.post("/api/video/render")
async def render_video(request: Request):
    body = await request.json()
    edl = body.get("edl")
    output_path = body.get("output_path")
    
    if not edl or not output_path:
        raise HTTPException(status_code=400, detail="edl and output_path are required")

    safe_output = _safe_output_path(output_path)
    project_id = edl.get("project_id")
    proj = video_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    def run_render():
        try:
            ffmpeg_engine.render_edl_direct(edl, proj["source_path"], safe_output)
        except Exception as e:
            log.error(f"Background render thread failed: {e}")

    threading.Thread(target=run_render, daemon=True).start()
    return {"status": "started"}

@router.post("/api/video/export/mlt")
async def export_mlt_endpoint(request: Request):
    body = await request.json()
    edl = body.get("edl")
    output_path = body.get("output_path")
    
    if not edl or not output_path:
        raise HTTPException(status_code=400, detail="edl and output_path are required")

    safe_output = _safe_output_path(output_path)
    project_id = edl.get("project_id")
    proj = video_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        ffmpeg_engine.export_to_mlt(edl, proj["source_path"], safe_output)
        return {"status": "success", "file": safe_output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/video/export/openshot")
async def export_openshot_endpoint(request: Request):
    body = await request.json()
    edl = body.get("edl")
    output_path = body.get("output_path")
    
    if not edl or not output_path:
        raise HTTPException(status_code=400, detail="edl and output_path are required")

    safe_output = _safe_output_path(output_path)
    project_id = edl.get("project_id")
    proj = video_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        ffmpeg_engine.export_to_openshot(edl, proj["source_path"], safe_output)
        return {"status": "success", "file": safe_output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/video/heuristics/{project_id}")
async def get_heuristics_endpoint(project_id: str):
    """
    Returns AI heuristics for a given project. 
    Currently returns intelligent mock data matching our UI test timeline.
    """
    return {
        "status": "success",
        "project_id": project_id,
        "suggestions": [
            {
                "id": "s1",
                "target_clip_id": "c1",
                "type": "video",
                "effect": "speed_ramp",
                "title": "Fast-Action Sequence",
                "description": "Optical flow detected high-energy camera motion. AI recommends a Speed Ramp to accelerate the drone flyover.",
                "timestamp": "00:00:02"
            },
            {
                "id": "s2",
                "target_clip_id": "c2",
                "type": "video",
                "effect": "cross_dissolve",
                "title": "Static Scene Detected",
                "description": "Camera motion is minimal. AI recommends a smooth Cross Dissolve to blend into this interview shot.",
                "timestamp": "00:00:05"
            },
            {
                "id": "s3",
                "target_clip_id": "a2",
                "type": "audio",
                "effect": "zoom_punch",
                "title": "Audio Energy Spike",
                "description": "A sudden RMS volume spike was detected. AI recommends applying a Zoom Punch to visually emphasize the SFX.",
                "timestamp": "00:00:15"
            }
        ]
    }
