"""The Deterministic Replay Pack.

A torture run that generates fresh artifacts every time measures a different
system each time. The pack fixes the inputs: every artifact is produced from a
seed, hashed, and recorded in a manifest with its expected outcome. A later
build reruns the identical bytes and the comparison means something.

Two properties this file exists to guarantee.

REPRODUCIBLE. `pack.build()` on any machine with the same seed and version
produces the same hashes. If it does not, that is itself a finding — an artifact
generator that drifts makes every downstream comparison noise.

COMPARABLE. `compare()` reports what changed BETWEEN runs, not just what failed
in this one. A regression benchmark's job is the delta: a module that scored 9
last build and 6 today is more informative than either number alone.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

PACK_VERSION = "1.0.0"

# Bump when a generator changes shape. Hashes are expected to differ across
# revisions; the manifest records which revision produced them so a comparison
# never silently pits one generator's output against another's.
GENERATOR_REVISION = 1


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class Artifact:
    key: str
    kind: str                      # conversation | deck | document | repo | graph | sheet
    path: str | None = None
    sha256: str = ""
    bytes: int = 0
    generated_s: float = 0.0
    expected: dict = field(default_factory=dict)   # what a correct system does with it
    notes: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Pack:
    root: Path
    seed: int = 20260815
    artifacts: dict = field(default_factory=dict)

    def add(self, artifact: Artifact) -> Artifact:
        self.artifacts[artifact.key] = artifact
        return artifact

    def add_file(self, key: str, kind: str, path: Path, *, expected: dict | None = None,
                 notes: str = "", generated_s: float = 0.0) -> Artifact:
        return self.add(Artifact(
            key=key, kind=kind, path=str(path.relative_to(self.root)),
            sha256=sha256_file(path), bytes=path.stat().st_size,
            expected=expected or {}, notes=notes, generated_s=generated_s,
        ))

    def add_inline(self, key: str, kind: str, data: str, *,
                   expected: dict | None = None, notes: str = "") -> Artifact:
        raw = data.encode("utf-8")
        return self.add(Artifact(
            key=key, kind=kind, sha256=sha256_bytes(raw), bytes=len(raw),
            expected=expected or {}, notes=notes,
        ))

    def to_dict(self) -> dict:
        return {
            "pack_version": PACK_VERSION,
            "generator_revision": GENERATOR_REVISION,
            "seed": self.seed,
            # Recorded, not asserted. These do not affect the hashes, but when a
            # hash DOES differ they are the first thing anyone asks about.
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "created_at": int(time.time() * 1000),
            },
            "artifacts": {k: a.to_dict() for k, a in sorted(self.artifacts.items())},
        }

    def write(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / "manifest.json"
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, root: Path) -> dict:
        return json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))


def verify(root: Path) -> list[str]:
    """Re-hash every file in a pack. Returns the keys that no longer match.

    This is what makes the pack a benchmark rather than a folder: an artifact
    that changed on disk invalidates every result derived from it, and silent
    drift would look like a regression in the system under test.
    """
    data = Pack.load(root)
    drifted: list[str] = []
    for key, art in data["artifacts"].items():
        if not art.get("path"):
            continue
        path = Path(root) / art["path"]
        if not path.exists() or sha256_file(path) != art["sha256"]:
            drifted.append(key)
    return drifted


def compare(previous: dict, current: dict) -> dict:
    """Delta between two Crucible runs. The regression signal."""
    prev_mods = {m["key"]: m for m in previous.get("modules", [])}
    curr_mods = {m["key"]: m for m in current.get("modules", [])}

    regressions, improvements, unchanged = [], [], []
    for key, curr in curr_mods.items():
        prev = prev_mods.get(key)
        if not prev or prev.get("average") is None or curr.get("average") is None:
            continue
        delta = round(curr["average"] - prev["average"], 2)
        row = {"module": key, "before": prev["average"],
               "after": curr["average"], "delta": delta}
        (regressions if delta < -0.05 else
         improvements if delta > 0.05 else unchanged).append(row)

    prev_titles = {(f["module"], f["title"])
                   for m in previous.get("modules", []) for f in m.get("findings", [])}
    curr_titles = {(f["module"], f["title"])
                   for m in current.get("modules", []) for f in m.get("findings", [])}

    return {
        "overall_before": previous.get("summary", {}).get("overall"),
        "overall_after": current.get("summary", {}).get("overall"),
        "regressions": sorted(regressions, key=lambda r: r["delta"]),
        "improvements": sorted(improvements, key=lambda r: -r["delta"]),
        "unchanged": len(unchanged),
        "new_findings": sorted(f"{m}: {t}" for m, t in curr_titles - prev_titles),
        "fixed_findings": sorted(f"{m}: {t}" for m, t in prev_titles - curr_titles),
    }
