"""Heavier tests for this session's riskiest changes: concurrent access to
memory.py's now-cached-per-thread DB connection, vault-invalidation racing
against live writes, meeting-recorder audio streaming at "long call" scale,
notes FTS5 at scale, note_links at scale, vault corruption-recovery under
repeated cycles, and Web Reach tool concurrency. These are slower than the
rest of the suite by design — they're exercising scale/concurrency, not just
logic — but still run by default (see pytest.ini's `slow` marker).
"""
import random
import struct
import threading
import time
import wave
from unittest.mock import MagicMock, patch

import pytest

import event_manager
import local_vault
import memory
import memory_mirror
import notes_manager
import tools
from feed_manager import FeedManager
from meeting_recorder import MeetingRecorder

pytestmark = pytest.mark.slow

_WORDS = (
    "apple banana cherry delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu"
).split()


def _distinct_text(i: int) -> str:
    """Short near-identical strings like f'memory {i}' vs f'memory {i+1}' score
    above is_duplicate()'s 0.85 SequenceMatcher threshold and get legitimately
    deduped — that's correct dedup behavior, but it defeats a concurrency test
    that needs every write to actually land. Shuffled words keep pairwise
    similarity low (measured ~0.35-0.45) regardless of index."""
    rng = random.Random(i)
    return " ".join(rng.sample(_WORDS, 6)) + f" id{i}"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test_memory.db")
    memory.init_db()
    return memory


@pytest.fixture
def mirror_dir(tmp_path, monkeypatch):
    d = tmp_path / "Memory"
    monkeypatch.setattr(memory_mirror, "MEMORY_DIR", d)
    monkeypatch.setattr(memory_mirror, "load_settings", lambda: {"active_model": "Groq_Llama_3"})
    return d


class TestMemoryConcurrency:
    """get_db() now caches one connection per thread. This is the test that
    would catch a bad interaction between that cache and SQLite's actual
    threading rules — each worker thread must get its own connection, never
    share one, and the end state must reflect every write from every thread."""

    def test_concurrent_add_memory_from_many_threads(self, db):
        n_threads = 20
        adds_per_thread = 25
        errors = []

        def worker(idx):
            try:
                for i in range(adds_per_thread):
                    memory.add_memory(_distinct_text(idx * adds_per_thread + i), category="session")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        assert len(memory.list_memories()) == n_threads * adds_per_thread

    def test_concurrent_reads_and_writes_do_not_crash(self, db):
        memory.add_memory("seed memory for search", category="work")
        stop = threading.Event()
        errors = []

        def writer():
            i = 0
            while not stop.is_set():
                try:
                    memory.add_memory(f"writer memory {i}", category="work")
                    i += 1
                except Exception as e:
                    errors.append(e)

        def reader():
            while not stop.is_set():
                try:
                    memory.search_memories("memory")
                    memory.list_memories()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)] + \
                  [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        time.sleep(1.5)
        stop.set()
        for t in threads:
            t.join(timeout=10)

        assert errors == []

    def test_each_thread_gets_its_own_connection(self, db):
        seen = {}
        lock = threading.Lock()

        def worker(idx):
            conn = memory.get_db()
            with lock:
                seen[idx] = id(conn)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(seen.values())) == 10  # every thread's connection object was distinct


class TestVaultInvalidationUnderConcurrency:
    """local_vault.py resets memory's connection cache mid-flight during
    unlock/lock. Simulates that racing against an active writer thread —
    the writer should never see a crash, only ever a fresh, working
    connection after each reset."""

    def test_resets_do_not_corrupt_concurrent_writes(self, db):
        stop = threading.Event()
        errors = []
        write_count = [0]

        def writer():
            while not stop.is_set():
                try:
                    memory.add_memory(_distinct_text(write_count[0]), category="session")
                    write_count[0] += 1
                except Exception as e:
                    errors.append(e)

        def resetter():
            while not stop.is_set():
                memory._reset_db_connection()
                time.sleep(0.01)

        writer_thread = threading.Thread(target=writer)
        resetter_thread = threading.Thread(target=resetter)
        writer_thread.start()
        resetter_thread.start()
        time.sleep(1.0)
        stop.set()
        writer_thread.join(timeout=10)
        resetter_thread.join(timeout=10)

        assert errors == []
        # Every add_memory call that ran should have actually persisted.
        assert len(memory.list_memories()) == write_count[0]


