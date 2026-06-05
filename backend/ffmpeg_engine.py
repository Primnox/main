import os
import json
import subprocess
import tempfile
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from video_manager import broadcast_to_websockets, get_project

# Setup logging
try:
    from logger import log
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("ffmpeg_engine")

def export_to_mlt(edl: dict, source_path: str, output_mlt_path: str, fps: float = 24.0):
    """
    Exports the EDL to a Shotcut/Kdenlive compatible MLT XML project file.
    """
    log.info(f"Exporting EDL to MLT XML: {output_mlt_path}")
    source_name = os.path.basename(source_path)
    
    # Calculate profile parameters
    width = 1920
    height = 1080
    
    root = ET.Element("mlt")
    
    # 1. Profile metadata
    profile = ET.SubElement(root, "profile")
    profile.set("id", "hd_1080_24p")
    profile.set("frame_rate_num", str(int(fps)))
    profile.set("frame_rate_den", "1")
    profile.set("width", str(width))
    profile.set("height", str(height))
    profile.set("progressive", "1")
    profile.set("sample_aspect_num", "1")
    profile.set("sample_aspect_den", "1")
    profile.set("display_aspect_num", "16")
    profile.set("display_aspect_den", "9")
    
    # 2. Main video source producer
    producer = ET.SubElement(root, "producer")
    producer.set("id", "producer_source")
    
    prop_res = ET.SubElement(producer, "property")
    prop_res.set("name", "resource")
    prop_res.text = str(Path(source_path).as_posix())
    
    # 3. Create playlists for each track
    # Group timeline clips by track index
    timeline_clips = edl.get("timeline", [])
    tracks = {}
    for clip in timeline_clips:
        track_idx = clip.get("track", 0)
        if track_idx not in tracks:
            tracks[track_idx] = []
        tracks[track_idx].append(clip)
        
    playlists = []
    for track_idx in sorted(tracks.keys()):
        playlist = ET.SubElement(root, "playlist")
        playlist_id = f"playlist_track_{track_idx}"
        playlist.set("id", playlist_id)
        playlists.append(playlist_id)
        
        # Sort clips on track by start_time
        clips = sorted(tracks[track_idx], key=lambda x: x.get("start_time", 0.0))
        
        current_time = 0.0
        for clip in clips:
            start_t = clip.get("start_time", 0.0)
            in_p = clip.get("in_point", 0.0)
            out_p = clip.get("out_point", 0.0)
            
            # If there is a gap, insert a blank/silence entry
            if start_t > current_time:
                blank_len_frames = int((start_t - current_time) * fps)
                blank = ET.SubElement(playlist, "blank")
                blank.set("length", str(blank_len_frames))
                
            in_frame = int(in_p * fps)
            out_frame = int(out_p * fps)
            
            entry = ET.SubElement(playlist, "entry")
            entry.set("producer", "producer_source")
            entry.set("in", str(in_frame))
            entry.set("out", str(out_frame))
            
            # Speed/Volume properties if set
            speed = clip.get("speed", 1.0)
            if speed != 1.0:
                # MLT uses warp filter for speed
                filter_warp = ET.SubElement(entry, "filter")
                filter_warp.set("id", "speed_warp")
                prop_warp = ET.SubElement(filter_warp, "property")
                prop_warp.set("name", "warp_speed")
                prop_warp.text = str(speed)
                
            volume = clip.get("volume", 1.0)
            if volume != 1.0 or clip.get("muted", False):
                filter_gain = ET.SubElement(entry, "filter")
                filter_gain.set("id", "gain")
                prop_gain = ET.SubElement(filter_gain, "property")
                prop_gain.set("name", "level")
                prop_gain.text = "0" if clip.get("muted", False) else str(volume)
                
            current_time = start_t + ((out_p - in_p) / speed)
            
    # 4. Tractor combining tracks
    tractor = ET.SubElement(root, "tractor")
    tractor.set("id", "main_tractor")
    
    multitrack = ET.SubElement(tractor, "multitrack")
    for pl_id in playlists:
        track_ref = ET.SubElement(multitrack, "track")
        track_ref.set("producer", pl_id)
        
    # Write XML string
    tree = ET.ElementTree(root)
    # Format XML nicely
    ET.indent(tree, space="  ", level=0)
    tree.write(output_mlt_path, encoding="utf-8", xml_declaration=True)
    log.info("MLT XML exported successfully.")

