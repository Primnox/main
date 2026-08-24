"""Generate a Synthetic Life pack.

    python sdl/generate.py --pack office-500 --out ./sdl-out
    python sdl/generate.py --pack enterprise-50k --out ./sdl-out
    python sdl/generate.py --list

Writes the deliverables the specification asks for: manifest.json,
timeline.json, memory.jsonl, graph.jsonl, queries.json, ground_truth.json, and
monthly snapshot directories.

Monthly snapshots are CUMULATIVE by month rather than copies of everything: each
directory holds what happened in that month, and the dataset is the union. That
is how the corpus is meant to be loaded — month by month, testing incremental
indexing — and copying the whole world 24 times would turn a 40MB pack into a
gigabyte of duplicates.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdl import VERSION, artifacts, recurrence as calendar_gen, code as code_gen  # noqa: E402
from sdl import contradictions, graph as graph_mod, memory as memory_gen        # noqa: E402
from sdl import packs, truth, validate, world as world_mod                      # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> int:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def _by_month(world, months: int, streams: dict[str, list[dict]]) -> list[dict]:
    """Per-month counts, bucketed in one pass.

    The obvious spelling — a list comprehension filtering each stream per month
    — is quadratic, and on the full pack that is 24 passes over 120,000 chats to
    produce a summary nobody would wait for.
    """
    tally = {name: [0] * months for name in streams}
    for name, rows in streams.items():
        counts = tally[name]
        for row in rows:
            month = row.get("month")
            if month is not None and 0 <= month < months:
                counts[month] += 1
    return [{"month": m, "label": world.month_label(m),
             "people_active": len(world.active_people(m)),
             **{name: tally[name][m] for name in streams}}
            for m in range(months)]


def generate(pack_name: str, out_dir: Path, seed: int = 20260815) -> dict:
    pack = packs.get(pack_name)
    started = time.perf_counter()

    world = world_mod.build(seed=seed, months=pack.months,
                            people_count=pack.people, project_count=pack.projects,
                            repo_count=pack.repos, dispute_count=pack.disputes)

    memories = memory_gen.generate(world, volume=pack.memories,
                                   promote=pack.promoted)
    chats = artifacts.chats(world, pack.chats)
    emails = artifacts.emails(world, pack.emails)
    meetings = artifacts.meetings(world, pack.meetings)
    documents = artifacts.documents(world, pack.documents)
    symbols = artifacts.code_symbols(world, pack.symbols)
    photos = artifacts.photos(world, pack.photos)

    calendar = calendar_gen.build(world, budget=pack.calendar)
    commits = code_gen.commits(world, pack.commits)
    issues = code_gen.issues(world, commits, pack.issues)
    prs = code_gen.pull_requests(world, commits, issues, pack.prs)
    todos = code_gen.todos(world, pack.todos)
    conflicts = contradictions.build(world)

    # Order matters here. Tasks point back at the conversation that raised them
    # and notes chain across artifact types, so both need the artifacts they
    # reference to exist already — a reference to an id that will be generated
    # later is a dangling edge dressed up as a feature.
    tasks = artifacts.tasks(world, pack.tasks, chats=chats, emails=emails,
                            meetings=meetings)
    notes = artifacts.notes(world, pack.notes, meetings=meetings, emails=emails,
                            documents=documents, commits=commits)

    graph = graph_mod.build(world, chats=chats, emails=emails, meetings=meetings,
                            documents=documents, symbols=symbols, photos=photos,
                            calendar=calendar, tasks=tasks, notes=notes,
                            commits=commits, issues=issues, prs=prs, todos=todos,
                            conflicts=conflicts)
    queries = truth.build(world, memories=memories, chats=chats, emails=emails,
                          meetings=meetings, documents=documents,
                          symbols=symbols, graph=graph, notes=notes, tasks=tasks,
                          calendar=calendar, commits=commits, issues=issues,
                          prs=prs, todos=todos, photos=photos,
                          conflicts=conflicts, budget=pack.queries)
    findings = validate.run(world, memories=memories, chats=chats, emails=emails,
                            meetings=meetings, documents=documents,
                            symbols=symbols, photos=photos, graph=graph,
                            queries=queries, calendar=calendar, tasks=tasks,
                            notes=notes, commits=commits, issues=issues,
                            prs=prs, todos=todos, conflicts=conflicts)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "assets").mkdir(exist_ok=True)
    (out_dir / "workspaces").mkdir(exist_ok=True)

    _write_jsonl(out_dir / "memory.jsonl", memories)
    # The row marker goes LAST so an attribute of the same name cannot shadow
    # it. Spreading the payload after `{"kind": "node"}` let a document node
    # carrying its own `kind` overwrite the marker, and every such node came
    # back from the file as an edge with no source.
    _write_jsonl(out_dir / "graph.jsonl",
                 [{**n, "kind": "node"} for n in graph["nodes"]]
                 + [{**e, "kind": "edge"} for e in graph["edges"]])
    _write_jsonl(out_dir / "chats.jsonl", chats)
    _write_jsonl(out_dir / "emails.jsonl", emails)
    _write_jsonl(out_dir / "meetings.jsonl", meetings)
    _write_jsonl(out_dir / "documents.jsonl", documents)
    _write_jsonl(out_dir / "photos.jsonl", photos)
    _write_jsonl(out_dir / "calendar.jsonl", calendar["events"])
    _write_jsonl(out_dir / "tasks.jsonl", tasks)
    _write_jsonl(out_dir / "notes.jsonl", notes)
    _write_jsonl(out_dir / "commits.jsonl", commits)
    _write_jsonl(out_dir / "issues.jsonl", issues)
    _write_jsonl(out_dir / "pull_requests.jsonl", prs)
    _write_jsonl(out_dir / "todos.jsonl", todos)
    _write_jsonl(out_dir / "conflicts.jsonl", conflicts["claims"])

    (out_dir / "queries.json").write_text(
        json.dumps([{k: v for k, v in q.items()
                     if k not in ("answer", "evidence", "graph_path")}
                    for q in queries], indent=2, ensure_ascii=False),
        encoding="utf-8")
    # Kept apart from queries.json on purpose: a system under test may read the
    # questions, and must never be handed the answers in the same file. Evidence
    # and the expected graph path live here too — a system told which artifacts
    # justify an answer can cite them without having found them, and citation is
    # a quarter of the score.
    (out_dir / "ground_truth.json").write_text(
        json.dumps({q["id"]: {"answer": q["answer"], "evidence": q["evidence"],
                              "graph_path": q["graph_path"],
                              "as_of_month": q["as_of_month"],
                              "level": q["level"], "kind": q["kind"],
                              "rationale": q["rationale"],
                              "subsystem": q["subsystem"]} for q in queries},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "contradictions.json").write_text(
        json.dumps(conflicts["resolutions"], indent=2, ensure_ascii=False),
        encoding="utf-8")

    timeline = {
        "months": pack.months,
        "start": world.month_date(0).isoformat(),
        "events": world.events,
        "by_month": _by_month(world, pack.months, {
            "memories": memories, "chats": chats, "emails": emails,
            "meetings": meetings, "documents": documents,
            "calendar": calendar["events"], "tasks": tasks, "notes": notes,
            "commits": commits, "issues": issues,
        }),
        "series": [{"id": s.id, "title": s.title, "cadence": s.cadence,
                    "start_month": s.start_month, "end_month": s.end_month,
                    "started_by": s.started_by, "ended_by": s.ended_by}
                   for s in calendar["series"]],
    }
    (out_dir / "timeline.json").write_text(
        json.dumps(timeline, indent=2), encoding="utf-8")

    # Monthly snapshots: what happened THAT month. Bucketed in one pass per
    # stream for the same reason as the timeline — the readable version rescans
    # every stream once per month.
    snapshots = out_dir / "snapshots"
    snapshots.mkdir(exist_ok=True)
    for m in range(pack.months):
        (snapshots / world.month_label(m)).mkdir(exist_ok=True)
    for name, rows in (("memory", memories), ("chats", chats),
                       ("emails", emails), ("meetings", meetings),
                       ("documents", documents), ("calendar", calendar["events"]),
                       ("tasks", tasks), ("notes", notes), ("commits", commits),
                       ("issues", issues)):
        buckets: list[list[dict]] = [[] for _ in range(pack.months)]
        for row in rows:
            month = row.get("month")
            if month is not None and 0 <= month < pack.months:
                buckets[month].append(row)
        for m in range(pack.months):
            _write_jsonl(snapshots / world.month_label(m) / f"{name}.jsonl",
                         buckets[m])

    manifest = {
        "sdl_version": VERSION,
        "pack": pack.as_dict(),
        "seed": seed,
        "generated_s": round(time.perf_counter() - started, 2),
        "subject": world.subject,
        "counts": {
            "months": pack.months,
            "people": len(world.people),
            "projects": len(world.projects),
            "repositories": len(world.repos),
            "memories": len(memories),
            "memories_promoted": len(memory_gen.promoted_ids(memories)),
            "chats": len(chats), "emails": len(emails),
            "meetings": len(meetings), "documents": len(documents),
            "symbols": len(symbols), "photos": len(photos),
            "calendar_events": len(calendar["events"]),
            "recurring_series": len(calendar["series"]),
            "tasks": len(tasks), "notes": len(notes),
            "commits": len(commits), "issues": len(issues),
            "pull_requests": len(prs), "todos": len(todos),
            "disputes": len(conflicts["resolutions"]),
            "graph_nodes": len(graph["nodes"]),
            "graph_edges": len(graph["edges"]),
            "queries": len(queries),
            "queries_by_level": {
                str(level): sum(1 for q in queries if q["level"] == level)
                for level in sorted({q["level"] for q in queries})},
        },
        "validation": validate.summarise(findings),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "validation.json").write_text(
        json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")

    return manifest


def main(argv=None) -> int:
    # cp1252 cannot encode the em dash in the summary below; see sdl/inject.py.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # pragma: no cover
        pass

    ap = argparse.ArgumentParser(description="Primnox Synthetic Digital Life")
    ap.add_argument("--pack", default=packs.DEFAULT)
    ap.add_argument("--out", default="./sdl-out")
    ap.add_argument("--seed", type=int, default=20260815)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        for name, pack in packs.PACKS.items():
            print(f"  {name:16} {pack.purpose}")
        return 0

    out = Path(args.out) / args.pack
    manifest = generate(args.pack, out, seed=args.seed)

    counts = manifest["counts"]
    validation = manifest["validation"]
    print(f"SDL {VERSION} — pack {args.pack}, seed {args.seed}, "
          f"{manifest['generated_s']}s")
    print(f"  {counts['months']} months, {counts['people']} people, "
          f"{counts['projects']} projects, {counts['repositories']} repositories")
    print(f"  memories {counts['memories']} ({counts['memories_promoted']} "
          f"worth keeping)  chats {counts['chats']}  emails {counts['emails']}")
    print(f"  calendar {counts['calendar_events']} across "
          f"{counts['recurring_series']} series  meetings {counts['meetings']}  "
          f"tasks {counts['tasks']}  notes {counts['notes']}")
    print(f"  commits {counts['commits']}  issues {counts['issues']}  "
          f"PRs {counts['pull_requests']}  TODOs {counts['todos']}")
    print(f"  documents {counts['documents']}  symbols {counts['symbols']}  "
          f"photos {counts['photos']}  disputes {counts['disputes']}")
    print(f"  graph {counts['graph_nodes']} nodes / {counts['graph_edges']} edges")
    levels = "  ".join(f"L{lv} {n}" for lv, n in
                       sorted(counts["queries_by_level"].items()))
    print(f"  queries {counts['queries']} with ground truth — {levels}")
    print(f"  validation {validation['passed']}/{validation['rules']} rules passed")
    for failure in validation["failures"]:
        print(f"     FAILED {failure['rule']}: {failure['detail']}")
    print(f"  -> {out}")

    # Non-zero when the dataset disagrees with itself. A pack that fails its own
    # rules must not become a benchmark.
    return 1 if validation["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
