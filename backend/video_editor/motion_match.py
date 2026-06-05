import numpy as np

def extract_and_normalize_pose(raw_landmarks):
    """
    Claude: Translates landmarks to hip-center origin and scales by shoulder width.
    Gemini: Added safe fallback if landmarks are missing.
    """
    if not raw_landmarks or len(raw_landmarks) < 33:
        return np.zeros(99) # Safe fallback
        
    # Extract hip center (MediaPipe conventions: 23=L_Hip, 24=R_Hip)
    l_hip = raw_landmarks[23]
    r_hip = raw_landmarks[24]
    hip_center_x = (l_hip['x'] + r_hip['x']) / 2.0
    hip_center_y = (l_hip['y'] + r_hip['y']) / 2.0
    hip_center_z = (l_hip['z'] + r_hip['z']) / 2.0

    # Shoulder distance for scaling (11=L_Sho, 12=R_Sho)
    l_sho = raw_landmarks[11]
    r_sho = raw_landmarks[12]
    shoulder_dist = np.sqrt(
        (l_sho['x'] - r_sho['x']) ** 2 + 
        (l_sho['y'] - r_sho['y']) ** 2 + 
        (l_sho['z'] - r_sho['z']) ** 2
    )
    scale_factor = shoulder_dist if shoulder_dist > 0.01 else 1.0

    flat_normalized = []
    for lm in raw_landmarks:
        norm_x = (lm['x'] - hip_center_x) / scale_factor
        norm_y = (lm['y'] - hip_center_y) / scale_factor
        norm_z = (lm['z'] - hip_center_z) / scale_factor
        flat_normalized.extend([norm_x, norm_y, norm_z])
        
    return np.array(flat_normalized)

def cosine_similarity(v1, v2):
    """Claude: 99-dimensional cosine similarity calculation."""
    dot = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

def find_match_cut(clip_a_frames: list, clip_b_frames: list) -> dict:
    """
    Claude/Gemini: Finds the earliest frame in B where similarity to A's final frame > 0.80.
    Input lists contain dicts with 'landmarks' and 'timestamp_s' (float seconds).
    """
    if not clip_a_frames or not clip_b_frames:
        # Safe fallback: cut exactly at the start of B
        return {"match_found": False, "cut_time_b": 0.0, "similarity": 0.0}

    # Use the final frame of Clip A as the target pose
    target_frame = clip_a_frames[-1]
    target_vector = extract_and_normalize_pose(target_frame.get('landmarks', []))
    
    if np.all(target_vector == 0):
        return {"match_found": False, "cut_time_b": float(clip_b_frames[0].get('timestamp_s', 0.0)), "similarity": 0.0}

    best_match_time = clip_b_frames[0].get('timestamp_s', 0.0)
    best_sim = 0.0
    
    for frame in clip_b_frames:
        b_vector = extract_and_normalize_pose(frame.get('landmarks', []))
        sim = cosine_similarity(target_vector, b_vector)
        
        if sim > 0.80:
            # 80% threshold reached!
            return {"match_found": True, "cut_time_b": float(frame.get('timestamp_s', 0.0)), "similarity": float(sim)}
            
        if sim > best_sim:
            best_sim = sim
            best_match_time = frame.get('timestamp_s', 0.0)
            
    # Fallback if no 80% match found
    return {"match_found": False, "cut_time_b": float(best_match_time), "similarity": float(best_sim)}
