import os
import json
import xml.etree.ElementTree as ET
import unittest
from ffmpeg_engine import export_to_mlt, export_to_openshot

class TestVideoEditorEngine(unittest.TestCase):
    def setUp(self):
        self.mock_edl = {
            "project_id": "test_project_123",
            "duration": 25.0,
            "timeline": [
                {
                    "clip_id": "clip_0",
                    "track": 0,
                    "start_time": 0.0,
                    "end_time": 5.0,
                    "in_point": 2.0,
                    "out_point": 7.0,
                    "speed": 1.0,
                    "volume": 1.0,
                    "muted": False
                },
                {
                    "clip_id": "clip_1",
                    "track": 0,
                    "start_time": 5.0,
                    "end_time": 10.0,
                    "in_point": 10.0,
                    "out_point": 20.0,
                    "speed": 2.0, # Double speed
                    "volume": 0.5,
                    "muted": False
                },
                {
                    "clip_id": "clip_2",
                    "track": 1, # Overlay B-roll track
                    "start_time": 2.0,
                    "end_time": 4.0,
                    "in_point": 0.0,
                    "out_point": 2.0,
                    "speed": 1.0,
                    "volume": 1.0,
                    "muted": True # Muted overlay
                }
            ]
        }
        self.source_path = "mock_source.mp4"
        self.output_mlt = "test_output.mlt"
        self.output_osp = "test_output.osp"

    def tearDown(self):
        # Clean up output files
        for f in [self.output_mlt, self.output_osp]:
            if os.path.exists(f):
                os.remove(f)

    def test_mlt_export(self):
        # Run exporter
        export_to_mlt(self.mock_edl, self.source_path, self.output_mlt, fps=24.0)
        self.assertTrue(os.path.exists(self.output_mlt))
        
        # Verify XML structure
        tree = ET.parse(self.output_mlt)
        root = tree.getroot()
        self.assertEqual(root.tag, "mlt")
        
        # Check profile
        profile = root.find("profile")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.get("width"), "1920")
        self.assertEqual(profile.get("frame_rate_num"), "24")
        
        # Check source producer
        producers = root.findall("producer")
        self.assertEqual(len(producers), 1)
        self.assertEqual(producers[0].get("id"), "producer_source")
        
        # Check playlists (tracks)
        playlists = root.findall("playlist")
        self.assertEqual(len(playlists), 2)
        self.assertEqual(playlists[0].get("id"), "playlist_track_0")
        self.assertEqual(playlists[1].get("id"), "playlist_track_1")
        
        # Track 0 should have 2 entries
        entries_t0 = playlists[0].findall("entry")
        self.assertEqual(len(entries_t0), 2)
        self.assertEqual(entries_t0[0].get("in"), "48") # 2.0s * 24fps
        self.assertEqual(entries_t0[0].get("out"), "168") # 7.0s * 24fps
        
        # Track 1 should have 1 blank (2.0s padding) and 1 entry
        blanks_t1 = playlists[1].findall("blank")
        self.assertEqual(len(blanks_t1), 1)
        self.assertEqual(blanks_t1[0].get("length"), "48") # 2.0s * 24fps
        
        entries_t1 = playlists[1].findall("entry")
        self.assertEqual(len(entries_t1), 1)
        self.assertEqual(entries_t1[0].get("in"), "0")
        self.assertEqual(entries_t1[0].get("out"), "48") # 2.0s * 24fps

    def test_openshot_export(self):
        # Run exporter
        export_to_openshot(self.mock_edl, self.source_path, self.output_osp)
        self.assertTrue(os.path.exists(self.output_osp))
        
        # Verify JSON content
        with open(self.output_osp, encoding="utf-8") as f:
            data = json.load(f)
            
        self.assertEqual(data["width"], 1920)
        self.assertEqual(data["height"], 1080)
        self.assertEqual(len(data["files"]), 1)
        self.assertEqual(data["files"][0]["id"], "F1")
        
        # Check clips
        self.assertEqual(len(data["clips"]), 3)
        clips = data["clips"]
        
        # Check layers mapping (track index matches layer value)
        self.assertEqual(clips[0]["layer"], 0)
        self.assertEqual(clips[1]["layer"], 0)
        self.assertEqual(clips[2]["layer"], 1)
        
        # Check speeds
        self.assertEqual(clips[0]["speed"], 1.0)
        self.assertEqual(clips[1]["speed"], 2.0)
        
        # Check volume translations (volume is 0.0 if muted)
        self.assertEqual(clips[0]["volume"], 1.0)
        self.assertEqual(clips[1]["volume"], 0.5)
        self.assertEqual(clips[2]["volume"], 0.0)

if __name__ == "__main__":
    unittest.main()
