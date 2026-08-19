"""Self-tests the dataset carries with it.

A generated corpus nobody checks is a corpus that quietly stops being coherent.
These run over the produced data — not over the generator — so a change that
breaks the world is caught by the artefact, and a pack that ships is a pack that
has already proved it agrees with itself.

Each rule is one of the assertions the specification asks for, phrased as
"what would be wrong if this failed" rather than as a bare comparison.
"""
from __future__ import annotations

import unicodedata

from . import code as code_mod, contradictions, graph as graph_mod
from .world import World


def _mixed_script(text: str) -> bool:
    """True when one word mixes alphabets — "Ваsquez", Cyrillic then Latin.

    This is not pedantry about Unicode. A name half in one alphabet renders
    normally, survives review, and then fails every string comparison a system
    under test makes against it — so it presents as a retrieval bug in the thing
    being measured rather than as corruption in the corpus. Accented Latin is
    fine and common; two alphabets inside one word never is.
    """
    for word in text.split():
        scripts = set()
        for ch in word:
            if not ch.isalpha():
                continue
            name = unicodedata.name(ch, "")
            scripts.add(name.split(" ")[0] if name else "?")
        if len(scripts) > 1:
            return True
    return False


def run(world: World, *, memories, chats, emails, meetings, documents,
        symbols, photos, graph, queries, calendar=None, tasks=(), notes=(),
        commits=(), issues=(), prs=(), todos=(), conflicts=None) -> list[dict]:
    """Every rule, with a pass/fail and what a failure means."""
    findings: list[dict] = []
    tasks, notes = list(tasks), list(notes)
    commits, issues, prs, todos = list(commits), list(issues), list(prs), list(todos)
    cal_events = list(calendar["events"]) if calendar else []
    cal_series = list(calendar["series"]) if calendar else []

    def check(name: str, ok: bool, detail: str, why: str) -> None:
        findings.append({"rule": name, "ok": bool(ok),
                         "detail": detail, "matters_because": why})

    known_people = {p.id for p in world.people} | {world.subject["id"]}
    known_projects = {p.id for p in world.projects}
    known_months = range(0, world.months)

    # ── the cast is consistent ────────────────────────────────────────────
    bad_authors = [c["id"] for c in chats if c["author"] not in known_people]
    check("chat authors exist", not bad_authors,
          f"{len(bad_authors)} chats from unknown people",
          "A message from someone who does not exist makes every 'who said "
          "this' query unanswerable and hides a real retrieval failure.")

    bad_recipients = [e["id"] for e in emails
                      if any(t not in known_people for t in e["to"])
                      or e["from"] not in known_people]
    check("emails reference existing people", not bad_recipients,
          f"{len(bad_recipients)} emails with unknown participants",
          "Mail to a stranger cannot be traversed to, so multi-hop queries "
          "silently return less than the truth.")

    bad_attendees = [m["id"] for m in meetings
                     if any(a not in known_people for a in m["attendees"])]
    check("meetings reference existing people", not bad_attendees,
          f"{len(bad_attendees)} meetings with unknown attendees",
          "Attendance is the edge multi-hop questions travel along.")

    # ── projects and repositories ─────────────────────────────────────────
    bad_projects = [d["id"] for d in documents if d["project"] not in known_projects]
    check("documents reference existing projects", not bad_projects,
          f"{len(bad_projects)} documents on unknown projects",
          "A document about nothing cannot be found by asking about the thing.")

    repos = set(world.repo_names())
    bad_repos = ([s["id"] for s in symbols if s["repo"] not in repos]
                 + [c["sha"] for c in commits if c["repo"] not in repos])
    check("code belongs to known repositories", not bad_repos,
          f"{len(bad_repos)} symbols or commits in unknown repos",
          "Commit-to-repo edges are half of the hardest query in the set.")

    # ── the code history ──────────────────────────────────────────────────
    check("no chore shares a word with a feature name",
          code_mod.feature_vocabulary_is_disjoint(),
          "filler commit text overlaps the feature vocabulary",
          "A chore worded 'add response caching' gives 'which repository "
          "introduced caching first' a second defensible answer, and the "
          "benchmark starts marking correct systems wrong.")

    introduced: dict[str, list[dict]] = {}
    for commit in commits:
        if commit["introduces"]:
            introduced.setdefault(commit["introduces"], []).append(commit)
    twice = [name for name, rows in introduced.items() if len(rows) > 1]
    check("each feature is introduced exactly once", not twice,
          f"{len(twice)} features introduced by more than one commit"
          + (f" ({twice[0]})" if twice else ""),
          "'Which repository was FIRST' has no answer if two commits claim it.")

    late_adopters = [
        f["name"] for f in world.features
        for a in f["adopters"] if a["month"] <= f["first_month"]]
    check("adoption follows introduction", not late_adopters,
          f"{len(late_adopters)} features adopted no later than they were introduced",
          "A repository that adopted a feature before it existed makes the "
          "chronology of the whole code history untrustworthy.")

    bad_close = [i["id"] for i in issues
                 if i["closed_month"] is not None and i["closed_month"] < i["month"]]
    check("issues close after they open", not bad_close,
          f"{len(bad_close)} issues closed before they were filed",
          "A graph stores this without complaint and every 'what fixed this' "
          "answer built on it is nonsense.")

    known_shas = {c["sha"] for c in commits}
    known_issues = {i["id"] for i in issues}
    bad_pr = [p["id"] for p in prs
              if any(s not in known_shas for s in p["commits"])
              or any(i not in known_issues for i in p["closes"])]
    check("pull requests carry real commits and close real issues", not bad_pr,
          f"{len(bad_pr)} pull requests referencing something that does not exist",
          "The PR is the middle hop in 'who reviewed the change that "
          "introduced X'; a broken link truncates the traversal silently.")

    # ── the calendar ──────────────────────────────────────────────────────
    series_ids = {s.id for s in cal_series}
    orphan_events = [e["id"] for e in cal_events
                     if e["series"] and e["series"] not in series_ids]
    check("recurring events belong to a retained series", not orphan_events,
          f"{len(orphan_events)} events pointing at a series that was not expanded",
          "An occurrence with no series behind it looks like a one-off, and "
          "'which meetings recur' quietly undercounts.")

    incomplete = []
    for series in cal_series:
        end = series.end_month if series.end_month is not None else world.months
        expected_months = set(range(series.start_month, min(end, world.months)))
        seen = {e["month"] for e in cal_events if e["series"] == series.id}
        if expected_months - seen:
            incomplete.append(series.id)
    check("retained series are expanded in full", not incomplete,
          f"{len(incomplete)} series missing months from their run",
          "A recurring meeting missing occurrences is indistinguishable from "
          "one repeatedly cancelled, so the benchmark scores its own sampling.")

    event_months = {e["month"] for e in world.events}
    ambiguous_lapse = [s.id for s in cal_series
                       if s.ended_by is None and s.end_month in event_months]
    check("lapsed series avoid life-event months", not ambiguous_lapse,
          f"{len(ambiguous_lapse)} series lapse in the same month as a life event",
          "'Which meetings stopped because of the reorg' would then have two "
          "defensible answers, and a correct system is marked wrong for a "
          "distinction the data does not carry.")

    # ── tasks and notes ───────────────────────────────────────────────────
    bad_tasks = [t["id"] for t in tasks
                 if t["completed_month"] is not None
                 and t["completed_month"] < t["month"]]
    check("tasks complete after they start", not bad_tasks,
          f"{len(bad_tasks)} tasks completed before they were created",
          "Every 'what was open at month N' answer is wrong by the same rows.")

    artifact_ids = ({c["id"] for c in chats} | {e["id"] for e in emails}
                    | {m["id"] for m in meetings} | {d["id"] for d in documents}
                    | known_shas)
    dangling_refs = [n["id"] for n in notes
                     if any(ref not in artifact_ids for ref in n["references"])]
    check("note references resolve", not dangling_refs,
          f"{len(dangling_refs)} notes referencing an artifact that does not exist",
          "The note chain is the multi-hop path; a broken link in it turns a "
          "traversal test into a test of how gracefully a system gives up.")

    future_refs = []
    by_id = {}
    for row in list(chats) + list(emails) + list(meetings) + list(documents):
        by_id[row["id"]] = row["month"]
    for commit in commits:
        by_id[commit["sha"]] = commit["month"]
    for note in notes:
        for ref in note["references"]:
            if ref in by_id and by_id[ref] > note["month"]:
                future_refs.append(note["id"])
    check("notes never reference the future", not future_refs,
          f"{len(future_refs)} notes citing an artifact written after them",
          "A citation that points forwards in time makes every temporal "
          "answer derived from the chain indefensible.")

    # ── contradictions ────────────────────────────────────────────────────
    check("contradictions resolve by the stated rule",
          contradictions.rule_holds(world),
          "a dispute's recorded answer disagrees with authority-then-recency",
          "The answer key and the rule must be the same thing. If they drift, "
          "the benchmark is testing whichever one the reader happened to trust.")

    if conflicts:
        shapes = {r["tests"] for r in conflicts["resolutions"]}
        check("both halves of the resolution rule are exercised",
              shapes >= {"authority", "recency"},
              f"dispute shapes present: {sorted(shapes) or 'none'}",
              "A rule only ever tested one way is a rule nobody has tested: "
              "pure-recency and pure-authority implementations would both pass.")

    # ── time ──────────────────────────────────────────────────────────────
    out_of_range = [m["id"] for m in memories if m["month"] not in known_months]
    check("memories fall inside the timeline", not out_of_range,
          f"{len(out_of_range)} memories outside month range",
          "A memory dated outside the life makes chronology meaningless.")

    chain_errors = []
    by_id = {m["id"]: m for m in memories}
    for m in memories:
        prior = m.get("supersedes")
        if prior and by_id.get(prior, {}).get("month", -1) > m["month"]:
            chain_errors.append(m["id"])
    check("supersession respects chronology", not chain_errors,
          f"{len(chain_errors)} memories supersede a LATER memory",
          "If an older statement can replace a newer one, 'what is true now' "
          "has no defensible answer and the contradiction tests are void.")

    # ── the graph ─────────────────────────────────────────────────────────
    node_ids = {n["id"] for n in graph["nodes"]}
    dangling = [e for e in graph["edges"]
                if e["source"] not in node_ids or e["target"] not in node_ids]
    check("no dangling edges", not dangling,
          f"{len(dangling)} edges point at missing nodes",
          "A dangling edge crashes a traversal or silently truncates it.")

    no_prov = graph_mod.missing_provenance(graph)
    check("every edge has provenance", not no_prov,
          f"{len(no_prov)} edges without a source (or inferred without evidence)",
          "An edge that cannot say where it came from cannot be explained to a "
          "user, checked by a reviewer, or removed when its source is deleted.")

    orphan_ids = graph_mod.orphans(graph)
    check("orphans are rare", len(orphan_ids) <= max(5, len(graph["nodes"]) // 200),
          f"{len(orphan_ids)} nodes touched by no edge",
          "A node nothing connects to is unreachable, so indexing it is work "
          "that can never pay off.")

    aliases = [p for p in world.projects if p.renamed_from]
    alias_edges = [e for e in graph["edges"] if e["relation"] == "renamed_from"]
    check("renames preserve their old name", len(alias_edges) >= len(aliases),
          f"{len(aliases)} renamed projects, {len(alias_edges)} alias edges",
          "Without the alias, every document written under the old name "
          "becomes unfindable the day the project is renamed.")

    # ── the text itself ───────────────────────────────────────────────────
    names = ([p.name for p in world.people] + [p.name for p in world.projects]
             + list(world.orgs) + [world.subject["name"]]
             + [f["name"] for f in world.subject["family"]])
    mixed = [n for n in names if _mixed_script(n)]
    check("names use one alphabet", not mixed,
          f"{len(mixed)} names mix scripts" + (f" ({mixed[0]!r})" if mixed else ""),
          "A half-Cyrillic surname looks correct on screen and fails every name "
          "match, so the system under test is blamed for corrupt input data.")

    # ── the answers ───────────────────────────────────────────────────────
    empty = [q["id"] for q in queries
             if q["answer"] in (None, [], {}, "")]
    check("every query has an answer", not empty,
          f"{len(empty)} queries with an empty ground truth",
          "A question with no known answer cannot score a retrieval system; it "
          "can only be eyeballed, which is what this dataset exists to replace.")

    unevidenced = [q["id"] for q in queries if not q["evidence"]]
    check("every query names its evidence", not unevidenced,
          f"{len(unevidenced)} queries with no evidence ids",
          "Evidence is a quarter of the score. A query that cannot say which "
          "artifacts justify its answer lets a system that guessed correctly "
          "score the same as one that actually found the source.")

    levels = {q["level"] for q in queries}
    check("all six levels are represented", levels >= {1, 2, 3, 4, 5, 6},
          f"levels present: {sorted(levels)}",
          "A suite missing multi-hop or workspace queries reports an overall "
          "score for capabilities it never tested.")

    resolvable = (artifact_ids | {m["id"] for m in memories}
                  | {n["id"] for n in notes} | {t["id"] for t in tasks}
                  | {i["id"] for i in issues} | {p["id"] for p in prs}
                  | {t["id"] for t in todos} | {e["id"] for e in cal_events}
                  | {s.id for s in cal_series} | {p["id"] for p in photos}
                  | {p.id for p in world.projects} | {p.id for p in world.people}
                  | {r.id for r in world.repos}
                  | {c["id"] for c in (conflicts["claims"] if conflicts else ())}
                  # Named sources that are not rows: the profile, the timeline
                  # and the graph file itself.
                  | {"profile.json", "graph.jsonl"}
                  | {f"timeline:{e['kind']}" for e in world.events})
    unknown = sorted({e for q in queries for e in q["evidence"]
                      if e not in resolvable})
    check("evidence ids resolve to real artifacts", not unknown,
          f"{len(unknown)} evidence ids point at nothing"
          + (f" (first: {unknown[0]})" if unknown else ""),
          "A scorer marking evidence against ids that do not exist penalises "
          "every system equally and measures nothing.")

    return findings


def summarise(findings: list[dict]) -> dict:
    failed = [f for f in findings if not f["ok"]]
    return {"rules": len(findings), "passed": len(findings) - len(failed),
            "failed": len(failed),
            "failures": [{"rule": f["rule"], "detail": f["detail"]} for f in failed]}
