"""Damage a generated pack the way a real filesystem damages one.

    python sdl/failure.py --from ./sdl-out/office-500
    python sdl/failure.py --from ./sdl-out/office-500 --modes deleted_files,ocr_noise
    python sdl/failure.py --from ./sdl-out/office-500 --in-place

A clean corpus measures retrieval on a good day. Real corpora have files that
were deleted after being cited, folders that were renamed under an index, PDFs
saved twice under different names, OCR that read "Sprint 14" as "Sprint 1A", and
an import that died two thirds of the way through. Every one of those is
ordinary, and each breaks a different assumption.

WHAT IS BEING MEASURED IS NOT SURVIVAL. Any system survives a missing file by
returning nothing. The question this asks is narrower and much more important:

    when the evidence is gone, does the system say so, or does it answer anyway?

So the manifest classifies every affected query. `still_answerable` means other
evidence remains and the answer should be unchanged. `degrade_gracefully` means
the evidence is gone and the only correct behaviours are an honest "not found"
or an answer that cites what actually survived. An unchanged confident answer
with dead citations is the failure this module exists to catch, and it is
invisible without a record of what was removed.

The damage is written to a COPY by default. A benchmark you can only run once
is a benchmark nobody runs twice.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STILL, DEGRADE = "still_answerable", "degrade_gracefully"

MODES = ("deleted_files", "renamed_folders", "duplicate_documents",
         "ocr_noise", "broken_links", "interrupted_indexing")

# OCR failures are not random bytes. They are confusions between glyphs that
# look alike, which is why they survive review and then break exact matching.
OCR_CONFUSIONS = [("1", "l"), ("0", "O"), ("5", "S"), ("rn", "m"), ("4", "A"),
                  ("8", "B"), ("2", "Z")]


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def deleted_files(pack: Path, r: random.Random, rate: float = 0.04) -> dict:
    """Remove documents and notes that other artifacts still cite."""
    removed: list[str] = []
    for name in ("documents.jsonl", "notes.jsonl"):
        rows = _read(pack / name)
        keep = [row for row in rows if r.random() >= rate]
        removed.extend(row["id"] for row in rows if row not in keep)
        _write(pack / name, keep)
    return {"mode": "deleted_files", "removed": removed,
            "detail": f"{len(removed)} files deleted after being written",
            "breaks": ("Citations to these ids now point at nothing. Anything "
                       "that still answers confidently from them is inventing.")}


def renamed_folders(pack: Path, r: random.Random) -> dict:
    """Move whole folders. Paths recorded at index time stop resolving."""
    renames = {"Documents/Work": "Documents/Archive/Work-2025",
               "Notes/Daily": "Notes/Journal",
               "Photos/Screenshots": "Photos/Captures"}
    touched: list[str] = []
    for name in ("documents.jsonl", "notes.jsonl", "photos.jsonl"):
        rows = _read(pack / name)
        for row in rows:
            if row.get("folder") in renames:
                row["folder_was"] = row["folder"]
                row["folder"] = renames[row["folder"]]
                touched.append(row["id"])
        _write(pack / name, rows)
    return {"mode": "renamed_folders", "renamed": renames, "affected": touched,
            "detail": f"{len(touched)} files moved between folders",
            "breaks": ("The files still exist and their ids are unchanged. A "
                       "system that reports them missing has indexed the path "
                       "as identity, which means every reorganisation looks "
                       "like data loss.")}


def duplicate_documents(pack: Path, r: random.Random, rate: float = 0.06) -> dict:
    """Save the same document again under a different name."""
    rows = _read(pack / "documents.jsonl")
    copies: list[dict] = []
    for row in rows:
        if r.random() < rate:
            copy = dict(row)
            copy["id"] = f"{row['id']}:copy"
            stem, _, ext = row["name"].rpartition(".")
            copy["name"] = f"{stem} (1).{ext}"
            copy["duplicate_of"] = row["id"]
            copies.append(copy)
    _write(pack / "documents.jsonl", rows + copies)
    return {"mode": "duplicate_documents",
            "added": [c["id"] for c in copies],
            "detail": f"{len(copies)} documents saved twice under new names",
            "breaks": ("'Find the latest version' now has a decoy for every "
                       "hit. Returning both is wrong; returning the copy is "
                       "worse.")}


def ocr_noise(pack: Path, r: random.Random, rate: float = 0.35) -> dict:
    """Corrupt OCR text the way an OCR engine does — glyph confusions."""
    rows = _read(pack / "photos.jsonl")
    damaged: list[str] = []
    for row in rows:
        if not row.get("ocr_text") or r.random() >= rate:
            continue
        text = row["ocr_text"]
        found, replaced = r.choice(OCR_CONFUSIONS)
        if found in text:
            row["ocr_text_was"] = text
            row["ocr_text"] = text.replace(found, replaced, 1)
            damaged.append(row["id"])
    _write(pack / "photos.jsonl", rows)
    return {"mode": "ocr_noise", "affected": damaged,
            "detail": f"{len(damaged)} photos have misread OCR text",
            "breaks": ("Exact-match search over OCR silently misses these. The "
                       "graph already marks OCR edges AMBIGUOUS; a system that "
                       "treats them as certain will state a wrong fact "
                       "confidently.")}


def broken_links(pack: Path, r: random.Random, rate: float = 0.08) -> dict:
    """Point references at artifacts that are not there."""
    rows = _read(pack / "notes.jsonl")
    broken: list[str] = []
    for row in rows:
        if not row.get("references") or r.random() >= rate:
            continue
        index = r.randrange(len(row["references"]))
        row.setdefault("references_was", list(row["references"]))
        row["references"][index] = f"{row['references'][index]}:missing"
        broken.append(row["id"])
    _write(pack / "notes.jsonl", rows)
    return {"mode": "broken_links", "affected": broken,
            "detail": f"{len(broken)} notes cite an artifact that does not exist",
            "breaks": ("A traversal that hits one of these must report a broken "
                       "chain rather than truncating quietly — a short chain "
                       "and a complete one look identical in the answer.")}


def interrupted_indexing(pack: Path, r: random.Random) -> dict:
    """Cut an import off partway, the way closing a laptop does."""
    snapshots = sorted((pack / "snapshots").glob("*")) if (pack / "snapshots").exists() else []
    if not snapshots:
        return {"mode": "interrupted_indexing", "affected": [],
                "detail": "no snapshots to interrupt", "breaks": ""}
    month = snapshots[len(snapshots) * 2 // 3]
    truncated = []
    for path in sorted(month.glob("*.jsonl")):
        rows = _read(path)
        if len(rows) < 2:
            continue
        # Two thirds written, then the process died. The final line is left
        # half-formed on purpose: a loader that only handles clean truncation
        # passes this and still fails on the real thing.
        keep = rows[:max(1, len(rows) * 2 // 3)]
        with path.open("w", encoding="utf-8") as fh:
            for row in keep:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.write(json.dumps(rows[len(keep) % len(rows)])[:40])
        truncated.append(path.name)
    return {"mode": "interrupted_indexing", "month": month.name,
            "affected": truncated,
            "detail": f"snapshot {month.name} truncated mid-write "
                      f"({len(truncated)} files, last line malformed)",
            "breaks": ("Re-running the import must reach a complete state. A "
                       "loader that skips the bad line and reports success has "
                       "lost a third of a month without telling anyone.")}


HANDLERS = {"deleted_files": deleted_files, "renamed_folders": renamed_folders,
            "duplicate_documents": duplicate_documents, "ocr_noise": ocr_noise,
            "broken_links": broken_links,
            "interrupted_indexing": interrupted_indexing}


def classify(pack: Path, manifest: list[dict]) -> list[dict]:
    """Which queries are affected, and what the right behaviour now is."""
    truth_path = pack / "ground_truth.json"
    if not truth_path.exists():
        return []
    truth = json.loads(truth_path.read_text(encoding="utf-8"))

    gone: set[str] = set()
    for entry in manifest:
        gone.update(entry.get("removed", []))
        for note_id in entry.get("affected", []) if entry["mode"] == "broken_links" else ():
            gone.add(note_id)

    out: list[dict] = []
    for query_id, row in truth.items():
        evidence = set(row.get("evidence", []))
        lost = evidence & gone
        if not lost:
            continue
        survives = evidence - gone
        out.append({
            "query_id": query_id, "level": row.get("level"),
            "lost_evidence": sorted(lost),
            "surviving_evidence": sorted(survives),
            "expect": STILL if survives else DEGRADE,
            "why": ("Some evidence survives, so the answer should be unchanged "
                    "and cite what remains."
                    if survives else
                    "Every artifact behind this answer is gone. The only "
                    "correct behaviours are an honest 'not found' or an answer "
                    "that names what it could actually reach."),
        })
    return out


def apply(pack: Path, modes: list[str], seed: int = 99) -> dict:
    r = random.Random(seed)
    manifest = [HANDLERS[mode](pack, r) for mode in modes]
    affected = classify(pack, manifest)
    report = {
        "seed": seed, "modes": modes, "damage": manifest,
        "affected_queries": affected,
        "summary": {
            "queries_affected": len(affected),
            "still_answerable": sum(1 for a in affected if a["expect"] == STILL),
            "must_degrade_gracefully": sum(1 for a in affected
                                           if a["expect"] == DEGRADE),
        },
    }
    (pack / "failures.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # pragma: no cover
        pass

    ap = argparse.ArgumentParser(description="Damage an SDL pack on purpose")
    ap.add_argument("--from", dest="source", required=True,
                    help="a directory generate.py wrote")
    ap.add_argument("--out", help="where to write the damaged copy")
    ap.add_argument("--in-place", action="store_true",
                    help="damage the pack where it sits (destructive)")
    ap.add_argument("--modes", default="all",
                    help=f"comma-separated: {', '.join(MODES)}")
    ap.add_argument("--seed", type=int, default=99)
    args = ap.parse_args(argv)

    source = Path(args.source)
    if not (source / "manifest.json").exists():
        raise SystemExit(f"{source} is not a generated pack (no manifest.json)")

    modes = MODES if args.modes == "all" else tuple(
        m.strip() for m in args.modes.split(",") if m.strip())
    unknown = [m for m in modes if m not in HANDLERS]
    if unknown:
        raise SystemExit(f"unknown mode(s): {', '.join(unknown)}")

    if args.in_place:
        target = source
    else:
        target = Path(args.out) if args.out else source.parent / f"{source.name}-damaged"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)

    report = apply(target, list(modes), seed=args.seed)

    print(f"damaged {target}")
    for entry in report["damage"]:
        print(f"  {entry['mode']:<22} {entry['detail']}")
    summary = report["summary"]
    print(f"  {summary['queries_affected']} queries affected: "
          f"{summary['still_answerable']} should still answer, "
          f"{summary['must_degrade_gracefully']} must degrade gracefully")
    print(f"  -> {target / 'failures.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
