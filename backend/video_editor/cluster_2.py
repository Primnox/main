from typing import List, Dict, Any

def whip_pan(data: Dict[str, Any]) -> Dict[str, Any]:
    duration = float(data.get("duration_s", 1.0))
    return {
        "location_x": {
            "Points": [
                {"co": {"X": 1.0, "Y": 0.0}, "interpolation": 1},
                {"co": {"X": 1.0 + (duration / 2), "Y": 1.0}, "interpolation": 2},
                {"co": {"X": 1.0 + duration, "Y": 0.0}, "interpolation": 1}
            ]
        }
    }

def zoom_punch(data: Dict[str, Any]) -> Dict[str, Any]:
    duration = float(data.get("duration_s", 1.0))
    zoom_factor = float(data.get("zoom_factor", 1.5))
    return {
        "scale_x": {
            "Points": [
                {"co": {"X": 1.0, "Y": 1.0}, "interpolation": 1},
                {"co": {"X": 1.0 + 0.1, "Y": zoom_factor}, "interpolation": 2},
                {"co": {"X": 1.0 + duration, "Y": 1.0}, "interpolation": 1}
            ]
        },
        "scale_y": {
            "Points": [
                {"co": {"X": 1.0, "Y": 1.0}, "interpolation": 1},
                {"co": {"X": 1.0 + 0.1, "Y": zoom_factor}, "interpolation": 2},
                {"co": {"X": 1.0 + duration, "Y": 1.0}, "interpolation": 1}
            ]
        }
    }

def auto_reframe(data: Dict[str, Any]) -> Dict[str, Any]:
    subject_x = float(data.get("subject_x", 0.5))
    return {
        "location_x": {
            "Points": [
                {"co": {"X": 1.0, "Y": subject_x - 0.5}, "interpolation": 1}
            ]
        }
    }

def motion_track(data: Dict[str, Any]) -> Dict[str, Any]:
    start_x = float(data.get("start_x", 0.0))
    end_x = float(data.get("end_x", 1.0))
    duration = float(data.get("duration_s", 1.0))
    return {
        "location_x": {
            "Points": [
                {"co": {"X": 1.0, "Y": start_x}, "interpolation": 1},
                {"co": {"X": 1.0 + duration, "Y": end_x}, "interpolation": 1}
            ]
        }
    }

def color_grade(data: Dict[str, Any]) -> Dict[str, Any]:
    intensity = float(data.get("intensity", 1.0))
    return {
        "alpha": {
            "Points": [
                {"co": {"X": 1.0, "Y": intensity}, "interpolation": 1}
            ]
        }
    }