def generate_openshot_keyframe(start_val, end_val, duration_frames):
    """Helper to generate OpenShot bezier keyframe objects."""
    return {
        "Points": [
            {"co": {"X": 1.0, "Y": float(start_val)}, "interpolation": 2},
            {"co": {"X": float(duration_frames), "Y": float(end_val)}, "interpolation": 2}
        ]
    }

def export_to_openshot(edl: dict, source_path: str, output_osp_path: str):
    """
    Exports the EDL to an OpenShot .osp project JSON file, supporting
    advanced AI-driven effects (cross dissolve, zoom punch, speed ramp).
    """
    log.info(f"Exporting EDL to OpenShot JSON: {output_osp_path}")
    source_name = os.path.basename(source_path)
    file_id = "F1"
    
    fps_num = 24
    
    osp = {
        "width": 1920,
        "height": 1080,
        "fps": {"num": fps_num, "den": 1},
        "display_ratio": {"num": 16, "den": 9},
        "pixel_ratio": {"num": 1, "den": 1},
        "files": [
            {
                "id": file_id,
                "path": str(Path(source_path).as_posix()),
                "name": source_name,
                "media_type": "video",
                "width": 1920,
                "height": 1080,
                "duration": edl.get("duration", 60.0)
            }
        ],
        "clips": [],
        "layers": [
            {"id": "L0", "label": "Track 0", "number": 0},
            {"id": "L1", "label": "Track 1", "number": 1},
            {"id": "L2", "label": "Track 2", "number": 2}
        ]
    }
    
    for idx, clip in enumerate(edl.get("timeline", [])):
        in_p = clip.get("in_point", 0.0)
        out_p = clip.get("out_point", 0.0)
        start_t = clip.get("start_time", 0.0)
        track = clip.get("track", 0)
        speed = clip.get("speed", 1.0)
        duration_s = (out_p - in_p) / speed
        duration_frames = max(2, int(duration_s * fps_num))
        
        effects = clip.get("effects", [])
        
        scale_x = clip.get("scale", 1.0)
        scale_y = clip.get("scale", 1.0)
        alpha = 1.0
        time_prop = 0.0
        
        if "zoom_punch" in effects:
            scale_x = generate_openshot_keyframe(1.0, 1.5, duration_frames)
            scale_y = generate_openshot_keyframe(1.0, 1.5, duration_frames)
            
        if "cross_dissolve" in effects:
            alpha = generate_openshot_keyframe(0.0, 1.0, duration_frames)
            
        if "speed_ramp" in effects:
            time_prop = generate_openshot_keyframe(0.0, duration_s, duration_frames)
            
        if "j_cut" in effects or "l_cut" in effects:
            osp["clips"].append({
                "id": f"clip_{idx}_audio",
                "file_id": file_id,
                "position": start_t - 1.0 if "j_cut" in effects else start_t,
                "start": in_p,
                "end": out_p,
                "layer": track + 1,
                "speed": speed,
                "volume": clip.get("volume", 1.0),
                "alpha": 0.0,
                "scale_x": 1.0,
                "scale_y": 1.0
            })
            volume = 0.0
        else:
            volume = 0.0 if clip.get("muted", False) else clip.get("volume", 1.0)
        
        osp_clip = {
            "id": f"clip_{idx}",
            "file_id": file_id,
            "position": start_t,
            "start": in_p,
            "end": out_p,
            "layer": track,
            "speed": speed,
            "volume": volume,
            "alpha": alpha,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "location_x": clip.get("position", {}).get("x", 0.0),
            "location_y": clip.get("position", {}).get("y", 0.0),
            "time": time_prop
        }
        osp["clips"].append(osp_clip)
        
    with open(output_osp_path, "w", encoding="utf-8") as f:
        json.dump(osp, f, indent=2)
    log.info("OpenShot OSP JSON exported successfully.")

