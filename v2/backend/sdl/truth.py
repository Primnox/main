"""Queries, and the answers that are known to be correct.

This is the file that makes the dataset a benchmark. Without it a synthetic life
is a pile of plausible documents and "did retrieval work" is a matter of
opinion; with it, every query has an answer DERIVED from the generator, so a
different result on the next build is a regression rather than a different mood.

Every answer is computed from the world, never written by hand. A hand-written
expectation drifts from the data the moment the generator changes, and then the
benchmark starts failing for reasons that have nothing to do with Primnox.

SIX LEVELS, and the reason they are separate. A single aggregate score hides the
thing you most want to know: a system can be excellent at recall and useless at
traversal, and one number averages that into "fine". Each level isolates one
capability, so a regression names the subsystem that caused it.

    L1  recall        one fact, one source
    L2  cross-source  one subject, several artifact types
    L3  multi-hop     two or more relationships, in order
    L4  temporal      what was true when, and what changed
    L5  workspace     where work stopped, so it can be resumed
    L6  asset         find the file, among near-misses

EVIDENCE IS PART OF THE ANSWER. Each query carries the artifact ids that justify
its answer, because a system that returns "Espresso" while citing a document
about laptops is not right — it guessed, and next month it will guess wrong. The
scorer weights evidence separately for exactly that reason.
"""
from __future__ import annotations

from . import memory as memory_gen
from .world import World

L1, L2, L3, L4, L5, L6 = 1, 2, 3, 4, 5, 6

# What a query needs in order to be answered. Reported so a failure implicates a
# subsystem rather than merely being wrong.
MEMORY, GRAPH, HYBRID, TEMPORAL, MULTIHOP, WORKSPACE, ASSET = (
    "memory", "graph", "hybrid", "temporal", "multi_hop", "workspace", "asset")

# How the query budget is divided. Recall dominates because it is what users do
# most; multi-hop is scarcer because each one is expensive to answer and a
# handful already tells you whether traversal works at all.
MIX = {L1: 0.25, L2: 0.20, L3: 0.15, L4: 0.20, L5: 0.10, L6: 0.10}


def _take(rows: list, n: int) -> list:
    """A spread sample, not a prefix.

    Taking the first n would draw every query from the first months of the
    life, and a benchmark that only ever asks about January cannot detect a
    system that has quietly stopped indexing after month six.
    """
    if n >= len(rows) or n <= 0:
        return rows if n > 0 else []
    step = len(rows) / n
    return [rows[int(i * step)] for i in range(n)]


class _Bank:
    """Candidate queries, bucketed by level."""

    def __init__(self, months: int):
        self.by_level: dict[int, list[dict]] = {lv: [] for lv in MIX}
        self.months = months

    def add(self, level: int, kind: str, question: str, answer, *,
            evidence: list[str], why: str, subsystem: str,
            as_of_month: int | None = None, path: list[str] | None = None) -> None:
        # A question with no answer cannot score anything. On a small pack some
        # queries have no subject — there may be no "delaying Sprint" email in
        # forty — and emitting them with an empty expectation would make every
        # run report a failure that is really an absent premise.
        if answer in (None, [], {}, ""):
            return
        self.by_level[level].append({
            "kind": kind, "level": level, "question": question, "answer": answer,
            "evidence": sorted(set(e for e in evidence if e)),
            "as_of_month": self.months - 1 if as_of_month is None else as_of_month,
            "graph_path": path or [],
            "rationale": why, "subsystem": subsystem,
        })

    def balance(self, budget: int) -> list[dict]:
        """Cut each level to its share, then renumber.

        Levels that cannot fill their share hand the remainder back, so a small
        pack stays balanced instead of silently becoming a recall-only suite.
        """
        targets = {lv: int(budget * share) for lv, share in MIX.items()}
        shortfall = 0
        for lv in sorted(MIX):
            have = len(self.by_level[lv])
            if have < targets[lv]:
                shortfall += targets[lv] - have
                targets[lv] = have
        for lv in sorted(MIX, key=lambda k: -len(self.by_level[k])):
            if shortfall <= 0:
                break
            spare = len(self.by_level[lv]) - targets[lv]
            claim = min(spare, shortfall)
            targets[lv] += claim
            shortfall -= claim

        out: list[dict] = []
        for lv in sorted(MIX):
            out.extend(_take(self.by_level[lv], targets[lv]))
        for i, query in enumerate(out):
            query["id"] = f"q:{i:04d}"
        return out


