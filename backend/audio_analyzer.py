import os
import subprocess
import tempfile
import requests
import numpy as np
import librosa
from pathlib import Path

# Setup logging
try:
    from logger import log
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("audio_analyzer")

def extract_audio_from_video(video_path: str) -> str:
    """
    Extracts the audio track from a video file and saves it as a temporary WAV file.
    Returns the absolute path to the generated WAV file.
    """
    temp_dir = tempfile.gettempdir()
    output_wav = os.path.join(temp_dir, f"primnox_temp_audio_{os.path.basename(video_path)}.wav")
    
    # Overwrite if exists
    if os.path.exists(output_wav):
        try:
            os.remove(output_wav)
        except Exception:
            pass

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",                   # Disable video
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", "16000",          # 16kHz sample rate (good for Whisper & Librosa)
        "-ac", "1",              # Mono channel
        output_wav
    ]
    
    log.info(f"Extracting audio to WAV: {output_wav}")
    try:
        # Run ffmpeg command
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return output_wav
    except subprocess.CalledProcessError as e:
        log.error(f"FFmpeg audio extraction failed: {e.stderr}")
        raise RuntimeError(f"FFmpeg failed to extract audio: {e.stderr}")

def get_groq_api_key() -> str:
    """Helper to get the Groq API key from environment or keyring."""
    try:
        import keyring
        key = keyring.get_password("primnox", "groq_api_key")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("GROQ_API_KEY", "")

def transcribe_with_timestamps(audio_path: str) -> list:
    """
    Transcribes the audio file using Groq's Whisper API with segment-level timestamps.
    Returns a list of segment dictionaries or None if key is missing/failed.
    """
    api_key = get_groq_api_key()
    if not api_key:
        log.warning("Groq API key missing, skipping Whisper timestamp analysis.")
        return None

    try:
        log.info("Requesting segment-level transcription from Groq Whisper...")
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            data={
                "model": "whisper-large-v3-turbo",
                "response_format": "verbose_json"
            },
            timeout=30
        )
        if resp.status_code != 200:
            log.warning(f"Groq Whisper transcription failed with status {resp.status_code}: {resp.text}")
            return None

        res = resp.json()
        segments = res.get("segments", [])
        return segments
    except Exception as e:
        log.error(f"Groq Whisper transcription crashed: {e}", exc_info=True)
        return None

def detect_silences_local(y: np.ndarray, sr: int, threshold_db: float = -35.0, min_silence_len_s: float = 0.5) -> list:
    """
    Detects silent intervals in audio using local RMS dB analysis.
    Returns list of [start, end] seconds.
    """
    # 50ms windows with 50% overlap (25ms step)
    frame_length = int(sr * 0.05)
    hop_length = int(sr * 0.025)
    
    # Compute RMS energy
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    
    # Convert to decibels (dB)
    rms_db = librosa.amplitude_to_db(rms, ref=np.max)
    
    # Identify silence
    is_silent = rms_db < threshold_db
    
    silences = []
    in_silence = False
    silence_start = 0.0
    frame_time = hop_length / sr
    
    for idx, silent in enumerate(is_silent):
        current_time = idx * frame_time
        if silent and not in_silence:
            in_silence = True
            silence_start = current_time
        elif not silent and in_silence:
            in_silence = False
            duration = current_time - silence_start
            if duration >= min_silence_len_s:
                silences.append([round(silence_start, 2), round(current_time, 2)])
                
    if in_silence:
        total_duration = len(y) / sr
        duration = total_duration - silence_start
        if duration >= min_silence_len_s:
            silences.append([round(silence_start, 2), round(total_duration, 2)])
            
    return silences

def analyze_audio(video_or_audio_path: str) -> dict:
    """
    Extracts audio, performs beat tracking, builds downsampled waveform array (100 samples/sec),
    and identifies dialogue gaps/silences (using Whisper if key is present, local fallback otherwise).
    Returns dictionary with results:
    {
       "beats": [float],
       "waveform": [float],
       "silences": [[float, float]]
    }
    """
    is_video = Path(video_or_audio_path).suffix.lower() in [".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"]
    temp_wav = None
    
    try:
        if is_video:
            temp_wav = extract_audio_from_video(video_or_audio_path)
            load_path = temp_wav
        else:
            load_path = video_or_audio_path

        log.info(f"Loading audio path for Librosa analysis: {load_path}")
        y, sr = librosa.load(load_path, sr=None)
        duration = len(y) / sr
        
        # Beat Tracking
        log.info("Running beat-tracking analysis...")
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
        # Round beat timestamps for clean EDL snapping
        beat_times = [round(b, 3) for b in beat_times]
        
        # Waveform Downsampling (100 samples/sec)
        log.info("Downsampling audio amplitude for timeline waveform rendering...")
        hop_length = max(1, sr // 100)
        waveform = []
        for i in range(0, len(y), hop_length):
            block = y[i:i+hop_length]
            if len(block) > 0:
                waveform.append(float(np.max(np.abs(block))))
        
        # Silence Detection
        silences = None
        # Try Whisper segments if API key is present
        whisper_segments = transcribe_with_timestamps(load_path)
        if whisper_segments is not None:
            log.info("Computing dialogue gaps from Whisper segment timecodes...")
            silences = []
            last_end = 0.0
            for seg in whisper_segments:
                start = seg.get("start", 0.0)
                end = seg.get("end", 0.0)
                if start - last_end >= 0.5:
                    silences.append([round(last_end, 2), round(start, 2)])
                last_end = end
            if duration - last_end >= 0.5:
                silences.append([round(last_end, 2), round(duration, 2)])
        
        # Local energy fallback if Whisper was skipped or failed
        if not silences:
            log.info("Running local dB-energy silence detection...")
            silences = detect_silences_local(y, sr, threshold_db=-35.0, min_silence_len_s=0.5)

        # Energy Spikes for Zoom Punches
        log.info("Detecting energy spikes for Zoom Punch transitions...")
        rms = librosa.feature.rms(y=y)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
        threshold = np.mean(rms) + 2 * np.std(rms)
        energy_spikes = []
        for i in range(1, len(rms)-1):
            if rms[i] > threshold and rms[i] > rms[i-1] and rms[i] > rms[i+1]:
                energy_spikes.append(round(times[i], 3))

        return {
            "beats": beat_times,
            "waveform": waveform,
            "silences": silences,
            "audio_heuristics": {
                "energy_spikes": energy_spikes
            }
        }
        
    finally:
        # Clean up temporary WAV file
        if temp_wav and os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
                log.info(f"Cleaned up temporary WAV: {temp_wav}")
            except Exception as e:
                log.warning(f"Could not delete temp WAV file: {e}")
