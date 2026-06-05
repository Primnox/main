from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from .motion_match import find_match_cut
from .cluster_1 import beat_sync, speed_ramp, slow_motion, hyperlapse, freeze_frame
from .cluster_2 import whip_pan, zoom_punch, auto_reframe, motion_track, color_grade
from .cluster_3 import jump_cut, split_edit, smash_cut, cross_dissolve, montage

router = APIRouter(prefix="/api/video_editor", tags=["Video Editor Extension"])

class FrameData(BaseModel):
    timestamp_s: float
    landmarks: List[Dict[str, float]]

class MatchCutRequest(BaseModel):
    clip_a_frames: List[FrameData]
    clip_b_frames: List[FrameData]

class AudioRmsData(BaseModel):
    timestamp: float
    rms: float

class BeatSyncRequest(BaseModel):
    audio_rms_data: List[AudioRmsData]
    threshold: float = 0.5

class TimeRangeRequest(BaseModel):
    clip_start: float
    clip_end: float

class FactorTimeRangeRequest(BaseModel):
    clip_start: float
    clip_end: float
    factor: float

class FreezeFrameRequest(BaseModel):
    freeze_time: float
    duration: float = 2.0

@router.post("/match-cut")
async def process_match_cut(payload: MatchCutRequest):
    """
    Gemini: FastAPI endpoint for motion_match calculations.
    Batched data processing. Never runs MediaPipe here, only receives metadata.
    """
    a_frames = [f.dict() for f in payload.clip_a_frames]
    b_frames = [f.dict() for f in payload.clip_b_frames]
    
    result = find_match_cut(a_frames, b_frames)
    return result

@router.post("/beat-sync")
async def process_beat_sync(payload: BeatSyncRequest):
    """
    Endpoint for Beat Synchronization heuristic.
    """
    return beat_sync([d.dict() for d in payload.audio_rms_data], payload.threshold)

@router.post("/speed-ramp")
async def process_speed_ramp(payload: TimeRangeRequest):
    """
    Endpoint for Speed Ramp heuristic.
    """
    return speed_ramp(payload.clip_start, payload.clip_end)

@router.post("/slow-motion")
async def process_slow_motion(payload: FactorTimeRangeRequest):
    """
    Endpoint for Slow Motion heuristic.
    """
    return slow_motion(payload.clip_start, payload.clip_end, payload.factor)

@router.post("/hyperlapse")
async def process_hyperlapse(payload: FactorTimeRangeRequest):
    """
    Endpoint for Time Lapse / Hyperlapse heuristic.
    """
    return hyperlapse(payload.clip_start, payload.clip_end, payload.factor)

@router.post("/freeze-frame")
async def process_freeze_frame(payload: FreezeFrameRequest):
    """
    Endpoint for Freeze Frame heuristic.
    """
    return freeze_frame(payload.freeze_time, payload.duration)

@router.post("/whip-pan")
async def process_whip_pan(payload: Dict[str, Any]):
    return whip_pan(payload)

@router.post("/zoom-punch")
async def process_zoom_punch(payload: Dict[str, Any]):
    return zoom_punch(payload)

@router.post("/auto-reframe")
async def process_auto_reframe(payload: Dict[str, Any]):
    return auto_reframe(payload)

@router.post("/motion-track")
async def process_motion_track(payload: Dict[str, Any]):
    return motion_track(payload)

@router.post("/color-grade")
async def process_color_grade(payload: Dict[str, Any]):
    return color_grade(payload)

@router.post("/jump-cut")
async def process_jump_cut(payload: Dict[str, Any]):
    return jump_cut(payload)

@router.post("/split-edit")
async def process_split_edit(payload: Dict[str, Any]):
    return split_edit(payload)

@router.post("/smash-cut")
async def process_smash_cut(payload: Dict[str, Any]):
    return smash_cut(payload)

@router.post("/cross-dissolve")
async def process_cross_dissolve(payload: Dict[str, Any]):
    return cross_dissolve(payload)

@router.post("/montage")
async def process_montage(payload: Dict[str, Any]):
    return montage(payload)
