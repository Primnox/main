"""Performance benchmark for the memory write/read path and the Markdown
mirror render — the pieces touched by the provenance/topic/scoring rework.

Run: python bench_memory.py [N ...]   (defaults to 100, 1000, 5000, 20000)

Each run uses a fresh throwaway DB and mirror folder under a temp dir so it
never touches real data.
"""
import random
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

import memory
import memory_mirror

PROVENANCES = ["explicit", "inferred_chat", "inferred_screen"]
TOPICS = [None, "project:primnox", "project:nothing-rom", "project:social-factory"]
WORDS = (
    "primnox project fix bug theme dark mode user prefers likes dislikes "
    "meeting call schedule deadline api key server backend frontend "
    "python rust tauri react memory search vault backup notes task"
).split()


def _rand_text(n=8):
    return " ".join(random.choice(WORDS) for _ in range(n))


def _percentile(values, p):
    s = sorted(values)
    return s[min(int(len(s) * p), len(s) - 1)]


def seed(n):
    for _ in range(n):
        memory.add_memory(
            _rand_text(),
            category=random.choice(memory.CATEGORIES),
            topic=random.choice(TOPICS),
            provenance=random.choice(PROVENANCES),
        )


def timed(fn, *a, **kw):
    t0 = time.perf_counter()
    result = fn(*a, **kw)
    return time.perf_counter() - t0, result


def bench(n):
    tmp = Path(tempfile.mkdtemp(prefix="primnox_bench_"))
    memory.DB_PATH = tmp / "memory.db"
    memory_mirror.MEMORY_DIR = tmp / "Memory"
    memory.init_db()

    seed_time, _ = timed(seed, n)

    add_times = [timed(memory.add_memory, _rand_text(), category=random.choice(memory.CATEGORIES))[0] for _ in range(50)]
    search_times = [timed(memory.search_memories, random.choice(WORDS), limit=10)[0] for _ in range(50)]
    stale_time, flagged = timed(memory.mark_stale_memories)
    mirror_time, topics = timed(memory_mirror.render_memory_mirror)
    # Second render — measures the steady-state cost once files/git history
    # already exist (git status/add/commit on an unchanged tree is the common
    # case: it runs every 24h whether or not memories changed).
    mirror_time_2, _ = timed(memory_mirror.render_memory_mirror)

    print(f"\n=== N={n} memories ===")
    print(f"seed:                  {seed_time:8.3f}s total  ({seed_time/n*1000:6.3f}ms/insert)")
    print(f"add_memory (dedup):    avg {statistics.mean(add_times)*1000:6.2f}ms  p95 {_percentile(add_times, 0.95)*1000:6.2f}ms")
    print(f"search_memories:       avg {statistics.mean(search_times)*1000:6.2f}ms  p95 {_percentile(search_times, 0.95)*1000:6.2f}ms")
    print(f"mark_stale_memories:   {stale_time*1000:8.2f}ms  ({flagged} flagged, full-scan-in-Python cost)")
    print(f"render_memory_mirror:  {mirror_time*1000:8.2f}ms  first run  ({topics} topic files + git commit)")
    print(f"render_memory_mirror:  {mirror_time_2*1000:8.2f}ms  steady-state (no changes, git status only)")

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    ns = [int(x) for x in sys.argv[1:]] or [100, 1000, 5000, 20000]
    for n in ns:
        bench(n)