def build(world: World, *, memories, chats, emails, meetings, documents,
          symbols, graph, notes=(), tasks=(), calendar=None, commits=(),
          issues=(), prs=(), todos=(), photos=(), conflicts=None,
          budget: int = 500) -> list[dict]:
    bank = _Bank(world.months)
    now = world.months - 1
    notes, tasks = list(notes), list(tasks)
    commits, issues, prs, todos = list(commits), list(issues), list(prs), list(todos)
    photos = list(photos)
    cal_events = list(calendar["events"]) if calendar else []
    cal_series = list(calendar["series"]) if calendar else []
    resolutions = list(conflicts["resolutions"]) if conflicts else []
    conflict_claims = list(conflicts["claims"]) if conflicts else []

    _level1(bank, world, memories, commits, now)
    _level2(bank, world, chats, emails, meetings, documents, notes, commits, now)
    _level3(bank, world, meetings, emails, documents, notes, symbols, commits,
            issues, prs, graph)
    _level4(bank, world, memories, cal_series, cal_events, tasks, issues,
            resolutions, conflict_claims, documents, now)
    _level5(bank, world, commits, tasks, todos, prs, notes, now)
    _level6(bank, world, documents, notes, photos, emails, now)

    return bank.balance(budget)


# ── L1: one fact, one source ─────────────────────────────────────────────────
def _level1(bank, world: World, memories, commits, now: int) -> None:
    by_feature_commit = {c["introduces"]: c for c in commits if c["introduces"]}

    current = memory_gen.current_preferences(memories)
    for topic, entry in sorted(current.items()):
        bank.add(L1, "preference",
                 f"What is the user's current preference regarding {topic}?",
                 {"text": entry["text"], "memory_id": entry["id"]},
                 evidence=[entry["id"]],
                 why="Head of the supersession chain for this topic.",
                 subsystem="Memory Service")

    device = max((d for d in world.subject["devices"] if d["kind"] == "laptop"),
                 key=lambda d: d.get("from_month", 0))
    bank.add(L1, "profile", "Which laptop does the user currently use?",
             device["name"], evidence=["profile.json"],
             why="The laptop with the latest from_month and no to_month.",
             subsystem="Memory Service")

    for field, question in (("city", "Which city does the user live in?"),
                            ("role", "What is the user's job title?"),
                            ("org", "Which company does the user work for?")):
        bank.add(L1, "profile", question, world.subject[field],
                 evidence=["profile.json"], why=f"subject.{field}",
                 subsystem="Memory Service")

    for relation in world.subject["family"]:
        bank.add(L1, "profile",
                 f"What is the name of the user's {relation['relation']}?",
                 relation["name"], evidence=["profile.json"],
                 why="Stated in the subject profile.", subsystem="Memory Service")

    for feature in world.features:
        commit = by_feature_commit.get(feature["name"])
        bank.add(L1, "feature_origin",
                 f"Which repository first introduced {feature['name']}?",
                 feature["first_repo"],
                 evidence=[commit["sha"]] if commit else [],
                 as_of_month=feature["first_month"],
                 why=("The earliest introducing commit. Later repositories "
                      "adopted it and are not the answer."),
                 subsystem="Knowledge Service")

    for event in world.events:
        bank.add(L1, "life_event",
                 f"In which month did this happen: {event['what']}?",
                 {"month": event["month"], "label": world.month_label(event["month"])},
                 evidence=[f"timeline:{event['kind']}"],
                 as_of_month=event["month"],
                 why="Recorded in the life timeline.", subsystem="Memory Service")

    for project in world.projects[:40]:
        bank.add(L1, "ownership", f"Who currently owns the project {project.name}?",
                 project.owner_at(now), evidence=[project.id],
                 why="Latest entry in the project's owner history.",
                 subsystem="Knowledge Service")

    for person in world.people[:60]:
        bank.add(L1, "person_role", f"What is {person.name}'s role?",
                 person.role, evidence=[person.id],
                 why="Stated in the directory.", subsystem="Knowledge Service")


