"""Communications, documents and code — everything that references the world.

Nothing here invents a name. Every sender is a Person, every project mention is
a Project, every date is inside the timeline. That constraint is what makes the
multi-hop queries answerable: "who attended a meeting with the CTO and later
committed to the same repository" is only a question if attendance and commits
come from the same cast.

Volume is a parameter. The spec asks for 5,000 chats and 400 emails; a
Memory-10 pack wants ten of everything. Both come from this file, and each is
byte-identical run to run — but the volume feeds the month spread, so the same
index in two packs is not the same artifact. Determinism is per pack, not
across packs.
"""
from __future__ import annotations

import hashlib
import random

from .world import World

GREETINGS = ["morning", "hey", "quick one", "sorry to bug you", "ok so", "heads up"]
SLANG = ["lgtm", "wfm", "ptal", "iirc", "afaict", "nit:", "+1", "ship it"]
EMOJI = ["🙂", "👍", "🔥", "😅", "🚀", "🤔", "😬", "🎉", "☕", "🧠"]


def _rng(world: World, salt: str) -> random.Random:
    # Salted per stream so adding emails does not shift the chat messages. A
    # generator where one knob changes every artifact makes diffs useless.
    digest = hashlib.sha256(f"{world.seed}:{salt}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def chats(world: World, count: int = 5000) -> list[dict]:
    """Messages across group and direct threads, timestamped and attributed."""
    r = _rng(world, "chats")
    threads = [f"thread:{i:03d}" for i in range(max(4, count // 120))]
    out: list[dict] = []

    for i in range(count):
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        cast = world.active_people(month)
        if not cast:
            continue
        author = r.choice(cast)
        project = r.choice(world.projects)
        body = r.choice([
            f"{r.choice(GREETINGS)} — is {project.name} still blocked on review?",
            f"{r.choice(SLANG)} pushed the fix for {project.name} {r.choice(EMOJI)}",
            f"can we move the {project.name} sync? clashes with the platform call",
            f"{project.name} numbers look off, checking the ETL",
            f"who owns {project.name} now? {r.choice(EMOJI)}",
            f"re: {project.name} — see the doc I sent last week",
        ])
        out.append({
            "id": f"chat:{i:05d}",
            "thread": r.choice(threads),
            "month": month,
            "date": world.month_date(month).isoformat(),
            "author": author.id,
            "author_name": author.name,
            "text": body,
            "mentions_project": project.id,
            # Real threads have edits and deletions; a corpus without them
            # never exercises "the message that is no longer there".
            "edited": r.random() < 0.04,
            "deleted": r.random() < 0.02,
        })
    return out


def emails(world: World, count: int = 400) -> list[dict]:
    r = _rng(world, "emails")
    out: list[dict] = []
    for i in range(count):
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        cast = world.active_people(month)
        if len(cast) < 2:
            continue
        sender = r.choice(cast)
        recipients = r.sample(cast, min(len(cast), r.randrange(1, 4)))
        project = r.choice(world.projects)
        forwarded = r.random() < 0.15
        out.append({
            "id": f"email:{i:04d}",
            "month": month,
            "date": world.month_date(month).isoformat(),
            "from": sender.id,
            "from_name": sender.name,
            "to": [p.id for p in recipients],
            "subject": (("Fwd: " if forwarded else "")
                        + r.choice([f"{project.name} status",
                                    f"proposal — {project.name}",
                                    f"delaying Sprint {r.randrange(1, 30)}",
                                    f"{project.name} handover"])),
            "body": (f"Sharing the latest on {project.name}. "
                     f"{'> quoted reply follows' if forwarded else ''}"),
            "mentions_project": project.id,
            "forwarded": forwarded,
        })
    return out


def meetings(world: World, count: int = 120) -> list[dict]:
    """Transcripts with an attendee list — the edge that makes multi-hop work."""
    r = _rng(world, "meetings")
    out: list[dict] = []
    for i in range(count):
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        cast = world.active_people(month)
        if len(cast) < 3:
            continue
        attendees = r.sample(cast, min(len(cast), r.randrange(3, 8)))
        # The CTO attends a fixed share, so "met with the CTO" has a knowable
        # answer rather than a random one.
        if r.random() < 0.25:
            cto = world.person("person:000")
            if cto and cto not in attendees:
                attendees.append(cto)
        project = r.choice(world.projects)
        out.append({
            "id": f"meeting:{i:03d}",
            "month": month,
            "date": world.month_date(month).isoformat(),
            "title": f"{project.name} {r.choice(['sync', 'review', 'planning', 'retro'])}",
            "attendees": [p.id for p in attendees],
            "project": project.id,
            "cancelled": r.random() < 0.08,
            "transcript": (f"{attendees[0].name}: opening notes on {project.name}. "
                           f"{attendees[1].name}: raised the migration risk."),
        })
    return out


def documents(world: World, count: int = 600) -> list[dict]:
    """Files across realistic folders, some referencing earlier conversations."""
    r = _rng(world, "docs")
    folders = ["Documents/Work", "Documents/Projects", "Documents/Receipts",
               "Documents/Travel", "Desktop", "Downloads", "Archive"]
    kinds = ["report", "proposal", "notes", "contract", "invoice", "journal",
             "recipe", "travel-plan", "resume", "deck"]
    out: list[dict] = []
    for i in range(count):
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        project = r.choice(world.projects)
        author = r.choice(world.active_people(month) or world.people)
        kind = r.choice(kinds)
        ext = {"deck": "pptx", "invoice": "pdf", "contract": "pdf"}.get(kind, "md")
        out.append({
            "id": f"doc:{i:04d}",
            "month": month,
            "date": world.month_date(month).isoformat(),
            "folder": r.choice(folders),
            "name": f"{project.name.lower().replace(' ', '-')}-{kind}-{i:04d}.{ext}",
            "kind": kind,
            "author": author.id,
            "project": project.id,
            "slides": r.randrange(20, 180) if kind == "deck" else None,
            # Duplicates, drafts and renames — the noise the spec asks for, and
            # the reason "find the LATEST version" is a real query.
            "duplicate_of": f"doc:{i - 1:04d}" if r.random() < 0.05 and i else None,
            "draft": r.random() < 0.12,
        })
    return out


def tasks(world: World, count: int = 2_000, *, chats=(), emails=(),
          meetings=()) -> list[dict]:
    """Work items, most of them traceable to the conversation that created them.

    The `source` field is what makes a task worth generating. A to-do list on
    its own is a list of strings; a task that points at the email it came out of
    turns "what did I agree to in that thread" into a graph traversal with one
    correct answer.
    """
    r = _rng(world, "tasks")
    verbs = ["Write up", "Review", "Chase", "Migrate", "Document", "Estimate",
             "Unblock", "Deprecate", "Benchmark", "Roll back"]
    origins = [a["id"] for a in list(emails) + list(meetings)] or [None]
    from_chats = [c["id"] for c in chats if not c.get("deleted")] or [None]

    out: list[dict] = []
    for i in range(count):
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        cast = world.active_people(month) or world.people
        project = world.projects[i % len(world.projects)]
        assignee = cast[(i * 5) % len(cast)]
        # Completion has to happen at or after creation. A task closed before it
        # was opened is the sort of thing a graph stores without complaint and a
        # temporal query then answers nonsensically.
        done = r.random() < 0.58
        completed = (min(world.months - 1, month + r.randrange(0, 4))
                     if done else None)
        source = (r.choice(origins) if r.random() < 0.45
                  else r.choice(from_chats) if r.random() < 0.5 else None)
        out.append({
            "id": f"task:{i:05d}",
            "month": month,
            "date": world.month_date(month).isoformat(),
            "title": f"{r.choice(verbs)} the {project.name} "
                     f"{r.choice(['spec', 'rollout', 'migration', 'dashboard'])}",
            "project": project.id,
            "assignee": assignee.id,
            "status": ("done" if completed is not None
                       else r.choice(["todo", "todo", "doing", "dropped"])),
            "completed_month": completed,
            "priority": r.choice(["low", "normal", "normal", "high"]),
            "source": source,
        })
    return out


def notes(world: World, count: int = 1_500, *, meetings=(), emails=(),
          documents=(), commits=()) -> list[dict]:
    """Written notes, a third of which chain across artifact types.

    The chain — meeting note references an email, which references a document,
    which references a commit — is the multi-hop path the specification asks
    for. It is built explicitly rather than hoped for, because references that
    emerge by coincidence are references no query can be written against.
    """
    r = _rng(world, "notes")
    meetings, emails = list(meetings), list(emails)
    documents, commits = list(documents), list(commits)
    folders = ["Notes/Daily", "Notes/Meetings", "Notes/Ideas", "Notes/Reading",
               "Notes/Personal"]
    out: list[dict] = []

    for i in range(count):
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        project = world.projects[(i * 3) % len(world.projects)]
        cast = world.active_people(month) or world.people
        references: list[str] = []

        # Every third note is a link in a chain, anchored on a meeting from the
        # same month or earlier so the references never point into the future.
        if i % 3 == 0:
            def pick(rows, key="id"):
                eligible = [x for x in rows if x["month"] <= month]
                return eligible[(i * 7) % len(eligible)][key] if eligible else None

            for row in (meetings, emails, documents):
                found = pick(row)
                if found:
                    references.append(found)
            if commits:
                eligible = [c for c in commits if c["month"] <= month]
                if eligible:
                    references.append(eligible[(i * 11) % len(eligible)]["sha"])

        out.append({
            "id": f"note:{i:05d}",
            "month": month,
            "date": world.month_date(month).isoformat(),
            "folder": r.choice(folders),
            "title": f"{project.name} — {r.choice(['notes', 'thinking', 'recap', 'questions'])}",
            "body": (f"Notes on {project.name}. "
                     + ("Follows on from " + ", ".join(references) + "."
                        if references else "No follow-ups.")),
            "tags": r.sample(["work", "idea", "todo", "reading", "personal",
                              "decision"], r.randrange(1, 3)),
            "project": project.id,
            "author": cast[(i * 13) % len(cast)].id,
            "references": references,
        })
    return out


def code_symbols(world: World, count: int = 25_000) -> list[dict]:
    """Symbols across the repositories, with committers drawn from the cast."""
    r = _rng(world, "code")
    repos = world.repo_names() or ["atlas-api"]
    out: list[dict] = []
    for i in range(count):
        repo = repos[i % len(repos)]
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        author = r.choice(world.active_people(month) or world.people)
        out.append({
            "id": f"sym:{i:06d}",
            "repo": repo,
            "file": f"src/mod_{i % 400:03d}.py",
            "symbol": f"{r.choice(['handle', 'build', 'parse', 'sync', 'emit'])}_{i:05d}",
            "line": (i % 400) + 1,
            "committer": author.id,
            "month": month,
        })
    return out


def photos(world: World, count: int = 2000) -> list[dict]:
    """EXIF-shaped metadata only. The bytes would be noise; the metadata is what
    a retrieval system actually indexes."""
    r = _rng(world, "photos")
    out: list[dict] = []
    for i in range(count):
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        out.append({
            "id": f"photo:{i:05d}",
            "month": month,
            "date": world.month_date(month).isoformat(),
            "folder": r.choice(["Photos/Camera", "Photos/Screenshots",
                                "Photos/Whiteboards", "Photos/Receipts"]),
            "name": f"IMG_{i:05d}.jpg",
            "exif": {
                "camera": r.choice(["Pixel 8", "Framework webcam", "scanner"]),
                "iso": r.choice([100, 200, 400, 800]),
                "gps": [round(59.9 + r.random(), 4), round(10.7 + r.random(), 4)],
            },
            "ocr_text": r.choice(["", "TOTAL 42.50", "sprint 14 plan",
                                  "architecture — do not erase"]),
        })
    return out
