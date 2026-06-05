import os
import subprocess
import tempfile
import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO

# Setup logging
try:
    from logger import log
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("video_analyzer")

def generate_proxy(video_path: str, target_height: int = 240, target_fps: int = 24) -> str:
    """
    Generates a low-resolution proxy video file (e.g. 240p at 24fps)
    under the temporary directory for rapid AI processing.
    """
    temp_dir = tempfile.gettempdir()
    proxy_filename = f"primnox_proxy_{target_height}p_{os.path.basename(video_path)}"
    proxy_path = os.path.join(temp_dir, proxy_filename)

    # If it already exists, overwrite it
    if os.path.exists(proxy_path):
        try:
            os.remove(proxy_path)
        except Exception:
            pass

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"scale=-2:{target_height},fps={target_fps}", # Scale keeping aspect ratio, force FPS
        "-an", # Remove audio (we analyze audio separately)
        "-c:v", "libx264",
        "-crf", "28", # Fast compression
        "-preset", "faster",
        proxy_path
    ]

    log.info(f"Generating proxy: {proxy_path}")
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return proxy_path
    except subprocess.CalledProcessError as e:
        log.error(f"FFmpeg proxy generation failed: {e.stderr}")
        raise RuntimeError(f"FFmpeg failed to generate proxy: {e.stderr}")