# ── L2: one subject, several artifact types ──────────────────────────────────
def _level2(bank, world: World, chats, emails, meetings, documents, notes,
            commits, now: int) -> None:
    """"Who is X" is the archetype: no single artifact answers it."""
    chats_by = {}
    for c in chats:
        if not c.get("deleted"):
            chats_by.setdefault(c["author"], []).append(c["id"])
    mail_by = {}
    for e in emails:
        mail_by.setdefault(e["from"], []).append(e["id"])
    met_by = {}
    for m in meetings:
        for a in m["attendees"]:
            met_by.setdefault(a, []).append(m["id"])
    commits_by = {}
    for c in commits:
        commits_by.setdefault(c["author"], []).append(c["sha"])

    for person in world.people:
        seen = (chats_by.get(person.id, []) + mail_by.get(person.id, [])
                + met_by.get(person.id, []))
        # Someone who appears in only one place does not test combining.
        kinds = sum(1 for bucket in (chats_by, mail_by, met_by, commits_by)
                    if bucket.get(person.id))
        if kinds < 2:
            continue
        bank.add(L2, "who_is", f"Who is {person.name}?",
                 {"role": person.role, "org": person.org,
                  "joined_month": person.joined_month,
                  "left_month": person.left_month,
                  "meetings": len(met_by.get(person.id, [])),
                  "emails_sent": len(mail_by.get(person.id, [])),
                  "messages": len(chats_by.get(person.id, [])),
                  "commits": len(commits_by.get(person.id, []))},
                 evidence=([person.id] + seen[:6]),
                 why=("Directory role plus participation counted across chats, "
                      "emails and meetings."),
                 subsystem="Context Service")

    docs_by_project = {}
    for d in documents:
        docs_by_project.setdefault(d["project"], []).append(d["id"])
    notes_by_project = {}
    for n in notes:
        notes_by_project.setdefault(n["project"], []).append(n["id"])

    for project in world.projects:
        docs = docs_by_project.get(project.id, [])
        note_ids = notes_by_project.get(project.id, [])
        if not docs or not note_ids:
            continue
        bank.add(L2, "about_project", f"What do we know about {project.name}?",
                 {"owner": project.owner_at(now), "repo": project.repo,
                  "started_month": project.started_month,
                  "documents": len(docs), "notes": len(note_ids),
                  "previously_called": project.renamed_from},
                 evidence=[project.id] + docs[:4] + note_ids[:2],
                 why="Project record joined to its documents and notes.",
                 subsystem="Context Service")

    for repo in world.repos:
        mine = [c for c in commits if c["repo"] == repo.name]
        if not mine:
            continue
        introduced = sorted({c["introduces"] for c in mine if c["introduces"]})
        bank.add(L2, "about_repo", f"Summarise the repository {repo.name}.",
                 {"language": repo.language, "project": repo.project_id,
                  "commits": len(mine),
                  "contributors": len({c["author"] for c in mine}),
                  "features_introduced": introduced},
                 evidence=[repo.id] + [c["sha"] for c in mine[:4]],
                 why="Repository record joined to its commit history.",
                 subsystem="Context Service")