def render_edl_direct(edl: dict, source_path: str, output_path: str):
    """
    Renders an EDL timeline directly into a final MP4 video file.
    Processes clip-by-clip to avoid command line limits,
    then combines clips using the FFmpeg concat demuxer.
    """
    project_id = edl.get("project_id", "render")
    timeline = edl.get("timeline", [])
    
    if not timeline:
        log.warning("Empty timeline passed to render engine.")
        return
        
    temp_dir = tempfile.mkdtemp()
    log.info(f"Direct rendering starting in temp folder: {temp_dir}")
    
    try:
        temp_clips = []
        total_clips = len(timeline)
        
        for idx, clip in enumerate(timeline):
            # Update percentage
            progress_val = int((idx / total_clips) * 90) # 0 to 90% for clip processing
            broadcast_to_websockets("render_progress", {
                "project_id": project_id,
                "percentage": progress_val,
                "status": "rendering"
            })
            
            in_p = clip.get("in_point", 0.0)
            out_p = clip.get("out_point", 0.0)
            speed = clip.get("speed", 1.0)
            volume = clip.get("volume", 1.0)
            muted = clip.get("muted", False)
            scale = clip.get("scale", 1.0)
            
            clip_duration = (out_p - in_p) / speed
            temp_clip_path = os.path.join(temp_dir, f"segment_{idx:03d}.mp4")
            
            # Build filters
            v_filters = []
            if scale != 1.0:
                v_filters.append(f"scale=iw*{scale}:ih*{scale}")
            if speed != 1.0:
                # setpts controls frame rate timing
                v_filters.append(f"setpts={1.0/speed}*PTS")
                
            a_filters = []
            if muted:
                a_filters.append("volume=0")
            elif volume != 1.0:
                a_filters.append(f"volume={volume}")
            if speed != 1.0:
                # atempo controls audio speed (must be between 0.5 and 2.0; chain if extreme)
                rem_speed = speed
                while rem_speed > 2.0:
                    a_filters.append("atempo=2.0")
                    rem_speed /= 2.0
                while rem_speed < 0.5:
                    a_filters.append("atempo=0.5")
                    rem_speed /= 0.5
                a_filters.append(f"atempo={rem_speed}")

            # Run FFmpeg command for this segment
            cmd = ["ffmpeg", "-y", "-ss", f"{in_p:.3f}", "-to", f"{out_p:.3f}", "-i", source_path]
            
            if v_filters:
                cmd.extend(["-vf", ",".join(v_filters)])
            if speed != 1.0:
                # Force re-encoding frames if speed is changed
                cmd.extend(["-c:v", "libx264"])
            else:
                cmd.extend(["-c:v", "libx264"])
                
            if a_filters:
                cmd.extend(["-af", ",".join(a_filters)])
                cmd.extend(["-c:a", "aac"])
            else:
                cmd.extend(["-c:a", "aac"])
                
            cmd.extend([
                "-preset", "faster",
                "-crf", "22",
                temp_clip_path
            ])
            
            log.info(f"Rendering clip segment {idx + 1}/{total_clips}: {cmd}")
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            temp_clips.append(temp_clip_path)
            
        # Create concat index text file
        concat_txt_path = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_txt_path, "w", encoding="utf-8") as f:
            for clip_path in temp_clips:
                # FFmpeg concat demuxer expects forward slashes and escaped single quotes
                normalized_path = Path(clip_path).as_posix()
                f.write(f"file '{normalized_path}'\n")
                
        # Final Concatenate
        broadcast_to_websockets("render_progress", {
            "project_id": project_id,
            "percentage": 92,
            "status": "rendering"
        })
        
        # Ensure output parent directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_txt_path,
            "-c", "copy", # Copy without re-encoding the concatenated clips (fast!)
            output_path
        ]
        
        log.info(f"Concatenating all segments into final video: {concat_cmd}")
        subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        
        # Complete
        broadcast_to_websockets("render_progress", {
            "project_id": project_id,
            "percentage": 100,
            "status": "done"
        })
        log.info(f"Direct render finished successfully! Saved to {output_path}")
        
    except Exception as e:
        log.error(f"Render failed: {traceback.format_exc()}")
        broadcast_to_websockets("render_progress", {
            "project_id": project_id,
            "percentage": 0,
            "status": "error"
        })
        raise e
        
    finally:
        # Clean up temporary segments
        log.info("Cleaning up temporary render segment files...")
        for clip in temp_clips:
            if os.path.exists(clip):
                try:
                    os.remove(clip)
                except Exception:
                    pass
        try:
            if os.path.exists(concat_txt_path):
                os.remove(concat_txt_path)
            os.rmdir(temp_dir)
        except Exception:
            pass
