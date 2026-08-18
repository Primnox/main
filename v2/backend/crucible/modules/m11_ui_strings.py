"""Module 11 — UI / string torture, at the API boundary.

The frontend cannot be driven from here, so this tests the layer that feeds it:
whether a 400-character filename, an RTL name, a path traversal or a reserved
Windows name survives ingestion and comes back intact.

WHY THIS IS NOT A UI TEST. It deliberately stops at the boundary and says so.
Clipping, overflow and focus order need a browser and a human eye; claiming to
have certified them from here would be the exact dishonesty this suite exists to
avoid. What CAN be certified is that the API neither corrupts nor executes these
strings — and a name that survives the API can then be judged visually.
"""
from __future__ import annotations

import time

from primnox2.assets import service as assets

from ..generate import hostile_strings
from ..scoring import CRITICAL, HIGH, MEDIUM, ModuleResult

KEY, NAME = "M11", "UI String Torture"


def run(ctx) -> ModuleResult:
    result = ModuleResult(key=KEY, name=NAME)
    started = time.perf_counter()

    cases = hostile_strings()
    survived, mangled, refused = {}, {}, {}

    for label, filename in cases.items():
        try:
            asset = assets.ingest_bytes(
                f"content for {label}".encode("utf-8"), filename, source="upload")
            stored = assets.get(asset["id"])
            got = stored["original_name"] if stored else None
            if got == filename:
                survived[label] = True
            else:
                mangled[label] = {"sent": filename[:60], "stored": (got or "")[:60]}
        except Exception as exc:
            refused[label] = f"{type(exc).__name__}: {exc}"

    result.measurements = {
        "cases": len(cases),
        "survived": len(survived),
        "mangled": len(mangled),
        "refused": len(refused),
        "mangled_detail": mangled,
        "refused_detail": refused,
    }

    # A traversal string must be stored as a NAME and never resolved as a path.
    # Content addressing means the bytes live under their hash, so the name is
    # only ever a label — this checks that property actually holds.
    traversal = assets.ingest_bytes(b"traversal probe", "../../../etc/passwd",
                                    source="upload")
    stored = assets.get(traversal["id"])
    path_on_disk = (stored or {}).get("path", "")
    escaped = ".." in str(path_on_disk)
    result.measurements["traversal_path"] = str(path_on_disk)[-70:]

    if escaped:
        result.find(
            title="A filename containing .. reached the storage path",
            severity=CRITICAL, owner="Asset Service",
            what_happened=f"Stored at {path_on_disk}",
            reproduction='assets.ingest_bytes(b"x", "../../../etc/passwd")',
            probable_cause="The original name is used to build the path.",
            suggested_fix=("Store by content hash only and treat the name as a "
                           "label, never as a path component."),
        )

    if mangled:
        result.find(
            title=f"{len(mangled)} hostile filenames were altered in storage",
            severity=MEDIUM, owner="Asset Service",
            what_happened=f"Names changed between write and read: {sorted(mangled)}",
            reproduction="Ingest crucible.generate.hostile_strings(); read each back.",
            probable_cause="Normalisation or an encoding round-trip on the name.",
            suggested_fix=("Store the name as opaque text; do any shortening at "
                           "render time so the original is always recoverable."),
        )

    if refused:
        result.find(
            title=f"{len(refused)} filenames were rejected outright",
            severity=HIGH, owner="Asset Service",
            what_happened=f"Ingestion raised for: {sorted(refused)}",
            reproduction="Ingest each hostile string.",
            probable_cause="An OS-level path operation on an untrusted name.",
            suggested_fix="Never let the original name reach the filesystem.",
            evidence=str(refused)[:400],
        )

    result.score(
        correctness=round(10 * len(survived) / len(cases)),
        consistency=10,
        recovery=10 if not refused else 5,
        performance=10,
        ux_stability=0 if escaped else 10,
    )
    result.duration_s = time.perf_counter() - started
    return result
