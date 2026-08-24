"""Repositories, and the history written into them.

Symbols say what the code contains. History says what happened to it, and that
is where the interesting questions live: which repository introduced a
capability first, which pull request closed which issue, which TODO is still
open eighteen months later.

The feature ledger is the part that has to be exact. `world.features` decides
that OAuth entered `atlas-core-api` in month 3 and reached two other
repositories later; this module writes the commits that make that true. Filler
commit messages are drawn from a vocabulary that shares no word with any feature
name, so "which repository introduced OAuth first" has one answer and not
several near-misses — a benchmark whose answer key is ambiguous measures
patience, not retrieval.
"""
from __future__ import annotations

import hashlib
import random

from .world import FEATURES, World

# Deliberately disjoint from FEATURES. Checked by a validation rule, because the
# day someone adds "caching" here is the day the OAuth question quietly breaks.
CHORES = ["tidy imports", "bump dependencies", "fix flaky test", "rename helper",
          "drop dead branch", "correct typo in docstring", "widen a timeout",
          "split a long function", "add a missing index", "silence a warning",
          "handle an empty list", "guard a null path", "shorten a log line"]

ISSUE_TITLES = ["intermittent failure on startup", "slow query on the list view",
                "stale data after a rename", "crash when the file is missing",
                "wrong timezone in the export", "memory grows under load",
                "duplicate rows after a retry", "broken link in the sidebar"]

LABELS = ["bug", "enhancement", "chore", "documentation", "performance",
          "regression", "good first issue"]

TODO_TEXTS = ["remove once the migration lands", "this should be paginated",
              "handle the retry case properly", "extract into its own module",
              "the timeout here is a guess", "needs a test for the empty case"]


def commit_sha(*parts) -> str:
    """Public because `evolve.py` writes commits too, and a tick's shas must be
    generated the same way as the pack's or the two stop being one history."""
    return hashlib.sha1(":".join(str(p) for p in parts).encode()).hexdigest()[:12]


def commits(world: World, count: int = 18_000) -> list[dict]:
    """Every commit, with the feature-introducing ones placed exactly.

    Feature commits are written first and never displaced by the volume knob. A
    pack small enough that the fillers crowd them out would silently lose the
    answers to the code questions, and would then fail its own validation for a
    reason nobody could guess from the symptom.
    """
    r = random.Random(world.seed ^ 0xC0DE)
    by_name = {repo.name: repo for repo in world.repos}
    out: list[dict] = []

    def add(repo_name: str, month: int, message: str, **extra) -> dict:
        repo = by_name[repo_name]
        cast = [p for p in world.active_people(month)
                if p.active(month)] or world.people
        author = cast[(len(out) * 7 + month) % len(cast)]
        entry = {
            "sha": commit_sha(world.seed, repo_name, month, len(out)),
            "repo": repo_name,
            "project": repo.project_id,
            "month": month,
            "date": world.month_date(month).isoformat(),
            "author": author.id,
            "author_name": author.name,
            "message": message,
            "files": [f"src/{repo.language}/mod_{(len(out) + i) % 200:03d}"
                      for i in range(1 + len(out) % 3)],
            "introduces": None,
            "adopts": None,
            **extra,
        }
        out.append(entry)
        return entry

    # ── the feature ledger, written as commits ────────────────────────────
    for feature in world.features:
        add(feature["first_repo"], feature["first_month"],
            f"add {feature['name']} support", introduces=feature["name"])
        for adopter in feature["adopters"]:
            add(adopter["repo"], adopter["month"],
                f"port {feature['name']} across from "
                f"{feature['first_repo']}", adopts=feature["name"])

    # ── filler ────────────────────────────────────────────────────────────
    names = sorted(by_name)
    while len(out) < count:
        i = len(out)
        repo = names[i % len(names)]
        month = min(world.months - 1,
                    max(by_name[repo].created_month,
                        int(i / max(1, count) * world.months)))
        add(repo, month, f"{r.choice(CHORES)} in {repo}")

    out.sort(key=lambda c: (c["month"], c["repo"], c["sha"]))
    return out