# ── L3: two or more relationships, in order ──────────────────────────────────
def _level3(bank, world: World, meetings, emails, documents, notes, symbols,
            commits, issues, prs, graph) -> None:
    committers_by_repo: dict[str, set[str]] = {}
    for s in symbols:
        committers_by_repo.setdefault(s["repo"], set()).add(s["committer"])
    for c in commits:
        committers_by_repo.setdefault(c["repo"], set()).add(c["author"])
    repo_of_project = {p.id: p.repo for p in world.projects if p.repo}

    multi = set()
    for m in meetings:
        if "person:000" not in m["attendees"]:
            continue
        repo = repo_of_project.get(m["project"])
        for person in m["attendees"] if repo else ():
            if person != "person:000" and person in committers_by_repo.get(repo, ()):
                multi.add(person)
    bank.add(L3, "cto_committers",
             "Which people attended a meeting with the CTO and later committed "
             "code to the repository that meeting was about?",
             sorted(multi),
             evidence=[m["id"] for m in meetings if "person:000" in m["attendees"]][:6],
             path=["attended", "references", "depends_on", "committed_to"],
             why="Intersection of CTO co-attendees and committers to the meeting's repo.",
             subsystem="Knowledge Service")

    # The note chains: note → email → document → commit, walked end to end.
    for note in notes:
        if len(note["references"]) < 3:
            continue
        bank.add(L3, "reference_chain",
                 f"Starting from the note “{note['title']}” ({note['id']}), "
                 f"what does it reference, and in what order?",
                 note["references"], evidence=[note["id"]] + note["references"],
                 as_of_month=note["month"],
                 path=["references"] * len(note["references"]),
                 why="The note's explicit reference list, in write order.",
                 subsystem="Knowledge Service")

    prs_by_issue: dict[str, list[str]] = {}
    for pr in prs:
        for issue_id in pr["closes"]:
            prs_by_issue.setdefault(issue_id, []).append(pr["id"])
    for issue in issues:
        closers = prs_by_issue.get(issue["id"])
        if not closers:
            continue
        bank.add(L3, "issue_closed_by",
                 f"Which pull request closed issue #{issue['number']} in "
                 f"{issue['repo']}?",
                 sorted(closers), evidence=[issue["id"]] + closers,
                 as_of_month=issue["closed_month"] or issue["month"],
                 path=["filed_in", "closes"],
                 why="Pull requests naming this issue in `closes`.",
                 subsystem="Knowledge Service")

    by_sha = {c["sha"]: c for c in commits}
    for pr in prs:
        if not pr["introduces"]:
            continue
        commit = next((by_sha[s] for s in pr["commits"] if s in by_sha
                       and by_sha[s]["introduces"]), None)
        if not commit:
            continue
        bank.add(L3, "feature_reviewers",
                 f"Who reviewed the pull request that introduced "
                 f"{pr['introduces']}?",
                 sorted(pr["reviewers"]),
                 evidence=[pr["id"], commit["sha"]], as_of_month=pr["month"],
                 path=["introduces", "carried_by", "reviewed_by"],
                 why="Reviewers of the PR carrying the introducing commit.",
                 subsystem="Knowledge Service")

    docs_by_project: dict[str, list[dict]] = {}
    for d in documents:
        docs_by_project.setdefault(d["project"], []).append(d)
    for email in emails:
        if "delaying Sprint" not in email["subject"]:
            continue
        decks = sorted(d["id"] for d in docs_by_project.get(email["mentions_project"], [])
                       if d["kind"] == "deck" and d["month"] >= email["month"])
        bank.add(L3, "email_to_deck",
                 f"Find the presentations that reference the project from the "
                 f"email “{email['subject']}” and were written after it.",
                 decks, evidence=[email["id"]] + decks,
                 as_of_month=email["month"],
                 path=["references", "references"],
                 why="Decks on the same project, dated at or after the email.",
                 subsystem="Context Service")

    inferred = [e for e in graph["edges"] if e["confidence"] == "INFERRED"]
    bank.add(L3, "provenance",
             "How many relationships are inferred rather than stated, and can "
             "each name its evidence?",
             {"inferred": len(inferred),
              "without_evidence": len([e for e in inferred
                                       if not e.get("inferred_from")])},
             evidence=["graph.jsonl"],
             why="Inferred edges must all carry inferred_from.",
             subsystem="Knowledge Service")


