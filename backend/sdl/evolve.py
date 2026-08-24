"""The life keeps going after the pack is generated.

    python sdl/evolve.py --from ./sdl-out/office-500            # one tick
    python sdl/evolve.py --from ./sdl-out/office-500 --ticks 6
    python sdl/evolve.py --from ./sdl-out/office-500 --status

A frozen dataset measures a system that indexed once. Nobody uses software that
way: chats arrive, a preference reverses, a project changes hands, a file is
renamed, work resumes on something abandoned in March. Each tick here extends
the life by one month and writes ONLY what is new, which is the shape a real
system receives its data in.

THE STALE LIST IS THE POINT. Every tick records which of the base pack's
questions now have a different answer. A system that indexed the pack once and
stopped will still answer those correctly-as-of-generation and be wrong, and it
will be wrong CONFIDENTLY — there is nothing in its store to suggest otherwise.
That failure is invisible against a static benchmark, which is exactly why it
survives so long in real systems.

Ticks are deterministic in the tick NUMBER, not in call order: tick 3 is the
same on every machine whether or not ticks 1 and 2 were run in this process.
A generator whose output depends on how many times it has been called cannot be
used to compare two versions of anything.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdl import code as code_gen, packs, world as world_mod  # noqa: E402

# Preferences do not only move forward. Reverting to something abandoned a year
# ago is common, and it is the case that breaks a store which treats "newest
# statement wins" as "the chain only ever grows".
REVERT_CHANCE = 0.35


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_world(pack_dir: Path):
    manifest = _read_json(pack_dir / "manifest.json")
    if not manifest:
        raise SystemExit(f"{pack_dir} is not a generated pack (no manifest.json)")
    pack = packs.get(manifest["pack"]["name"])
    world = world_mod.build(seed=manifest["seed"], months=pack.months,
                            people_count=pack.people,
                            project_count=pack.projects, repo_count=pack.repos,
                            dispute_count=pack.disputes)
    return world, pack, manifest


def _base_queries(pack_dir: Path) -> list[dict]:
    """Base questions joined to their answers, so staleness can be reported
    against the ids a scorer already knows."""
    questions = _read_json(pack_dir / "queries.json") or []
    truth = _read_json(pack_dir / "ground_truth.json") or {}
    return [{**q, **truth.get(q["id"], {})} for q in questions]


def tick(world, pack, tick_no: int, base: list[dict]) -> dict:
    """One month of new life, and what it invalidates."""
    month = pack.months + tick_no - 1
    # `month_date` is pure arithmetic from the start date and has no upper
    # bound, so it extends past the pack correctly. An open-coded version here
    # put tick 1 of a 24-month pack in 2028.
    label = world.month_label(month)
    r = random.Random(world.seed ^ (0xE001 + tick_no * 7919))
    cast = world.active_people(world.months - 1) or world.people
    changes: list[dict] = []
    new_truth: list[dict] = []
    stale: list[dict] = []

    def supersede(question: str, new_answer, evidence: list[str], why: str,
                  kind: str, level: int, subsystem: str) -> None:
        """Record a new answer, and flag the base query it displaces."""
        new_truth.append({"id": f"q:t{tick_no:02d}:{len(new_truth):03d}",
                          "kind": kind, "level": level, "question": question,
                          "answer": new_answer, "evidence": evidence,
                          "as_of_month": month, "graph_path": [],
                          "rationale": why, "subsystem": subsystem})
        for row in base:
            if row.get("question") != question or row.get("answer") == new_answer:
                continue
            # A restated preference and a reversed one are both "stale", and
            # treating them as the same thing overstates the damage: one means
            # the user changed their mind, the other only means the newest
            # citation moved. A system returning the old row is wrong either
            # way, but only the first is wrong about a fact.
            was, now = row.get("answer"), new_answer
            fact_changed = True
            if isinstance(was, dict) and isinstance(now, dict):
                fact_changed = was.get("text") != now.get("text")
            stale.append({"query_id": row["id"], "question": question,
                          "was": was, "now": now, "changed_in_tick": tick_no,
                          "kind": "fact_changed" if fact_changed
                                  else "evidence_moved"})

    # ── a preference moves ────────────────────────────────────────────────
    topic, chain = world_mod.PREFERENCE_ARCS[tick_no % len(world_mod.PREFERENCE_ARCS)]
    if len(chain) > 1 and r.random() < REVERT_CHANCE:
        statement, kind_of_change = chain[0], "reverted"
    else:
        statement, kind_of_change = chain[-1], "restated"
    text = f"{world.subject['name'].split()[0]} {statement}."
    memory_row = {
        "id": f"mem:t{tick_no:02d}:000", "month": month,
        "timestamp": f"{label}-15", "text": text, "category": "personal",
        "confidence": "stated", "topic": topic,
        "source": f"chat/{label}/msg_{r.randrange(1000, 9999)}.md",
        "supersedes": None, "salient": True, "promoted": True,
    }
    changes.append({"what": "preference", "topic": topic,
                    "change": kind_of_change, "now": text})
    supersede(f"What is the user's current preference regarding {topic}?",
              {"text": text, "memory_id": memory_row["id"]},
              [memory_row["id"]],
              f"Superseded in tick {tick_no} ({kind_of_change}).",
              "preference", 1, "Memory Service")

    # ── work continues in a repository ────────────────────────────────────
    repo = world.repos[tick_no % len(world.repos)]
    commits: list[dict] = []
    for i in range(r.randrange(3, 9)):
        author = cast[(tick_no * 3 + i) % len(cast)]
        commits.append({
            "sha": code_gen.commit_sha(world.seed, repo.name, month,
                                       f"t{tick_no}:{i}"),
            "repo": repo.name, "project": repo.project_id, "month": month,
            "date": f"{label}-{10 + i:02d}", "author": author.id,
            "author_name": author.name,
            "message": f"{r.choice(code_gen.CHORES)} in {repo.name}",
            "files": [f"src/{repo.language}/mod_{(tick_no * 5 + i) % 200:03d}"],
            "introduces": None, "adopts": None,
        })
    latest = commits[-1]
    changes.append({"what": "commits", "repo": repo.name, "count": len(commits)})
    supersede(f"What was the last change made to {repo.name}, and by whom?",
              {"sha": latest["sha"], "message": latest["message"],
               "author": latest["author"], "month": month},
              [latest["sha"]],
              f"New commits landed in tick {tick_no}.",
              "resume_repo", 5, "Workspace System")

    # ── a project changes hands ───────────────────────────────────────────
    project = world.projects[(tick_no * 11) % len(world.projects)]
    previous = project.owner_at(world.months - 1)
    candidates = [p for p in cast if p.id != previous]
    if candidates:
        new_owner = candidates[(tick_no * 5) % len(candidates)]
        changes.append({"what": "ownership", "project": project.name,
                        "from": previous, "to": new_owner.id})
        supersede(f"Who currently owns the project {project.name}?",
                  new_owner.id, [project.id],
                  f"Handed over in tick {tick_no}.", "ownership", 1,
                  "Knowledge Service")

    # ── a file is renamed ─────────────────────────────────────────────────
    renamed = {
        "id": f"doc:t{tick_no:02d}:000",
        "month": month, "date": f"{label}-05",
        "folder": "Documents/Work",
        "name": f"{project.name.lower().replace(' ', '-')}-handover-v2.md",
        "renamed_from": f"{project.name.lower().replace(' ', '-')}-handover.md",
        "kind": "notes", "author": world.subject["id"], "project": project.id,
        "slides": None, "duplicate_of": None, "draft": False,
    }
    changes.append({"what": "rename", "file": renamed["name"],
                    "was": renamed["renamed_from"]})

    # ── a meeting is rescheduled ──────────────────────────────────────────
    calendar_rows: list[dict] = []
    series = world.series[tick_no % len(world.series)] if world.series else None
    if series:
        calendar_rows.append({
            "id": f"cal:t{tick_no:02d}:000", "series": series.id,
            "series_title": series.title, "title": series.title,
            "kind": series.kind, "recurring": True, "month": month,
            "date": f"{label}-12", "weekday": "Tuesday",
            "attendees": list(series.attendees), "status": "moved",
            "moved_to": f"{label}-14",
        })
        changes.append({"what": "rescheduled", "series": series.title})

    # ── conversations, and a task closes ──────────────────────────────────
    chats = [{
        "id": f"chat:t{tick_no:02d}:{i:03d}", "thread": f"thread:t{tick_no:02d}",
        "month": month, "date": f"{label}-{5 + i:02d}",
        "author": cast[(tick_no + i) % len(cast)].id,
        "author_name": cast[(tick_no + i) % len(cast)].name,
        "text": r.choice([
            f"picking {project.name} back up where we left it",
            f"{repo.name} is green again after the weekend",
            f"who has context on {project.name} now?",
            text.lower(),
        ]),
        "mentions_project": project.id, "edited": False, "deleted": False,
    } for i in range(r.randrange(4, 12))]

    tasks = [{
        "id": f"task:t{tick_no:02d}:{i:03d}", "month": month,
        "date": f"{label}-08",
        "title": f"Follow up on {project.name} handover",
        "project": project.id, "assignee": cast[(tick_no * 7 + i) % len(cast)].id,
        "status": "todo", "completed_month": None, "priority": "normal",
        "source": chats[0]["id"] if chats else None,
    } for i in range(r.randrange(1, 4))]

    return {
        "tick": tick_no, "month": month, "label": label,
        "changes": changes,
        "rows": {"memory": [memory_row], "commits": commits, "chats": chats,
                 "tasks": tasks, "documents": [renamed],
                 "calendar": calendar_rows},
        "ground_truth": new_truth,
        "stale": stale,
    }


def write_tick(pack_dir: Path, result: dict) -> Path:
    out = pack_dir / "deltas" / f"tick-{result['tick']:03d}"
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in result["rows"].items():
        if rows:
            _write_jsonl(out / f"{name}.jsonl", rows)
    (out / "changes.json").write_text(
        json.dumps({"tick": result["tick"], "month": result["month"],
                    "label": result["label"], "changes": result["changes"]},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "ground_truth.json").write_text(
        json.dumps({q["id"]: q for q in result["ground_truth"]}, indent=2,
                   ensure_ascii=False), encoding="utf-8")
    (out / "stale.json").write_text(
        json.dumps(result["stale"], indent=2, ensure_ascii=False),
        encoding="utf-8")
    return out


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # pragma: no cover
        pass

    ap = argparse.ArgumentParser(description="Keep an SDL pack living")
    ap.add_argument("--from", dest="source", required=True)
    ap.add_argument("--ticks", type=int, default=1)
    ap.add_argument("--start", type=int, default=None,
                    help="first tick number (default: continue from the pack)")
    ap.add_argument("--status", action="store_true",
                    help="report what has already been applied and stop")
    args = ap.parse_args(argv)

    pack_dir = Path(args.source)
    world, pack, _ = load_world(pack_dir)
    existing = sorted((pack_dir / "deltas").glob("tick-*")) \
        if (pack_dir / "deltas").exists() else []

    if args.status:
        print(f"{pack_dir.name}: {len(existing)} ticks applied")
        for path in existing:
            changes = _read_json(path / "changes.json") or {}
            summary = ", ".join(c["what"] for c in changes.get("changes", []))
            print(f"  {path.name}  month {changes.get('label', '?')}  {summary}")
        return 0

    base = _base_queries(pack_dir)
    start = args.start if args.start is not None else len(existing) + 1

    total_stale: list[dict] = []
    for n in range(start, start + args.ticks):
        result = tick(world, pack, n, base)
        out = write_tick(pack_dir, result)
        total_stale.extend(result["stale"])
        rows = sum(len(v) for v in result["rows"].values())
        print(f"tick {n:>3}  month {result['label']}  {rows} new rows  "
              f"{len(result['stale'])} answers now stale  -> {out.name}")
        for change in result["changes"]:
            detail = {k: v for k, v in change.items() if k != "what"}
            print(f"     {change['what']:<12} {detail}")

    if total_stale:
        facts = [s for s in total_stale if s["kind"] == "fact_changed"]
        moved = len(total_stale) - len(facts)
        print(f"\n{len(total_stale)} base-pack answers are now wrong "
              f"({len(facts)} because the fact changed, {moved} because the "
              f"newest evidence moved). A system that indexed once will still "
              f"return the old ones:")
        for row in facts[:5]:
            print(f"  {row['query_id']}  {row['question']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