def issues(world: World, commit_rows: list[dict], count: int = 900) -> list[dict]:
    r = random.Random(world.seed ^ 0x1550)
    names = world.repo_names()
    out: list[dict] = []
    for i in range(count):
        repo = names[i % len(names)]
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        cast = world.active_people(month) or world.people
        author = cast[(i * 5) % len(cast)]
        closed = r.random() < 0.62
        # An issue closed before it was opened is nonsense that a graph will
        # happily store and a temporal query will then trip over.
        closed_month = (min(world.months - 1, month + r.randrange(1, 5))
                        if closed and month < world.months - 1 else None)
        out.append({
            "id": f"issue:{i:05d}",
            "number": i + 1,
            "repo": repo,
            "month": month,
            "date": world.month_date(month).isoformat(),
            "author": author.id,
            "title": f"{repo}: {r.choice(ISSUE_TITLES)}",
            "labels": r.sample(LABELS, r.randrange(1, 3)),
            "state": "closed" if closed_month is not None else "open",
            "closed_month": closed_month,
        })
    return out


def pull_requests(world: World, commit_rows: list[dict], issue_rows: list[dict],
                  count: int = 2_200) -> list[dict]:
    """Pull requests that carry real commits and close real issues.

    The links are the point. "Which pull request introduced OAuth" is a
    two-step: find the commit that did it, then the PR that carried it — and
    that only works if the PR names commits that exist.
    """
    r = random.Random(world.seed ^ 0x9411)
    by_repo: dict[str, list[dict]] = {}
    for c in commit_rows:
        by_repo.setdefault(c["repo"], []).append(c)
    open_issues: dict[str, list[dict]] = {}
    for issue in issue_rows:
        if issue["state"] == "closed":
            open_issues.setdefault(issue["repo"], []).append(issue)

    names = world.repo_names()
    out: list[dict] = []
    cursor: dict[str, int] = {}
    issue_cursor: dict[str, int] = {}
    for i in range(count):
        repo = names[i % len(names)]
        pool = by_repo.get(repo, [])
        if not pool:
            continue
        start = cursor.get(repo, 0) % len(pool)
        carried = pool[start:start + r.randrange(1, 4)] or [pool[start]]
        cursor[repo] = start + len(carried)
        month = carried[0]["month"]

        closes = []
        candidates = open_issues.get(repo, [])
        if candidates and r.random() < 0.45:
            j = issue_cursor.get(repo, 0) % len(candidates)
            issue_cursor[repo] = j + 1
            # Only an issue that was open at the time. A PR closing an issue
            # filed months later is the kind of detail that looks harmless and
            # makes every "what fixed this" answer unfalsifiable.
            if candidates[j]["month"] <= month:
                closes.append(candidates[j]["id"])

        cast = world.active_people(month) or world.people
        author = cast[(i * 3) % len(cast)]
        reviewers = [p.id for p in cast[(i * 11) % len(cast):][:2]]
        merged = r.random() < 0.78
        out.append({
            "id": f"pr:{i:05d}",
            "number": i + 1,
            "repo": repo,
            "month": month,
            "date": world.month_date(month).isoformat(),
            "author": author.id,
            "title": carried[0]["message"],
            "commits": [c["sha"] for c in carried],
            "closes": closes,
            "reviewers": [x for x in reviewers if x != author.id],
            "state": "merged" if merged else r.choice(["open", "closed"]),
            "introduces": next((c["introduces"] for c in carried
                                if c["introduces"]), None),
        })
    return out


def todos(world: World, count: int = 400) -> list[dict]:
    """Comments left in the code, some of them still there two years later."""
    r = random.Random(world.seed ^ 0x70D0)
    names = world.repo_names()
    out: list[dict] = []
    for i in range(count):
        repo = names[i % len(names)]
        month = min(world.months - 1, int(i / max(1, count) * world.months))
        cast = world.active_people(month) or world.people
        resolved = (min(world.months - 1, month + r.randrange(1, 8))
                    if r.random() < 0.4 and month < world.months - 1 else None)
        out.append({
            "id": f"todo:{i:04d}",
            "repo": repo,
            "file": f"src/mod_{i % 200:03d}",
            "line": (i % 300) + 1,
            "text": f"TODO: {r.choice(TODO_TEXTS)}",
            "month": month,
            "author": cast[(i * 7) % len(cast)].id,
            "resolved_month": resolved,
        })
    return out


def first_introducer(world: World, feature: str) -> dict | None:
    return next((f for f in world.features if f["name"] == feature), None)


def feature_vocabulary_is_disjoint() -> bool:
    """No filler message may contain a feature name.

    Checked as a rule rather than trusted, because the failure is silent: a
    chore worded "add response caching to the list view" gives the OAuth-style
    questions a second defensible answer, and the benchmark starts marking
    correct systems wrong.
    """
    words = {w.lower() for f in FEATURES for w in f.split()}
    for phrase in CHORES + ISSUE_TITLES + TODO_TEXTS:
        if words & {w.lower().strip(",.") for w in phrase.split()}:
            return False
    return True
