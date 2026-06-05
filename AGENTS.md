# 🌌 Primnox AI Video Editor: Agent Coordination Spec (AGENTS.md)

This specification defines the architecture, workflow, and division of labor for implementing the **Primnox AI Video Editor**. Work is divided between **Claude Code** (Complex System Design, UI/UX Timeline, Motion Match Algorithms) and **Gemini 3.5 Flash** (FastAPI Boilerplate, FFmpeg Command Generation, AI Analytics Bindings, Unit Tests) under the orchestration of **Antigravity 2.0**.

---

## 🏗️ System Architecture

The video editor operates inside the existing Primnox application using a **Proxy-First Processing Pipeline**:

```
[User Video Upload] ──> [Proxy Generator (240p)] ──> [AI Analytics (MediaPipe/YOLO/Librosa)]
          │                                                    │
          ▼                                                    ▼
[Full-Res Source] ──────> [FFmpeg Splicing Engine] <────── [Edit Decision List (EDL)]
                                  │
                                  ▼
                        [Rendered Output Video]
```

1. **Proxy Pipeline**: Upon upload, the backend creates a low-res `240p` proxy file for fast local AI scanning. Timecodes remain resolution-independent, allowing analytical metadata to map perfectly to the high-res source.
2. **Edit Decision List (EDL)**: The frontend/LLM generates a standardized JSON array of cuts, scales, and audio offsets (the EDL).
3. **FFmpeg Splicing Engine**: A backend worker reads the high-res source and compiles the final video using FFmpeg command strings generated from the EDL.

---

## 👥 Division of Labor

### 🧠 Antigravity 2.0 (Orchestrator)
- Coordinates code merges, handles workspace directories, manages backups.
- Resolves conflicts between frontend layout parameters and backend capabilities.

### 💻 Claude Code (Architecture & Frontend UI)
*Focuses on high-complexity logic, interactive controls, and visual representation.*
1. **Frontend Timeline UI**:
   - Canvas-based multi-track timeline panel (Video Track, Audio Track, Subtitle/Text Track, Transitions Track).
   - Drag-and-drop handles for trimming, slicing, and positioning clips.
   - Interactive zoom keyframe controls and playhead tracker.
2. **Motion-Aware Transition Matching**:
   - Math for calculating normalized Euclidean distance & vector cosine similarity between MediaPipe pose endpoints.
   - 80% similarity threshold comparator logic for subject alignment.
3. **Primnox Integration**:
   - Registering IPC channels in `preload.js` and `electron.cjs` for video analytics and window controls.

### ⚡ Gemini 3.5 Flash (Backend Core & Analytical Wrappers)
*Focuses on high-speed data pipelines, CLI execution, tests, and API endpoints.*
1. **FastAPI Endpoints**:
   - POST `/api/video/upload` (accepts video, generates proxy).
   - GET/POST `/api/video/project` (save/load project state).
   - POST `/api/video/render` (takes EDL, runs rendering).
2. **FFmpeg Splicing Engine**:
   - Python module generating complex FFmpeg CLI arguments (split, concatenation, overlay, audio padding, setpts, zoompan).
3. **AI Analytics Bindings**:
   - **MediaPipe / OpenCV**: Bounding box extraction, optical flow motion vector calculation, and pose coordinates storage.
   - **Librosa**: Audio file extraction, onset/transient/beat tracking, and beat coordinate mapping.
   - **Whisper (via Groq)**: Transcribing proxy audio, parsing word-level timestamps, and returning dialogue gap intervals.
   - **YOLOv8 & Kalman Filter**: Object detection and bounding box center tracking with smoothing.
4. **Unit Tests**:
   - Writing tests to verify FFmpeg CLI string formatting and analytical math validity.

---

## 📥 IPC & REST API Specification

### 1. REST Endpoints
* **`POST /api/video/analyze`**: Runs analytical scan on a video. Returns JSON with beats, silent intervals, and frame-by-frame motion vectors.
* **`POST /api/video/render`**: Executes FFmpeg concatenation and rendering. Returns progress via WebSocket.

### 2. EDL Schema (JSON)
```json
{
  "project_id": "string",
  "source_video": "string",
  "timeline": [
    {
      "clip_id": "string",
      "start": 0.0,
      "end": 5.2,
      "speed": 1.0,
      "scale": 1.0,
      "position": {"x": 0, "y": 0},
      "audio_offset": 0.0,
      "transition": {
        "type": "none | whip_pan | cross_fade | match_cut",
        "duration": 0.5
      }
    }
  ]
}
```

---

## 📈 Verification Plan

1. **Analytical Accuracy**: Run tests comparing Librosa beat coordinates against known reference tracks.
2. **FFmpeg Validity**: Validate that generated FFmpeg commands compile and execute without throwing syntax or filter errors.
3. **End-to-End Test**: Verify video import → timeline trim → transition insert → final render output pipeline.
