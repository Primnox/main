"""Tests for the meeting recorder's disk-streaming rework: audio used to be
buffered entirely in memory for the whole call (multi-GB for a long meeting);
now it's flushed to a WAV file incrementally and the mix step reads it back
from disk. Also covers the is_meeting_running() poll-frequency cache.

No real audio hardware involved — these exercise the WAV read/write/mix
logic directly with synthetic PCM data.
"""
import struct
import wave

import pytest

import notes_manager
from meeting_recorder import MeetingRecorder, create_tasks_from_summary


def _pcm_silence(n_samples: int) -> bytes:
    return struct.pack(f"<{n_samples}h", *([0] * n_samples))


@pytest.fixture
def rec():
    r = MeetingRecorder.__new__(MeetingRecorder)  # skip __init__'s FeedManager/etc. wiring
    r.audio_frames = []
    r.mic_frames = []
    r._spk_writer = None
    r._mic_writer = None
    import threading
    r._frame_lock = threading.Lock()
    r.capture_channels = 1
    r.capture_rate = 16000
    r.mic_channels = 1
    r.mic_rate = 16000
    r._native_check_at = 0.0
    r._native_check_cached = True
    return r


class TestWavStreaming:
    def test_flush_writes_accumulated_frames_and_clears_list(self, rec, tmp_path):
        path = tmp_path / "spk.wav"
        rec._spk_writer = rec._open_wav_writer(path, 1, 16000)
        rec.audio_frames = [_pcm_silence(100), _pcm_silence(50)]

        rec._flush_audio_to_disk()

        assert rec.audio_frames == []
        rec._close_wav_writers()
        with wave.open(str(path), 'rb') as wf:
            assert wf.getnframes() == 150

    def test_multiple_flushes_accumulate_across_calls(self, rec, tmp_path):
        path = tmp_path / "spk.wav"
        rec._spk_writer = rec._open_wav_writer(path, 1, 16000)

        for _ in range(5):
            rec.audio_frames.append(_pcm_silence(10))
            rec._flush_audio_to_disk()

        rec._close_wav_writers()
        with wave.open(str(path), 'rb') as wf:
            assert wf.getnframes() == 50

    def test_flush_with_no_writer_does_not_raise(self, rec):
        rec.audio_frames = [_pcm_silence(10)]
        rec._flush_audio_to_disk()  # no writer opened — should be a no-op, not a crash
        assert rec.audio_frames == []

    def test_flush_is_thread_safe_swap(self, rec, tmp_path):
        # A flush mid-append should never lose the whole buffer — this checks
        # the swap-under-lock pattern doesn't drop frames appended just before it.
        path = tmp_path / "spk.wav"
        rec._spk_writer = rec._open_wav_writer(path, 1, 16000)
        with rec._frame_lock:
            rec.audio_frames.append(_pcm_silence(20))
        rec._flush_audio_to_disk()
        rec._close_wav_writers()
        with wave.open(str(path), 'rb') as wf:
            assert wf.getnframes() == 20


class TestReadWav:
    def test_reads_existing_file(self, rec, tmp_path):
        path = tmp_path / "a.wav"
        w = rec._open_wav_writer(path, 2, 44100)
        w.writeframes(_pcm_silence(200))  # 100 stereo frames
        w.close()

        raw, channels, rate = rec._read_wav(path)
        assert channels == 2
        assert rate == 44100
        assert len(raw) == 200 * 2  # 200 int16 samples

    def test_missing_file_returns_empty(self, rec, tmp_path):
        raw, channels, rate = rec._read_wav(tmp_path / "missing.wav")
        assert raw == b""
        assert channels == 0
        assert rate == 0


class TestSaveMixedWav:
    def test_mixes_two_existing_tracks(self, rec, tmp_path):
        spk_path, mic_path, out_path = tmp_path / "spk.wav", tmp_path / "mic.wav", tmp_path / "mixed.wav"
        for p in (spk_path, mic_path):
            w = rec._open_wav_writer(p, 1, 16000)
            w.writeframes(_pcm_silence(1600))  # 0.1s
            w.close()

        assert rec._save_mixed_wav(out_path, spk_path, mic_path) is True
        assert out_path.exists()
        with wave.open(str(out_path), 'rb') as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 16000
            assert wf.getnframes() > 0

    def test_returns_false_when_neither_track_exists(self, rec, tmp_path):
        result = rec._save_mixed_wav(tmp_path / "out.wav", tmp_path / "spk.wav", tmp_path / "mic.wav")
        assert result is False

    def test_mixes_when_only_speaker_track_exists(self, rec, tmp_path):
        spk_path, mic_path, out_path = tmp_path / "spk.wav", tmp_path / "mic.wav", tmp_path / "mixed.wav"
        w = rec._open_wav_writer(spk_path, 1, 16000)
        w.writeframes(_pcm_silence(800))
        w.close()

        assert rec._save_mixed_wav(out_path, spk_path, mic_path) is True
        with wave.open(str(out_path), 'rb') as wf:
            assert wf.getnframes() == 800


class TestCreateTasksFromSummary:
    @pytest.fixture
    def notes_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(notes_manager, "DB_PATH", tmp_path / "notes.db")
        notes_manager.init_db()
        return notes_manager

    def test_creates_a_task_per_action_item(self, notes_db):
        summary = "Overview text.\nTODO: send the follow-up email.\nWe agreed the plan looks solid."
        created = create_tasks_from_summary(summary, "Standup")
        assert created == 1
        [task] = notes_db.get_tasks()
        assert "send the follow-up email" in task["text"]
        assert task["text"].startswith("[Standup]")

    def test_no_action_items_creates_nothing(self, notes_db):
        created = create_tasks_from_summary("Just a general recap, nothing actionable.", "Standup")
        assert created == 0
        assert notes_db.get_tasks() == []

    def test_deduplicates_identical_action_items(self, notes_db):
        summary = "Need to finish the report. Need to finish the report."
        created = create_tasks_from_summary(summary, "Standup")
        assert created == 1

    def test_caps_at_ten_items(self, notes_db):
        summary = "\n".join(f"TODO: item number {i}." for i in range(20))
        created = create_tasks_from_summary(summary, "Standup")
        assert created == 10


class TestIsMeetingRunningCache:
    def test_native_check_is_cached_within_interval(self, rec, monkeypatch):
        rec._active_in_browser = False
        calls = []
        monkeypatch.setattr(
            "meeting_recorder.psutil.process_iter",
            lambda *a, **k: calls.append(1) or iter([]),
        )
        rec.is_meeting_running()
        rec.is_meeting_running()
        assert len(calls) == 1  # second call hit the cache, no new scan

    def test_native_check_rescans_after_interval(self, rec, monkeypatch):
        rec._active_in_browser = False
        calls = []
        monkeypatch.setattr(
            "meeting_recorder.psutil.process_iter",
            lambda *a, **k: calls.append(1) or iter([]),
        )
        rec.is_meeting_running()
        rec._native_check_at = 0.0  # force the cache to look stale
        rec.is_meeting_running()
        assert len(calls) == 2
