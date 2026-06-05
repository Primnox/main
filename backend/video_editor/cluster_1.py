from typing import List, Dict, Any

def beat_sync(audio_rms_data: List[Dict[str, float]], threshold: float = 0.5) -> Dict[str, Any]:
    """
    Beat Synchronization heuristic.
    Uses mock RMS audio thresholding to find beats.
    Returns OpenShot compatible cuts / split points.
    """
    cuts = []
    for data in audio_rms_data:
        if data.get("rms", 0.0) >= threshold:
            cuts.append(data.get("timestamp", 0.0))
            
    # Safe fallback
    if not cuts:
        cuts = [0.0]
        
    clips = []
    start = 0.0
    for cut in cuts:
        if cut > start:
            clips.append({"start": start, "end": cut})
            start = cut

    return {
        "status": "success",
        "heuristic": "beat_sync",
        "cuts": cuts,
        "clips": clips
    }

def speed_ramp(clip_start: float, clip_end: float) -> Dict[str, Any]:
    """
    Speed Ramp heuristic.
    Speeds up, slows down in the middle, and speeds up again.
    Returns OpenShot 'time' property keyframes.
    """
    duration = clip_end - clip_start
    if duration <= 0:
        return {"time": {"Points": []}}
        
    mid_start = clip_start + duration * 0.3
    mid_end = clip_start + duration * 0.7
    
    # Y represents the source time
    points = [
        {"co": {"X": clip_start, "Y": clip_start}, "interpolation": 0},
        {"co": {"X": mid_start, "Y": clip_start + duration * 0.4}, "interpolation": 0},
        {"co": {"X": mid_end, "Y": clip_start + duration * 0.6}, "interpolation": 0},
        {"co": {"X": clip_end, "Y": clip_end}, "interpolation": 1}
    ]
    
    return {"time": {"Points": points}}

def slow_motion(clip_start: float, clip_end: float, factor: float = 0.5) -> Dict[str, Any]:
    """
    Slow Motion & Ramps heuristic.
    Slows down the clip by the given factor.
    """
    duration = clip_end - clip_start
    if duration <= 0:
        return {"time": {"Points": []}}
        
    source_duration = duration * factor
    
    points = [
        {"co": {"X": clip_start, "Y": clip_start}, "interpolation": 1},
        {"co": {"X": clip_end, "Y": clip_start + source_duration}, "interpolation": 1}
    ]
    
    return {"time": {"Points": points}}

def hyperlapse(clip_start: float, clip_end: float, factor: float = 10.0) -> Dict[str, Any]:
    """
    Time Lapse / Hyperlapse heuristic.
    Speeds up the clip dramatically.
    """
    duration = clip_end - clip_start
    if duration <= 0:
        return {"time": {"Points": []}}
        
    source_duration = duration * factor
    
    points = [
        {"co": {"X": clip_start, "Y": clip_start}, "interpolation": 1},
        {"co": {"X": clip_end, "Y": clip_start + source_duration}, "interpolation": 1}
    ]
    
    return {"time": {"Points": points}}

def freeze_frame(freeze_time: float, duration: float = 2.0) -> Dict[str, Any]:
    """
    Freeze Frame heuristic.
    Holds a specific frame for a given duration.
    """
    points = [
        {"co": {"X": freeze_time, "Y": freeze_time}, "interpolation": 1},
        {"co": {"X": freeze_time + duration, "Y": freeze_time}, "interpolation": 1}
    ]
    
    return {"time": {"Points": points}}
