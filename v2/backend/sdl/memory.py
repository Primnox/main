"""Memories over 24 months, including the ones that contradict each other.

The contradictions are the point. A store where every fact agrees with every
other fact tests insertion. A store where "prefers dark mode" in month 2 is
followed by "switched to light mode" in month 15 tests whether the system knows
which is true NOW — and that is the question a user actually asks.

Each memory carries timestamp, confidence, source and category, so a retrieval
answer can be checked against what was true at that date rather than against
whatever the store happens to return.
"""
from __future__ import annotations

import random

from .world import PREFERENCE_ARCS, World

# How sure the system should be. `stated` is the user saying it outright;
# `observed` is inferred from behaviour and is the one that should lose a tie.
STATED, OBSERVED, REPORTED = "stated", "observed", "reported"

CATEGORIES = ("personal", "work", "project", "session")


def generate(world: World, volume: int = 0, promote: int = 0) -> list[dict]:
    """Every memory, in chronological order, with supersession recorded.

    `promote` splits the corpus into what a system is OFFERED and what it should
    KEEP. Without that split a store which retains everything scores exactly the
    same as one which retains the right things, and the hardest part of a memory
    system — deciding what is worth remembering — goes unmeasured.

    Salience is decided here rather than sampled: preferences, life events,
    project facts and colleagues are worth keeping; "met someone at the cafe in
    week 3" is not. When the promotion budget is smaller than the salient set,
    the most recent salient facts win, because a two-year-old preference that has
    since been superseded is the first thing that should fall out.
    """
    r = random.Random(world.seed ^ 0xA11CE)
    out: list[dict] = []

    def add(month: int, text: str, category: str, confidence: str,
            source: str, supersedes: str | None = None, topic: str = "",
            salient: bool = True) -> dict:
        entry = {
            "id": f"mem:{len(out):05d}",
            "timestamp": world.month_date(month).isoformat(),
            "month": month,
            "text": text,
            "category": category,
            "confidence": confidence,
            "source": source,
            "topic": topic,
            "supersedes": supersedes,
            "salient": salient,
            "promoted": False,
        }
        out.append(entry)
        return entry

    # ── preference arcs: the contradictions, spread across the timeline ───
    for topic, chain in PREFERENCE_ARCS:
        previous: str | None = None
        # Spaced so no two links in one arc land in the same month; a reversal
        # inside a month is ambiguous even to a correct implementation.
        span = max(2, world.months // (len(chain) + 1))
        for index, statement in enumerate(chain):
            month = min(world.months - 1, 1 + index * span + r.randrange(0, 2))
            entry = add(
                month, f"{world.subject['name'].split()[0]} {statement}.",
                "personal", STATED if index == 0 else r.choice([STATED, OBSERVED]),
                f"chat/{world.month_label(month)}/msg_{r.randrange(1000, 9999)}.md",
                supersedes=previous, topic=topic,
            )
            previous = entry["id"]

    # ── life events become memories ───────────────────────────────────────
    for event in world.events:
        add(event["month"], event["what"] + ".", "personal", REPORTED,
            f"calendar/{world.month_label(event['month'])}/events.json",
            topic=event["kind"])

    # ── work facts that do not change ─────────────────────────────────────
    for project in world.projects:
        add(project.started_month,
            f"Works on project {project.name}.", "project", STATED,
            f"meetings/{world.month_label(project.started_month)}/kickoff.md",
            topic=f"project:{project.name}")

    for person in world.people:
        if not person.active(0):
            continue
        add(person.joined_month,
            f"{person.name} is a {person.role} at {person.org}.", "work", REPORTED,
            f"email/{world.month_label(person.joined_month)}/intro.eml",
            topic=f"colleague:{person.name}")

    # ── decisions, to reach the promotion budget ──────────────────────────
    # Salient facts have to SCALE with the pack. The specification asks for
    # 12,000 candidates of which 1,000 are worth keeping; a fixed set of
    # preferences, events, projects and colleagues tops out around two hundred,
    # and the remaining eight hundred would have to be padded from routine
    # encounters — which would mean the "what is worth keeping" answer key
    # contained a random sample of lunches. Decisions are genuinely worth
    # keeping and there is no shortage of them in two years of work.
    salient_now = len(out)
    if promote > salient_now:
        subjects = ["the deployment target", "the retry policy", "the on-call rota",
                    "the release cadence", "the review threshold", "the data model",
                    "the error budget", "the naming convention", "the test strategy",
                    "the rollout order", "the backup schedule", "the alert routing"]
        choices = ["Postgres", "a queue", "two weeks", "one reviewer", "canary first",
                   "a feature flag", "weekly", "nightly", "opt-in", "a hard cap"]
        for i in range(promote - salient_now):
            month = i % world.months
            project = world.projects[i % len(world.projects)]
            add(month,
                f"Decided {subjects[i % len(subjects)]} for {project.name} "
                f"is {choices[(i // len(subjects)) % len(choices)]} "
                f"(revision {i // (len(subjects) * len(choices)) + 1}).",
                "project", STATED,
                f"meetings/{world.month_label(month)}/decision_{i:05d}.md",
                topic=f"decision:{project.id}:{i}")

    # ── routine life, to reach volume ─────────────────────────────────────
    # Distinct facts, not restatements. The memory service suppresses
    # near-duplicates at 0.85 overlap, so a thousand paraphrases of one
    # sentence would collapse to one row and the volume would be a fiction.
    if volume > len(out):
        verbs = ["Met", "Reviewed a proposal with", "Paired with", "Had lunch with",
                 "Was unblocked by", "Handed over the on-call rota to"]
        places = ["the Kvarter cafe", "the Halden Bay office", "the annex",
                  "a video call", "the roof terrace"]
        needed = volume - len(out)
        for i in range(needed):
            month = i % world.months
            cast = world.active_people(month) or world.people
            person = cast[(i * 7 + month) % len(cast)]
            project = world.projects[(i * 3) % len(world.projects)]
            add(month,
                f"{verbs[i % len(verbs)]} {person.name} about {project.name} "
                f"at {places[i % len(places)]} (week {i % 4 + 1}).",
                "work", OBSERVED,
                f"calendar/{world.month_label(month)}/event_{i:04d}.ics",
                topic=f"encounter:{person.id}:{project.id}:{i}", salient=False)

    out.sort(key=lambda m: (m["month"], m["id"]))

    # ── promotion ─────────────────────────────────────────────────────────
    # A cap on what is worth keeping, never a quota to be filled. When the
    # budget exceeds the salient set the answer is "keep all of them", not
    # "promote some lunches to make up the numbers" — padding would put routine
    # encounters into the retention answer key and quietly destroy the only
    # thing this split measures.
    salient = [m for m in out if m["salient"]]
    budget = promote if promote > 0 else len(salient)
    # Most recent first, so a tight budget keeps what is still true.
    for entry in sorted(salient, key=lambda m: (-m["month"], m["id"]))[:budget]:
        entry["promoted"] = True

    return out


def current_preferences(memories: list[dict]) -> dict[str, dict]:
    """What is true NOW for each topic — the head of every supersession chain.

    This is the ground truth for "what does the user currently prefer". Derived
    from the generator rather than written by hand, so it cannot drift from the
    data it describes.
    """
    latest: dict[str, dict] = {}
    for m in memories:
        topic = m.get("topic")
        if not topic or not any(topic == t for t, _ in PREFERENCE_ARCS):
            continue
        seen = latest.get(topic)
        if seen is None or m["month"] >= seen["month"]:
            latest[topic] = m
    return latest


def promoted_ids(memories: list[dict]) -> set[str]:
    """What should survive consolidation. The complement is offered and dropped."""
    return {m["id"] for m in memories if m.get("promoted")}


def superseded_ids(memories: list[dict]) -> set[str]:
    """Every memory that a later one replaces. These must NOT be returned as
    current, and must still be findable when asked about the past."""
    return {m["supersedes"] for m in memories if m.get("supersedes")}