class TestMeetingRecorderLongCall:
    """The whole point of streaming to disk was bounding memory for a long
    call. Simulates ~2 hours of flush cycles (one flush per 2s poll tick,
    matching the real loop's cadence) and checks both the final file and
    that the in-memory list never grows past a couple of chunks between
    flushes."""

    def test_two_hour_call_produces_correct_total_frames_with_bounded_memory(self, tmp_path):
        rec = MeetingRecorder.__new__(MeetingRecorder)
        rec.audio_frames = []
        rec.mic_frames = []
        rec._frame_lock = threading.Lock()
        rec._spk_writer = rec._open_wav_writer(tmp_path / "spk.wav", 1, 16000)
        rec._mic_writer = None

        chunk_samples = 1600  # 0.1s at 16kHz, arbitrary small unit
        flushes = 72_000 // 20  # simulate ~2h of 20s-worth-per-flush chunks, kept fast
        max_list_len_seen = 0

        for _ in range(flushes):
            rec.audio_frames.append(struct.pack(f"<{chunk_samples}h", *([0] * chunk_samples)))
            max_list_len_seen = max(max_list_len_seen, len(rec.audio_frames))
            rec._flush_audio_to_disk()
            assert rec.audio_frames == []  # bounded: never accumulates across flushes

        rec._close_wav_writers()

        assert max_list_len_seen == 1  # at most one chunk was ever resident between flushes
        with wave.open(str(tmp_path / "spk.wav"), 'rb') as wf:
            assert wf.getnframes() == chunk_samples * flushes


class TestNotesFTSAtScale:
    @pytest.fixture
    def notes_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(notes_manager, "DB_PATH", tmp_path / "notes.db")
        notes_manager.init_db()
        return notes_manager

    def test_search_finds_the_right_note_among_thousands(self, notes_db):
        for i in range(2000):
            notes_db.add_note(f"generic filler content number {i}", title=f"Note {i}")
        notes_db.add_note("the unique needle phrase appears exactly here", title="Special Note")

        results = notes_db.search_notes("needle phrase")

        assert any(r["title"] == "Special Note" for r in results)

    def test_search_stays_fast_at_scale(self, notes_db):
        for i in range(2000):
            notes_db.add_note(f"content block {i} about various topics", title=f"Note {i}")

        t0 = time.perf_counter()
        notes_db.search_notes("various topics")
        elapsed = time.perf_counter() - t0

        assert elapsed < 0.5  # FTS5 should stay well under this even at this scale


class TestRecurringErrorAtScale:
    @pytest.fixture
    def fm(self):
        f = FeedManager.__new__(FeedManager)
        f.error_recurrence_count = {}
        f.error_recurrence_recorded = set()
        f.RECURRING_ERROR_THRESHOLD = 3
        return f

    def test_many_distinct_fingerprints_do_not_interfere(self, fm, db):
        for fp_idx in range(500):
            fm._maybe_record_recurring_error(f"fp{fp_idx}", _distinct_text(fp_idx), {})
        # None crossed the threshold (each seen once) — nothing recorded yet.
        assert memory.list_memories() == []

        # Now push 50 of them past the threshold.
        for fp_idx in range(50):
            fm._maybe_record_recurring_error(f"fp{fp_idx}", _distinct_text(fp_idx), {})
            fm._maybe_record_recurring_error(f"fp{fp_idx}", _distinct_text(fp_idx), {})

        # The recorder's own bookkeeping is the real contract here: 50
        # distinct fingerprints crossed the threshold and got marked handled.
        # Asserting the DB's memory count would also be re-testing
        # is_duplicate()'s similarity dedup — every one of these 50 texts
        # shares the literal "Recurring error (seen 3+ times): " prefix,
        # which inflates pairwise similarity regardless of the random
        # suffix, so a rare cross-fingerprint dedup collision here is
        # expected noise, not a bug (that's what the loose bound below
        # tolerates rather than asserting an exact count).
        assert len(fm.error_recurrence_recorded) == 50
        assert len(memory.list_memories()) >= 45