def smooth_bounding_boxes(boxes: list, window_size: int = 7) -> list:
    """
    Applies a rolling average window to smooth bounding box coordinates
    and center coordinates to prevent camera jitter on auto-reframe.
    """
    smoothed = []
    n = len(boxes)
    for i in range(n):
        # Determine window boundaries
        start = max(0, i - window_size // 2)
        end = min(n, i + window_size // 2 + 1)
        
        window_boxes = [b for b in boxes[start:end] if b is not None]
        if not window_boxes:
            smoothed.append(None)
            continue
            
        # Average coordinates
        avg_box = np.mean(window_boxes, axis=0).tolist()
        smoothed.append(avg_box)
    return smoothed

def analyze_video(proxy_path: str, sample_fps: int = 6) -> dict:
    """
    Processes the proxy video frame-by-frame (sub-sampling at sample_fps to save CPU/GPU cycles).
    Performs:
    1. OpenCV Farneback Optical Flow (camera motion magnitude and angles)
    2. YOLOv8 human bounding box detection (for auto-reframe tracking)
    3. MediaPipe Pose landmarks extraction (for pose-aware match cuts)
    
    Returns:
    {
      "motion_vectors": [float],       # avg optical flow magnitude per sampled frame
      "motion_angles": [float],          # avg optical flow direction angle per sampled frame
      "reframe_boxes": [[x1, y1, x2, y2]], # smoothed person bounding boxes (normalized)
      "pose_trajectories": [[float]],  # flattened 3D landmarks relative to hips per sampled frame
      "sample_fps": int,
      "duration": float
    }
    """
    # Initialize YOLOv8 (loading local yolov8n.pt in backend directory)
    model_path = os.path.join(os.path.dirname(__file__), "yolov8n.pt")
    if not os.path.exists(model_path):
        model_path = "yolov8n.pt" # Check working directory
        
    log.info(f"Loading YOLOv8 model from {model_path}...")
    try:
        yolo_model = YOLO(model_path)
    except Exception as e:
        log.warning(f"Failed to load YOLOv8 model ({e}). Auto-reframe will be disabled.")
        yolo_model = None

    # Initialize MediaPipe Pose
    log.info("Initializing MediaPipe Pose tracker...")
    try:
        import mediapipe as mp
        mp_pose = mp.solutions.pose
        pose_tracker = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
    except Exception as e:
        log.error(f"Failed to initialize MediaPipe Pose: {e}")
        pose_tracker = None

    cap = cv2.VideoCapture(proxy_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open proxy video file: {proxy_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps
    
    # Calculate sub-sampling interval (e.g. process every 4th frame for 24fps video -> 6fps analysis)
    step = max(1, int(round(fps / sample_fps)))
    
    log.info(f"Analyzing proxy video: {width}x{height}, {fps} fps, {duration:.2f}s, sub-sampling step: {step}")

    motion_vectors = []
    motion_angles = []
    raw_reframe_boxes = []
    pose_trajectories = []

    prev_gray = None
    frame_idx = 0
    sampled_frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Process only sub-sampled frames
        if frame_idx % step == 0:
            sampled_frame_count += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # 1. Optical Flow Camera Motion Analysis
            flow_mag = 0.0
            flow_ang = 0.0
            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                flow_mag = float(np.mean(mag))
                flow_ang = float(np.mean(ang))
            
            motion_vectors.append(round(flow_mag, 3))
            motion_angles.append(round(flow_ang, 3))
            prev_gray = gray

            # 2. YOLOv8 Person Bounding Box Detection (Auto-Reframe)
            person_box = None
            if yolo_model is not None:
                results = yolo_model(frame, verbose=False)
                best_conf = 0.0
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    if cls_id == 0 and conf > 0.4: # Class 0 = Person
                        if conf > best_conf:
                            best_conf = conf
                            # Normalize coordinates to 0.0 - 1.0 range
                            xyxy = box.xyxy[0].tolist()
                            person_box = [
                                xyxy[0] / width,
                                xyxy[1] / height,
                                xyxy[2] / width,
                                xyxy[3] / height
                            ]
            raw_reframe_boxes.append(person_box)

            # 3. MediaPipe Pose Keypoints Estimation (Pose Matching)
            landmarks_flat = []
            if pose_tracker is not None:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pose_results = pose_tracker.process(rgb_frame)
                if pose_results.pose_landmarks:
                    # Extract 33 landmarks
                    raw_landmarks = pose_results.pose_landmarks.landmark
                    
                    # Normalize landmarks relative to hip center to align different heights
                    # Left Hip (23), Right Hip (24)
                    l_hip = raw_landmarks[23]
                    r_hip = raw_landmarks[24]
                    hip_center_x = (l_hip.x + r_hip.x) / 2.0
                    hip_center_y = (l_hip.y + r_hip.y) / 2.0
                    hip_center_z = (l_hip.z + r_hip.z) / 2.0

                    # Also calculate shoulder width for scaling
                    # Left Shoulder (11), Right Shoulder (12)
                    l_sho = raw_landmarks[11]
                    r_sho = raw_landmarks[12]
                    shoulder_dist = np.sqrt(
                        (l_sho.x - r_sho.x) ** 2 + 
                        (l_sho.y - r_sho.y) ** 2 + 
                        (l_sho.z - r_sho.z) ** 2
                    )
                    scale_factor = shoulder_dist if shoulder_dist > 0.01 else 1.0

                    for lm in raw_landmarks:
                        # Relativize and scale coordinates
                        norm_x = (lm.x - hip_center_x) / scale_factor
                        norm_y = (lm.y - hip_center_y) / scale_factor
                        norm_z = (lm.z - hip_center_z) / scale_factor
                        landmarks_flat.extend([round(norm_x, 3), round(norm_y, 3), round(norm_z, 3)])
                else:
                    # Fill with zeros if no pose found
                    landmarks_flat = [0.0] * 99 # 33 points * 3 coordinates
            pose_trajectories.append(landmarks_flat)

        frame_idx += 1

    cap.release()
    if pose_tracker is not None:
        pose_tracker.close()

    # Smooth the reframe boxes
    log.info("Smoothing bounding box coordinates for auto-reframe stabilization...")
    smoothed_boxes = smooth_bounding_boxes(raw_reframe_boxes, window_size=9)
    
    # Fill in missing boxes with default center frame if no subject detected
    final_boxes = []
    for box in smoothed_boxes:
        if box is None:
            # Default center box [left, top, right, bottom]
            final_boxes.append([0.35, 0.1, 0.65, 0.9])
        else:
            final_boxes.append(box)

    # Calculate Heuristics
    log.info("Calculating video heuristics for AI editing decisions...")
    static_scenes = []
    fast_scenes = []
    
    current_scene_type = None
    scene_start_frame = 0
    
    for i, mag in enumerate(motion_vectors):
        if mag < 0.5:
            scene_type = "static"
        elif mag > 3.0:
            scene_type = "fast"
        else:
            scene_type = "normal"
            
        if scene_type != current_scene_type:
            if current_scene_type == "static" and (i - scene_start_frame) > sample_fps * 2:
                static_scenes.append([round(scene_start_frame / sample_fps, 2), round(i / sample_fps, 2)])
            elif current_scene_type == "fast" and (i - scene_start_frame) > sample_fps:
                fast_scenes.append([round(scene_start_frame / sample_fps, 2), round(i / sample_fps, 2)])
                
            current_scene_type = scene_type
            scene_start_frame = i

    return {
        "motion_vectors": motion_vectors,
        "motion_angles": motion_angles,
        "reframe_boxes": final_boxes,
        "pose_trajectories": pose_trajectories,
        "video_heuristics": {
            "static_scenes": static_scenes,
            "fast_scenes": fast_scenes
        },
        "sample_fps": sample_fps,
        "duration": round(duration, 2)
    }
