"""The knowledge graph, with provenance on every edge.

Every relationship names the artifact it came from. That is not bookkeeping: an
edge without a source cannot be checked, cannot be explained to a user, and
cannot be removed when the artifact behind it is deleted. `INFERRED` edges carry
the evidence they were inferred FROM, which is the difference between a system
that can justify an answer and one that can only assert it.
"""
from __future__ import annotations

from .world import World

EXTRACTED, INFERRED, AMBIGUOUS = "EXTRACTED", "INFERRED", "AMBIGUOUS"

RELATIONS = ("works_with", "reports_to", "authored", "mentions", "references",
             "depends_on", "located_in", "attended", "purchased", "scheduled",
             "inferred_from", "owns", "committed_to", "renamed_from",
             "assigned_to", "derived_from", "closes", "carries", "reviewed",
             "introduced", "adopted", "claims", "recurs_as", "filed_in")


def build(world: World, *, chats, emails, meetings, documents, symbols,
          photos=(), calendar=None, tasks=(), notes=(), commits=(), issues=(),
          prs=(), todos=(), conflicts=None) -> dict:
    """Nodes and edges for the whole dataset."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(nid: str, label: str, node_type: str, **extra) -> str:
        """`node_type`, not `kind`: a document carries its own `kind`
        attribute, and the collision passed two values for one parameter."""
        if nid not in nodes:
            nodes[nid] = {"id": nid, "label": label, "type": node_type, **extra}
        return nid

    def edge(src: str, dst: str, relation: str, confidence: str,
             source: str, month: int, evidence: str | None = None) -> None:
        if src == dst:
            return
        edges.append({
            "source": src, "target": dst, "relation": relation,
            "confidence": confidence, "source_artifact": source, "month": month,
            # Only INFERRED edges carry this. An EXTRACTED edge IS its source.
            **({"inferred_from": evidence} if evidence else {}),
        })

    subject = node(world.subject["id"], world.subject["name"], "person",
                   role=world.subject["role"])
    # Only organisations somebody actually belongs to. Emitting the whole roster
    # put a node in the graph for every company in the name list, and on a small
    # pack most of them employ nobody — an unreachable node that costs indexing
    # and can never be returned, which is the exact thing the orphan rule exists
    # to catch.
    for org in sorted({p.org for p in world.people} | {world.subject["org"]}
                      | {p.org for p in world.projects}):
        node(f"org:{org}", org, "organization")
    edge(subject, f"org:{world.subject['org']}", "located_in", EXTRACTED,
         "profile.json", 0)

    for person in world.people:
        pid = node(person.id, person.name, "person", role=person.role)
        edge(pid, f"org:{person.org}", "located_in", EXTRACTED,
             "directory.csv", person.joined_month)
        if person.role in ("Engineer", "Senior Engineer", "Staff Engineer"):
            edge(pid, "person:000", "reports_to", INFERRED, "directory.csv",
                 person.joined_month, evidence="org chart, role hierarchy")

    for project in world.projects:
        proj = node(project.id, project.name, "project")
        edge(proj, f"org:{project.org}", "located_in", EXTRACTED,
             "projects.json", project.started_month)
        edge(project.owner_id, proj, "owns", EXTRACTED, "projects.json",
             project.started_month)
        for month, new_owner in project.owner_history:
            # Ownership after a handover. Both edges survive, with different
            # months — "who owned it in month 10" and "who owns it now" are
            # different questions and the graph must answer both.
            edge(new_owner, proj, "owns", EXTRACTED, "reorg-announcement.eml", month)
        if project.renamed_from:
            old = node(f"project:alias:{project.renamed_from}",
                       project.renamed_from, "project_alias")
            edge(proj, old, "renamed_from", EXTRACTED, "projects.json",
                 project.started_month)
        if project.repo:
            repo = node(f"repo:{project.repo}", project.repo, "repository")
            edge(proj, repo, "depends_on", EXTRACTED, "projects.json",
                 project.started_month)

    for m in meetings:
        mid = node(m["id"], m["title"], "meeting", date=m["date"])
        edge(mid, m["project"], "references", EXTRACTED, m["id"], m["month"])
        for attendee in m["attendees"]:
            edge(attendee, mid, "attended", EXTRACTED, m["id"], m["month"])
        # works_with is INFERRED from co-attendance, and says so. It is the
        # relationship a user asks about and the one no artifact states.
        for i, a in enumerate(m["attendees"]):
            for b in m["attendees"][i + 1:]:
                edge(a, b, "works_with", INFERRED, m["id"], m["month"],
                     evidence=f"co-attended {m['id']}")

    for e in emails:
        eid = node(e["id"], e["subject"], "email", date=e["date"])
        edge(e["from"], eid, "authored", EXTRACTED, e["id"], e["month"])
        for to in e["to"]:
            edge(eid, to, "mentions", EXTRACTED, e["id"], e["month"])
        edge(eid, e["mentions_project"], "references", EXTRACTED, e["id"], e["month"])

    for d in documents:
        # `doc_kind`, not `kind`. A node already carries `type`; a second
        # attribute called `kind` collided with the row marker graph.jsonl uses
        # to separate nodes from edges, and every document node was read back as
        # a malformed edge by anything loading the file.
        did = node(d["id"], d["name"], "document", folder=d["folder"],
                   doc_kind=d["kind"])
        edge(d["author"], did, "authored", EXTRACTED, d["id"], d["month"])
        edge(did, d["project"], "references", EXTRACTED, d["id"], d["month"])
        if d["duplicate_of"]:
            # A duplicate is genuinely ambiguous: same content, different file,
            # and nothing in the artifact says which is authoritative.
            edge(did, d["duplicate_of"], "references", AMBIGUOUS, d["id"],
                 d["month"])

    for c in chats:
        if c["deleted"]:
            continue
        cid = node(c["id"], c["text"][:60], "message", thread=c["thread"])
        edge(c["author"], cid, "authored", EXTRACTED, c["id"], c["month"])
        edge(cid, c["mentions_project"], "mentions", EXTRACTED, c["id"], c["month"])

    for s in symbols:
        sid = node(s["id"], s["symbol"], "symbol", file=s["file"], line=s["line"])
        repo = node(f"repo:{s['repo']}", s["repo"], "repository")
        edge(sid, repo, "located_in", EXTRACTED, s["file"], s["month"])
        edge(s["committer"], repo, "committed_to", EXTRACTED,
             f"git/{s['repo']}", s["month"])

    for p in photos:
        pid = node(p["id"], p["name"], "photo", folder=p["folder"])
        edge(world.subject["id"], pid, "authored", EXTRACTED, p["id"], p["month"])
        if p["ocr_text"]:
            # OCR text is evidence, and it is frequently wrong — AMBIGUOUS is
            # the honest confidence for a relationship read off a photograph.
            edge(pid, world.subject["id"], "mentions", AMBIGUOUS, p["id"],
                 p["month"])

    # ── the calendar ──────────────────────────────────────────────────────
    for series in (calendar["series"] if calendar else ()):
        node(series.id, series.title, "series", cadence=series.cadence,
             series_kind=series.kind, start_month=series.start_month,
             end_month=series.end_month, ended_by=series.ended_by,
             started_by=series.started_by)
    for event in (calendar["events"] if calendar else ()):
        eid = node(event["id"], event["title"], "calendar_event",
                   date=event["date"], status=event["status"])
        if event["series"]:
            edge(event["series"], eid, "recurs_as", EXTRACTED, event["id"],
                 event["month"])
        for attendee in event["attendees"]:
            edge(attendee, eid, "attended", EXTRACTED, event["id"], event["month"])

    # ── tasks ─────────────────────────────────────────────────────────────
    for task in tasks:
        tid = node(task["id"], task["title"], "task", status=task["status"])
        edge(tid, task["project"], "references", EXTRACTED, task["id"], task["month"])
        edge(tid, task["assignee"], "assigned_to", EXTRACTED, task["id"],
             task["month"])
        if task["source"]:
            # Where the task came from. INFERRED because no artifact states
            # "this email produced this task" — a reader concluded it, and an
            # answer built on this edge has to be able to say so.
            edge(tid, task["source"], "derived_from", INFERRED, task["id"],
                 task["month"], evidence=f"raised in {task['source']}")

    # ── notes and their reference chains ──────────────────────────────────
    for note in notes:
        nid = node(note["id"], note["title"], "note", folder=note["folder"])
        edge(note["author"], nid, "authored", EXTRACTED, note["id"], note["month"])
        edge(nid, note["project"], "references", EXTRACTED, note["id"], note["month"])
        for target in note["references"]:
            edge(nid, target, "references", EXTRACTED, note["id"], note["month"])

    # ── git history ───────────────────────────────────────────────────────
    for commit in commits:
        cid = node(commit["sha"], commit["message"][:60], "commit",
                   repo=commit["repo"], date=commit["date"])
        repo = node(f"repo:{commit['repo']}", commit["repo"], "repository")
        edge(commit["author"], cid, "authored", EXTRACTED, commit["sha"],
             commit["month"])
        edge(cid, repo, "committed_to", EXTRACTED, commit["sha"], commit["month"])
        if commit["introduces"]:
            feature = node(f"feature:{commit['introduces']}",
                           commit["introduces"], "feature")
            edge(repo, feature, "introduced", EXTRACTED, commit["sha"],
                 commit["month"])
        if commit["adopts"]:
            feature = node(f"feature:{commit['adopts']}", commit["adopts"],
                           "feature")
            edge(repo, feature, "adopted", EXTRACTED, commit["sha"],
                 commit["month"])

    for issue in issues:
        iid = node(issue["id"], issue["title"], "issue", state=issue["state"])
        edge(iid, f"repo:{issue['repo']}", "filed_in", EXTRACTED, issue["id"],
             issue["month"])
        edge(issue["author"], iid, "authored", EXTRACTED, issue["id"], issue["month"])

    known_shas = {c["sha"] for c in commits}
    for pr in prs:
        pid = node(pr["id"], pr["title"], "pull_request", state=pr["state"])
        edge(pid, f"repo:{pr['repo']}", "filed_in", EXTRACTED, pr["id"], pr["month"])
        edge(pr["author"], pid, "authored", EXTRACTED, pr["id"], pr["month"])
        for sha in pr["commits"]:
            if sha in known_shas:
                edge(pid, sha, "carries", EXTRACTED, pr["id"], pr["month"])
        for issue_id in pr["closes"]:
            edge(pid, issue_id, "closes", EXTRACTED, pr["id"], pr["month"])
        for reviewer in pr["reviewers"]:
            edge(reviewer, pid, "reviewed", EXTRACTED, pr["id"], pr["month"])

    for todo in todos:
        tid = node(todo["id"], todo["text"][:60], "todo", file=todo["file"],
                   resolved=todo["resolved_month"] is not None)
        edge(tid, f"repo:{todo['repo']}", "located_in", EXTRACTED, todo["id"],
             todo["month"])

    # ── contradictions ────────────────────────────────────────────────────
    for claim in (conflicts["claims"] if conflicts else ()):
        dispute = node(claim["dispute"], claim["topic"], "dispute")
        cid = node(claim["id"], claim["text"][:80], "claim",
                   source_kind=claim["source_kind"], value=claim["value"],
                   authority=claim["authority"])
        # AMBIGUOUS by construction: several claims contradict each other and
        # nothing inside any one of them says which is right. The edge records
        # the disagreement rather than pre-resolving it, because a graph that
        # silently drops the losing claims cannot answer "what was I told at
        # the time" — which is half of why the contradictions are here.
        edge(dispute, cid, "claims", AMBIGUOUS, claim["id"], claim["month"])

    return {"nodes": list(nodes.values()), "edges": edges}


def orphans(graph: dict) -> list[str]:
    """Nodes no edge touches. A validation rule, not a metric: the spec allows
    intentional orphans, so this reports them rather than failing."""
    touched = {e["source"] for e in graph["edges"]} | {e["target"] for e in graph["edges"]}
    return [n["id"] for n in graph["nodes"] if n["id"] not in touched]


def missing_provenance(graph: dict) -> list[dict]:
    """Edges with no source artifact, and INFERRED edges with no evidence."""
    bad = []
    for e in graph["edges"]:
        if not e.get("source_artifact"):
            bad.append(e)
        elif e["confidence"] == INFERRED and not e.get("inferred_from"):
            bad.append(e)
    return bad