class TestFocusModeSuppressionAtScale:
    @pytest.fixture
    def fm(self):
        f = FeedManager.__new__(FeedManager)
        f.window_start_time = 0.0
        f.FOCUS_SUPPRESSION_SECONDS = 1200
        f._suppressed_nudges = []
        f.MAX_SUPPRESSED_NUDGES = 20
        f.callback = None
        return f

    def test_queue_stays_capped_under_heavy_nudge_volume(self, fm):
        # A pathologically long focus session shouldn't let this grow
        # unbounded even if every nudge type somehow fired repeatedly.
        for i in range(5000):
            fm._emit_nudge("proactive_message", {"i": i}, current_time=2000.0)

        assert len(fm._suppressed_nudges) == fm.MAX_SUPPRESSED_NUDGES

    def test_capped_queue_keeps_the_most_recent_entries_in_order(self, fm):
        for i in range(5000):
            fm._emit_nudge("proactive_message", {"i": i}, current_time=2000.0)

        kept = [payload["i"] for _, payload in fm._suppressed_nudges]
        assert kept == list(range(4980, 5000))  # last 20, oldest to newest

    def test_flush_after_heavy_volume_delivers_exactly_the_capped_set(self, fm):
        received = []
        fm.callback = lambda t, p: received.append(p["i"])
        for i in range(5000):
            fm._emit_nudge("proactive_message", {"i": i}, current_time=2000.0)

        fm._flush_suppressed_nudges()

        assert received == list(range(4980, 5000))
        assert fm._suppressed_nudges == []

    def test_concurrent_emit_never_crashes_or_exceeds_cap(self, fm):
        errors = []

        def worker(base):
            try:
                for i in range(500):
                    fm._emit_nudge("proactive_message", {"i": base + i}, current_time=2000.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t * 500,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        assert len(fm._suppressed_nudges) <= fm.MAX_SUPPRESSED_NUDGES


class TestMemoryMirrorConcurrency:
    """render_memory_mirror() runs on the cleanup scheduler's thread while
    chat/feed threads keep calling add_memory concurrently in real use —
    simulates that overlap instead of only ever rendering a frozen snapshot."""

    def test_concurrent_writes_during_render_do_not_crash(self, db, mirror_dir):
        stop = threading.Event()
        errors = []

        def writer():
            i = 0
            while not stop.is_set():
                try:
                    memory.add_memory(_distinct_text(i), category="session")
                    i += 1
                except Exception as e:
                    errors.append(e)

        def renderer():
            while not stop.is_set():
                try:
                    memory_mirror.render_memory_mirror()
                except Exception as e:
                    errors.append(e)

        writer_thread = threading.Thread(target=writer)
        renderer_thread = threading.Thread(target=renderer)
        writer_thread.start()
        renderer_thread.start()
        time.sleep(1.5)
        stop.set()
        writer_thread.join(timeout=10)
        renderer_thread.join(timeout=10)

        assert errors == []
        # One final render should reflect everything written, with no
        # partial/corrupt output left over from an interrupted render.
        memory_mirror.render_memory_mirror()
        text = (mirror_dir / "session.md").read_text(encoding="utf-8")
        assert text.startswith("# Session")


class TestMarkStaleMemoriesAtScale:
    def _insert_raw(self, text, category, provenance, age_days, access_count=0):
        from datetime import datetime, timedelta
        conn = memory.get_db()
        c = conn.cursor()
        ts = (datetime.now() - timedelta(days=age_days)).isoformat()
        c.execute(
            "INSERT INTO memories (key, text, category, timestamp, stale, topic, provenance, access_count) "
            "VALUES (?, ?, ?, ?, 0, NULL, ?, ?)",
            (text, text, category, ts, provenance, access_count),
        )
        conn.commit()

    def test_correct_partitioning_at_scale(self, db):
        # 2000 explicit memories just past the inferred cutoff but well
        # within the explicit one — must all survive.
        for i in range(2000):
            self._insert_raw(f"explicit {i}", "personal", "explicit", age_days=15)
        # 2000 inferred memories past their (shorter) cutoff — must all go stale.
        for i in range(2000):
            self._insert_raw(f"inferred {i}", "session", "inferred_chat", age_days=15)
        # 500 inferred but frequently recalled — grace should save them.
        for i in range(500):
            self._insert_raw(f"popular {i}", "session", "inferred_screen", age_days=15, access_count=10)

        t0 = time.perf_counter()
        flagged = memory.mark_stale_memories()
        elapsed = time.perf_counter() - t0

        assert flagged == 2000
        remaining = memory.list_memories()
        assert len(remaining) == 2500  # 2000 explicit + 500 popular-inferred
        assert elapsed < 2.0


class TestNotesConcurrency:
    @pytest.fixture
    def notes_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(notes_manager, "DB_PATH", tmp_path / "notes.db")
        notes_manager.init_db()
        return notes_manager

    def test_concurrent_notes_and_tasks_from_many_threads(self, notes_db):
        errors = []

        def note_worker(idx):
            try:
                for i in range(50):
                    notes_db.add_note(_distinct_text(idx * 50 + i), title=f"Note {idx}-{i}")
            except Exception as e:
                errors.append(e)

        def task_worker(idx):
            try:
                for i in range(50):
                    notes_db.add_task(_distinct_text(10_000 + idx * 50 + i))
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=note_worker, args=(t,)) for t in range(5)] +
            [threading.Thread(target=task_worker, args=(t,)) for t in range(5)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        assert len(notes_db.get_notes()) == 250
        assert len(notes_db.get_tasks()) == 250


class TestMeetingMixingAtScale:
    def test_mixes_thirty_seconds_of_differing_sample_rates(self, tmp_path):
        rec = MeetingRecorder.__new__(MeetingRecorder)
        spk_path, mic_path, out_path = tmp_path / "spk.wav", tmp_path / "mic.wav", tmp_path / "mixed.wav"

        # Speaker at 44.1kHz stereo (typical WASAPI loopback), mic at 48kHz
        # mono — exercises the resample_poly path, not just the silence case.
        spk_w = rec._open_wav_writer(spk_path, 2, 44100)
        spk_w.writeframes(struct.pack(f"<{30 * 44100 * 2}h", *([100] * (30 * 44100 * 2))))
        spk_w.close()

        mic_w = rec._open_wav_writer(mic_path, 1, 48000)
        mic_w.writeframes(struct.pack(f"<{30 * 48000}h", *([200] * (30 * 48000))))
        mic_w.close()

        t0 = time.perf_counter()
        ok = rec._save_mixed_wav(out_path, spk_path, mic_path)
        elapsed = time.perf_counter() - t0

        assert ok is True
        with wave.open(str(out_path), 'rb') as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 16000
            # ~30s at 16kHz, allowing for resampling rounding
            assert abs(wf.getnframes() - 30 * 16000) < 16000 * 0.05
        assert elapsed < 5.0


class TestNoteLinksAtScale:
    """note_links is new this session (wiki-link feature). Many threads
    creating/updating notes that [[link]] to a shared pool of targets at
    once — the real-world equivalent of several devices/tabs syncing notes
    concurrently. _resolve_and_set_links does a DELETE+SELECT+executemany
    per save under notes_manager's fresh-connection-per-call model (no
    thread-local cache like memory.py), so this is the test that would catch
    a WAL-mode locking/retry problem or a link left in a half-written state."""

    @pytest.fixture
    def notes_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(notes_manager, "DB_PATH", tmp_path / "notes.db")
        notes_manager.init_db()
        return notes_manager

    def test_concurrent_linking_from_many_threads(self, notes_db):
        n_targets = 10
        targets = [notes_db.add_note("x", title=f"Target {i}") for i in range(n_targets)]
        errors = []

        def worker(idx):
            try:
                for i in range(20):
                    target = targets[(idx * 20 + i) % n_targets]
                    notes_db.add_note(f"see [[{target['title']}]]", title=f"Source {idx}-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        all_notes = notes_db.get_notes()
        # 10 targets + 10 threads * 20 sources
        assert len(all_notes) == n_targets + 200

        # Every source note resolved to exactly one link, and no link points
        # at a nonexistent note (a half-written DELETE+INSERT would show up
        # here as either 0 or >1 links for some source).
        source_notes = [n for n in all_notes if n["title"].startswith("Source")]
        assert len(source_notes) == 200
        for n in source_notes:
            links = notes_db.get_note_links(n["id"])
            assert len(links) == 1
            assert links[0]["id"] in {t["id"] for t in targets}

    def test_repeated_updates_never_leave_stale_or_duplicate_links(self, notes_db):
        """update_note's _resolve_and_set_links does DELETE-then-INSERT for
        the same note_id from many threads — a race here would either leave
        zero links (DELETE from thread B ran after thread A's INSERT) or
        duplicate rows (two INSERTs landed before either DELETE). Both are
        detectable from a single thread re-reading after the storm settles."""
        target = notes_db.add_note("x", title="Shared Target")
        source = notes_db.add_note("initial", title="Racer")
        errors = []

        def worker(idx):
            try:
                for i in range(30):
                    notes_db.update_note(source["id"], "Racer", f"see [[Shared Target]] rev{idx}-{i}", project=None, parent_id=None)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        # UNIQUE(source_id, target_id) makes duplicates structurally
        # impossible; the real risk this catches is a DELETE racing ahead of
        # the final INSERT and leaving zero links behind.
        links = notes_db.get_note_links(source["id"])
        assert links == [{"id": target["id"], "title": "Shared Target"}]


class TestEventManagerConcurrency:
    """event_manager.py shares memory.py's thread-cached get_db() connection
    — the exact class of module that had a real production bug earlier this
    session (reminder_manager/event_manager were calling conn.close() on
    that shared connection, poisoning it for the rest of the thread's
    lifetime). This drives concurrent event creation/update across many
    threads as a regression guard: if that bug ever comes back, this fails
    with 'Cannot operate on a closed database' instead of silently passing."""

    def test_concurrent_event_creation_with_note_links(self, db):
        event_manager.init_events_table()
        errors = []

        def worker(idx):
            try:
                for i in range(25):
                    event_manager.create_event({
                        "title": f"Event {idx}-{i}",
                        "start_dt": f"2026-0{(idx % 9) + 1}-01T09:00:00",
                        "end_dt": f"2026-0{(idx % 9) + 1}-01T10:00:00",
                        "note_id": idx * 100 + i,
                    })
                    # Interleave with the shared memory.py connection this
                    # module also touches — this is exactly the surface the
                    # earlier connection-closing bug broke.
                    memory.get_db().execute("SELECT 1")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        assert len(event_manager.list_events()) == 15 * 25
        # The shared connection must still be alive on the main thread too.
        assert tuple(memory.get_db().execute("SELECT 1").fetchone()) == (1,)


class TestVaultRecoveryUnderRepeatedCycles:
    """Repeated lock→corrupt→recover cycles to shake out edge cases in this
    session's new recovery path — a single pass proved it works once, this
    proves it keeps working after the connection cache has been through
    several open/close/recover transitions, which is closer to how a
    long-running desktop app would actually hit this over days of use."""

    TEST_KEY = b"\x02" * 32

    def test_survives_ten_corrupt_and_recover_cycles(self, db):
        # _distinct_text(), not f"cycle {cycle} fact" — near-identical short
        # strings score above is_duplicate()'s threshold and get legitimately
        # deduped (see this file's module docstring), which would make every
        # cycle after the first silently vanish for reasons unrelated to the
        # recovery path this test actually exercises.
        for cycle in range(10):
            memory.add_memory(_distinct_text(cycle), category="session")
            memory._reset_db_connection()

            local_vault.lock_vault(memory.DB_PATH, key=self.TEST_KEY)
            assert not memory.DB_PATH.exists()

            # Simulate the interrupted-overwrite corruption this session's
            # incident actually produced, then let get_db() recover from the
            # still-good .vault written by lock_vault() above.
            memory.DB_PATH.write_bytes(b"corrupted mid-write garbage")
            with patch.object(local_vault, "_keychain_load", return_value=self.TEST_KEY):
                memory.init_db()

            rows = memory.get_db().execute("SELECT text FROM memories").fetchall()
            texts = {r["text"] for r in rows}
            assert _distinct_text(cycle) in texts
            # Every prior cycle's data must still be present — recovery
            # replaces the corrupted file with the vault's actual contents,
            # it must never silently drop history.
            for prior in range(cycle):
                assert _distinct_text(prior) in texts


class TestWebReachToolsConcurrency:
    """Web Reach tools are now LLM-callable — if two chat sessions (or two
    tool calls in the same multi-step tool loop) fire concurrently, nothing
    in tools.py should share mutable state across threads. All network calls
    are mocked; this is purely a thread-safety check on the Python side."""

    def test_concurrent_calls_across_all_tools_do_not_interfere(self):
        errors = []
        results = []
        lock = threading.Lock()

        def fake_get(url, *args, **kwargs):
            resp = MagicMock(status_code=200)
            resp.raise_for_status = MagicMock()
            if "r.jina.ai" in url:
                resp.text = f"content for {url}"
            elif "api.github.com" in url and "/issues" in url:
                resp.ok = True
                resp.json.return_value = []
            elif "api.github.com" in url:
                resp.json.return_value = {"full_name": "a/b", "description": "d", "stargazers_count": 1, "language": "Python"}
            elif "reddit.com" in url:
                resp.json.return_value = [
                    {"data": {"children": [{"data": {"title": "t", "selftext": "s"}}]}},
                    {"data": {"children": []}},
                ]
            elif "syndication.twimg.com" in url:
                resp.json.return_value = {"text": "hi", "user": {"screen_name": "u", "name": "n"}}
            return resp

        def worker(idx):
            try:
                r1 = tools.fetch_webpage(f"https://example.com/{idx}")
                r2 = tools.fetch_github_repo_info("a/b")
                r3 = tools.fetch_reddit_thread(f"https://reddit.com/r/x/comments/{idx}/y/")
                r4 = tools.fetch_tweet(str(idx))
                with lock:
                    results.append((idx, r1, r2, r3, r4))
            except Exception as e:
                errors.append(e)

        # patch() swaps a module-global attribute — applying it once per
        # thread (each with its own enter/exit) races against every other
        # thread's enter/exit on the SAME target and can leave requests.get
        # briefly unpatched mid-run (that's what actually happened: a real
        # network call escaped and hit Twitter's live endpoint, returning a
        # genuine 404 instead of the mock). One patch around the whole
        # thread pool is the correct pattern for this.
        with patch("tools.requests.get", side_effect=fake_get):
            threads = [threading.Thread(target=worker, args=(t,)) for t in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        assert errors == []
        assert len(results) == 20
        for idx, r1, r2, r3, r4 in results:
            # Each thread's own URL/id must come back in its own result —
            # any cross-talk from shared state would mix these up.
            assert f"example.com/{idx}" in r1
            assert "a/b" in r2
            assert "t" in r3
            assert "hi" in r4