# ── L4: what was true when, and what changed ─────────────────────────────────
def _level4(bank, world: World, memories, cal_series, cal_events, tasks, issues,
            resolutions, conflict_claims, documents, now: int) -> None:
    for event in world.events:
        month = event["month"]
        stopped = sorted(s.title for s in cal_series if s.ended_by == event["kind"])
        started = sorted(s.title for s in cal_series if s.started_by == event["kind"])
        if stopped:
            bank.add(L4, "series_stopped",
                     f"Which recurring meetings stopped when this happened: "
                     f"{event['what']}?",
                     stopped, as_of_month=month,
                     evidence=[s.id for s in cal_series if s.ended_by == event["kind"]],
                     why=("Series whose end is attributed to this event. Series "
                          "that merely lapsed end in other months."),
                     subsystem="Knowledge Service")
        if started:
            bank.add(L4, "series_started",
                     f"Which recurring meetings began when this happened: "
                     f"{event['what']}?",
                     started, as_of_month=month,
                     evidence=[s.id for s in cal_series if s.started_by == event["kind"]],
                     why="Series whose start is attributed to this event.",
                     subsystem="Knowledge Service")

        before = {d["id"] for d in documents if d["month"] == month - 1}
        after = {d["id"] for d in documents if d["month"] == month + 1}
        if before and after:
            bank.add(L4, "around_event",
                     f"What was written in the month after this, that was not "
                     f"being written before: {event['what']}?",
                     {"month_before": month - 1, "month_after": month + 1,
                      "documents_before": len(before), "documents_after": len(after)},
                     as_of_month=month, evidence=sorted(after)[:5],
                     why="Document volume either side of the event month.",
                     subsystem="Context Service")

    # Cancellations and reschedulings. The occurrence is still in the calendar
    # either way, so both questions separate a system that reads the series from
    # one that reads what actually happened — and "did it happen" is what the
    # user is asking when they ask about a meeting they missed.
    by_series: dict[str, list[dict]] = {}
    for event in cal_events:
        if event["series"]:
            by_series.setdefault(event["series"], []).append(event)
    for series in cal_series:
        occurrences = by_series.get(series.id, [])
        cancelled = sorted(e["id"] for e in occurrences
                           if e["status"] == "cancelled")
        moved = sorted(({"id": e["id"], "from": e["date"], "to": e["moved_to"]}
                        for e in occurrences if e["status"] == "moved"),
                       key=lambda e: e["id"])
        if cancelled:
            bank.add(L4, "cancelled_occurrences",
                     f"Which occurrences of “{series.title}” were cancelled?",
                     cancelled, evidence=cancelled[:8],
                     why="Occurrences of this series with status `cancelled`.",
                     subsystem="Knowledge Service")
        if moved:
            bank.add(L4, "moved_occurrences",
                     f"Which “{series.title}” meetings were rescheduled, and to "
                     f"when?", moved,
                     evidence=[m["id"] for m in moved][:8],
                     why=("Occurrences carrying `moved_to`. The original slot "
                          "is kept, so a system reporting only the new date has "
                          "lost the fact that it moved."),
                     subsystem="Knowledge Service")

    reorg = world.event_month("reorg")
    if reorg is not None:
        changed = [{"project": p.name, "before": p.owner_at(reorg - 1),
                    "after": p.owner_at(reorg)}
                   for p in world.projects
                   if p.owner_at(reorg - 1) != p.owner_at(reorg)]
        bank.add(L4, "ownership_change",
                 "Which projects changed owners after the company reorganisation?",
                 sorted(changed, key=lambda c: c["project"]), as_of_month=reorg,
                 evidence=[p.id for p in world.projects
                           if p.owner_at(reorg - 1) != p.owner_at(reorg)][:8],
                 why=f"Projects whose owner differs between month {reorg - 1} and {reorg}.",
                 subsystem="Knowledge Service")

    renamed = [{"now": p.name, "previously": p.renamed_from}
               for p in world.projects if p.renamed_from]
    bank.add(L4, "renames",
             "Which projects were renamed, and what were they called before?",
             renamed, evidence=[p.id for p in world.projects if p.renamed_from],
             why="Projects carrying a renamed_from alias.",
             subsystem="Knowledge Service")

    # What was true THEN, not now. The superseded statement must still be
    # findable, and must not be returned as current.
    by_topic: dict[str, list[dict]] = {}
    for m in memories:
        if m.get("topic"):
            by_topic.setdefault(m["topic"], []).append(m)
    for topic, entries in sorted(by_topic.items()):
        chain = sorted(entries, key=lambda e: e["month"])
        if len(chain) < 2:
            continue
        for older, newer in zip(chain, chain[1:]):
            probe = (older["month"] + newer["month"]) // 2
            if probe <= older["month"]:
                continue
            bank.add(L4, "as_of",
                     f"In month {probe}, what was the user's preference "
                     f"regarding {topic}?",
                     {"text": older["text"], "memory_id": older["id"]},
                     as_of_month=probe, evidence=[older["id"]],
                     why=(f"{older['id']} held from month {older['month']} until "
                          f"{newer['id']} superseded it in month {newer['month']}."),
                     subsystem="Memory Service")

    promoted = memory_gen.promoted_ids(memories)
    if promoted and len(promoted) < len(memories):
        bank.add(L4, "retention",
                 "Of everything observed, which facts are worth keeping "
                 "long-term rather than discarding as routine?",
                 {"keep": len(promoted), "discard": len(memories) - len(promoted),
                  "keep_ids": sorted(promoted)[:25]},
                 evidence=sorted(promoted)[:8],
                 why=("Preferences, life events, project facts and colleagues "
                      "are salient; routine encounters are not. A store that "
                      "keeps everything scores the same as one that keeps "
                      "nothing unless this is measured separately."),
                 subsystem="Memory Service")

    superseded = memory_gen.superseded_ids(memories)
    bank.add(L4, "changed_preferences",
             "Which preferences has the user changed at least once?",
             sorted({m["topic"] for m in memories
                     if m["id"] in superseded and m.get("topic")}),
             evidence=sorted(superseded)[:8],
             why="Topics with at least one superseded memory.",
             subsystem="Memory Service")

    # The contradictions.
    claims_by_dispute: dict[str, list[str]] = {}
    for claim in conflict_claims:
        claims_by_dispute.setdefault(claim["dispute"], []).append(claim["id"])
    for resolution in resolutions:
        bank.add(L4, "contradiction", resolution["question"],
                 {"answer": resolution["answer"],
                  "source": resolution["winning_source"],
                  "superseded": resolution["superseded"]},
                 as_of_month=resolution["decided_at_month"],
                 evidence=claims_by_dispute.get(resolution["dispute"], []),
                 why=(f"Resolved by {resolution['decided_by']} "
                      f"({resolution['tests']} rule): authority first, then "
                      f"recency inside the winning tier."),
                 subsystem="Knowledge Service")

    for probe in range(1, world.months, max(1, world.months // 8)):
        open_tasks = [t["id"] for t in tasks
                      if t["month"] <= probe
                      and (t["completed_month"] is None or t["completed_month"] > probe)]
        bank.add(L4, "open_at", f"Which tasks were still open at the end of "
                 f"month {probe} ({world.month_label(probe)})?",
                 {"count": len(open_tasks), "ids": sorted(open_tasks)[:20]},
                 as_of_month=probe, evidence=sorted(open_tasks)[:6],
                 why="Tasks created on or before the month and not yet completed.",
                 subsystem="Context Service")

        gone = sorted(p.id for p in world.people
                      if p.left_month is not None and p.left_month <= probe)
        bank.add(L4, "departed_by",
                 f"Who had left the company by month {probe}?", gone,
                 as_of_month=probe, evidence=gone[:6],
                 why="People whose left_month is at or before the probe.",
                 subsystem="Knowledge Service")


# ── L5: where work stopped ───────────────────────────────────────────────────
def _level5(bank, world: World, commits, tasks, todos, prs, notes, now: int) -> None:
    """Resumption questions. "Continue where I stopped" is only answerable if
    the system can find the LAST thing that happened, which is a different
    problem from finding the most relevant thing."""
    latest_commit: dict[str, dict] = {}
    for c in commits:
        seen = latest_commit.get(c["repo"])
        if seen is None or (c["month"], c["sha"]) > (seen["month"], seen["sha"]):
            latest_commit[c["repo"]] = c
    for repo, commit in sorted(latest_commit.items()):
        bank.add(L5, "resume_repo",
                 f"What was the last change made to {repo}, and by whom?",
                 {"sha": commit["sha"], "message": commit["message"],
                  "author": commit["author"], "month": commit["month"]},
                 as_of_month=commit["month"], evidence=[commit["sha"]],
                 why="Highest month in the repository's commit history.",
                 subsystem="Workspace System")

    open_todos: dict[str, list[dict]] = {}
    for todo in todos:
        if todo["resolved_month"] is None:
            open_todos.setdefault(todo["repo"], []).append(todo)
    for repo, rows in sorted(open_todos.items()):
        oldest = min(rows, key=lambda t: (t["month"], t["id"]))
        bank.add(L5, "open_todo",
                 f"What is the oldest unresolved TODO still in {repo}?",
                 {"id": oldest["id"], "file": oldest["file"],
                  "line": oldest["line"], "text": oldest["text"],
                  "month": oldest["month"]},
                 as_of_month=oldest["month"], evidence=[oldest["id"]],
                 why="Earliest TODO in the repository with no resolved_month.",
                 subsystem="Workspace System")

    by_project: dict[str, list[dict]] = {}
    for task in tasks:
        if task["status"] in ("todo", "doing"):
            by_project.setdefault(task["project"], []).append(task)
    for project in world.projects:
        rows = by_project.get(project.id)
        if not rows:
            continue
        oldest = min(rows, key=lambda t: (t["month"], t["id"]))
        bank.add(L5, "resume_project",
                 f"Work on {project.name} was interrupted. What is the oldest "
                 f"task still outstanding?",
                 {"id": oldest["id"], "title": oldest["title"],
                  "assignee": oldest["assignee"], "month": oldest["month"],
                  "status": oldest["status"]},
                 as_of_month=oldest["month"], evidence=[oldest["id"]],
                 why="Earliest task on the project still in todo or doing.",
                 subsystem="Workspace System")

    stale = [pr for pr in prs if pr["state"] == "open"]
    by_repo: dict[str, list[dict]] = {}
    for pr in stale:
        by_repo.setdefault(pr["repo"], []).append(pr)
    for repo, rows in sorted(by_repo.items()):
        oldest = min(rows, key=lambda p: (p["month"], p["id"]))
        bank.add(L5, "stale_pr",
                 f"Which pull request in {repo} has been open the longest?",
                 {"id": oldest["id"], "number": oldest["number"],
                  "title": oldest["title"], "month": oldest["month"]},
                 as_of_month=oldest["month"], evidence=[oldest["id"]],
                 why="Earliest pull request in the repository still open.",
                 subsystem="Workspace System")


# ── L6: find the file, among near-misses ─────────────────────────────────────
def _level6(bank, world: World, documents, notes, photos, emails, now: int) -> None:
    by_project: dict[str, list[dict]] = {}
    for d in documents:
        by_project.setdefault(d["project"], []).append(d)

    for project in world.projects:
        rows = by_project.get(project.id, [])
        final = [d for d in rows if not d["draft"] and not d["duplicate_of"]]
        if not final:
            continue
        newest = max(final, key=lambda d: (d["month"], d["id"]))
        bank.add(L6, "latest_version",
                 f"Which is the most recent finished (non-draft, non-duplicate) "
                 f"document about {project.name}?",
                 {"id": newest["id"], "name": newest["name"],
                  "month": newest["month"]},
                 as_of_month=newest["month"], evidence=[newest["id"]],
                 why=("Latest document on the project that is neither a draft "
                      "nor a duplicate — the drafts and copies are the near "
                      "misses this question exists to reject."),
                 subsystem="Asset Service")

    dupes = sorted(d["id"] for d in documents if d["duplicate_of"])
    bank.add(L6, "duplicates",
             "Which documents are duplicates of an earlier file?", dupes,
             evidence=dupes[:8], why="Documents carrying duplicate_of.",
             subsystem="Asset Service")

    for kind in ("contract", "invoice", "deck", "proposal", "report"):
        rows = sorted((d for d in documents if d["kind"] == kind),
                      key=lambda d: (d["month"], d["id"]))
        if len(rows) < 2:
            continue
        midpoint = world.months // 2
        after = [d["id"] for d in rows if d["month"] >= midpoint]
        bank.add(L6, "by_kind_and_date",
                 f"Find every {kind} filed from month {midpoint} onwards.",
                 after, as_of_month=midpoint, evidence=after[:8],
                 why=f"{kind} documents dated at or after the midpoint month.",
                 subsystem="Asset Service")

    with_text: dict[str, list[str]] = {}
    for photo in photos:
        if photo["ocr_text"]:
            with_text.setdefault(photo["ocr_text"], []).append(photo["id"])
    for text, ids in sorted(with_text.items()):
        bank.add(L6, "photo_ocr",
                 f"Which photographs contain the text “{text}”?", sorted(ids),
                 evidence=sorted(ids)[:8],
                 why=("Photos whose OCR text matches. OCR is unreliable, so "
                      "these edges are AMBIGUOUS in the graph and a system that "
                      "asserts them with confidence is overclaiming."),
                 subsystem="Asset Service")

    by_folder: dict[str, list[str]] = {}
    for note in notes:
        by_folder.setdefault(note["folder"], []).append(note["id"])
    for folder, ids in sorted(by_folder.items()):
        bank.add(L6, "by_folder",
                 f"How many notes are filed under {folder}, and which is the "
                 f"earliest?",
                 {"count": len(ids), "earliest": min(ids)},
                 evidence=sorted(ids)[:5],
                 why="Notes grouped by their folder.", subsystem="Asset Service")
