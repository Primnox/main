def jump_cut(payload: dict) -> dict:
    """
    Heuristic: Keep only valid regions (remove silence/bad takes).
    Input:
    {
      "silences": [{"start": 1.0, "end": 2.5}, ...],
      "duration": 10.0
    }
    Output: OpenShot clips dict with split edits.
    """
    silences = payload.get("silences", [])
    duration = float(payload.get("duration", 0.0))
    
    # Safe fallback
    if not silences or duration <= 0:
        return {"clips": [{"start": 0.0, "end": duration}]}
        
    clips = []
    current_time = 0.0
    for s in sorted(silences, key=lambda x: float(x.get("start", 0))):
        start = float(s.get("start", 0))
        end = float(s.get("end", 0))
        if start > current_time:
            clips.append({"start": current_time, "end": start})
        current_time = max(current_time, end)
        
    if current_time < duration:
        clips.append({"start": current_time, "end": duration})
        
    return {"clips": clips}

def split_edit(payload: dict) -> dict:
    """
    J-Cuts & L-Cuts
    Input:
    {
      "cut_time": 5.0,
      "audio_offset": 1.0  # Positive for L-Cut, Negative for J-Cut
    }
    Output: OpenShot split edits required.
    """
    cut_time = float(payload.get("cut_time", 5.0))
    audio_offset = float(payload.get("audio_offset", 0.0))
    
    return {
        "clip_a": {
            "video_end": cut_time,
            "audio_end": cut_time + audio_offset
        },
        "clip_b": {
            "video_start": cut_time,
            "audio_start": cut_time + audio_offset
        }
    }

def smash_cut(payload: dict) -> dict:
    """
    Smash Cut: Instantaneous audio/video transition.
    Input: {"cut_time": 5.0}
    Output: volume drop keyframes.
    """
    cut_time = float(payload.get("cut_time", 5.0))
    
    return {
        "clip_a": {
            "volume": {
                "Points": [
                    {"co": {"X": cut_time - 0.01, "Y": 1.0}, "interpolation": 2}, # Constant
                    {"co": {"X": cut_time, "Y": 0.0}, "interpolation": 2}
                ]
            }
        },
        "clip_b": {
            "volume": {
                "Points": [
                    {"co": {"X": cut_time, "Y": 1.0}, "interpolation": 2}
                ]
            }
        }
    }

def cross_dissolve(payload: dict) -> dict:
    """
    Cross Dissolve: Fade out A, Fade in B.
    Input:
    {
        "clip_a_end": 10.0,
        "clip_b_start": 10.0,
        "overlap_duration": 2.0
    }
    """
    clip_a_end = float(payload.get("clip_a_end", 10.0))
    clip_b_start = float(payload.get("clip_b_start", 10.0))
    duration = float(payload.get("overlap_duration", 1.0))
    
    if duration <= 0:
        duration = 1.0 # Safe fallback
        
    a_fade_start = clip_a_end - duration
    b_fade_end = clip_b_start + duration
    
    return {
        "clip_a": {
            "alpha": {
                "Points": [
                    {"co": {"X": a_fade_start, "Y": 1.0}, "interpolation": 1}, # Linear
                    {"co": {"X": clip_a_end, "Y": 0.0}, "interpolation": 1}
                ]
            }
        },
        "clip_b": {
            "alpha": {
                "Points": [
                    {"co": {"X": clip_b_start, "Y": 0.0}, "interpolation": 1},
                    {"co": {"X": b_fade_end, "Y": 1.0}, "interpolation": 1}
                ]
            }
        }
    }

def montage(payload: dict) -> dict:
    """
    Montage: Cut clips to audio beats.
    Input:
    {
        "beats": [1.0, 2.5, 3.2, 4.0],
        "clips_duration": [5.0, 4.0, 6.0]
    }
    """
    beats = payload.get("beats", [])
    clips_duration = payload.get("clips_duration", [])
    
    if not beats or not clips_duration:
        return {"clips": []}
        
    results = []
    clip_idx = 0
    current_time = 0.0
    
    for beat in beats:
        beat = float(beat)
        if clip_idx >= len(clips_duration):
            break
        
        duration_needed = beat - current_time
        if duration_needed <= 0:
            continue
            
        clip_dur = float(clips_duration[clip_idx])
        actual_duration = min(duration_needed, clip_dur)
        
        results.append({
            "clip_index": clip_idx,
            "start": 0.0,
            "end": actual_duration,
            "placed_at": current_time
        })
        
        current_time += actual_duration
        clip_idx += 1
        
    return {"clips": results}
