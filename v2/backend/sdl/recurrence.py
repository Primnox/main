"""The calendar: things that repeat, and things that stop repeating.

A pile of dated events tests that dates parse. What this generates instead is
RECURRENCE with a lifecycle — a standup that runs every week for fourteen months
and then never appears again, in the month of the reorganisation — because the
question users actually ask is about an absence, and an absence is the one thing
a corpus of independently-generated events can never contain.

Two rules the expansion is careful about.

Every retained series is expanded IN FULL. When a pack's budget will not fit
another series, the series is left out entirely rather than thinned. A recurring
meeting missing half its occurrences is indistinguishable from one that was
repeatedly cancelled, and a benchmark that cannot tell those apart is scoring
its own sampling.

Series carrying a life event are retained FIRST. `ends_at="reorg"` is the reason
several queries exist; dropping it to make room for a book club would remove the
question rather than shrink it.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .world import CADENCE_PER_MONTH, Series, World

HELD, CANCELLED, MOVED = "held", "cancelled", "moved"

ONE_OFF_KINDS = [
    ("Dentist", "personal"), ("Flight to Lisbon", "travel"),
    ("Return flight", "travel"), ("Apartment viewing", "personal"),
    ("Annual review", "work"), ("Team offsite", "work"),
    ("Doctor", "personal"), ("Visa appointment", "personal"),
    ("Conference talk", "work"), ("Hackathon", "work"),
    ("Rowan's birthday", "personal"), ("Car service", "personal"),
]


def _occurrence(first_of_month: date, weekday: int, n: int) -> date | None:
    """The nth occurrence of a weekday in a month, or None if it runs past the end."""
    offset = (weekday - first_of_month.weekday()) % 7
    d = first_of_month + timedelta(days=offset + 7 * n)
    return d if d.month == first_of_month.month else None


def _slots(cadence: str) -> list[int]:
    return {"weekly": [0, 1, 2, 3], "biweekly": [0, 2], "monthly": [1]}[cadence]


def _expanded_size(series: Series, months: int) -> int:
    span = (series.end_month if series.end_month is not None else months) - series.start_month
    return max(0, span) * CADENCE_PER_MONTH[series.cadence]


def _priority(series: Series) -> tuple:
    """Event-linked series first, then lapses, then everything else."""
    linked = 0 if (series.started_by or series.ended_by) else 1
    lapsed = 0 if series.end_month is not None else 1
    return (linked, lapsed, series.id)


def build(world: World, budget: int = 900) -> dict:
    """Recurring instances plus one-off events, inside a total budget.

    Returns `{"events", "series", "dropped"}`. `series` is the list actually
    expanded — ground truth must be built from that rather than from
    `world.series`, or a small pack asks questions about a standup it does not
    contain and fails itself.
    """
    r = random.Random(world.seed ^ 0xCA1E)
    ordered = sorted(world.series, key=_priority)

    kept: list[Series] = []
    spent = 0
    # A fifth of the budget is held back for one-off events. A calendar that is
    # nothing but recurring meetings has no texture, and "what was I doing the
    # week I moved" needs something that happened exactly once.
    recurring_budget = int(budget * 0.8)
    for series in ordered:
        size = _expanded_size(series, world.months)
        if size == 0:
            continue
        if spent + size > recurring_budget and kept:
            continue
        kept.append(series)
        spent += size

    events: list[dict] = []
    for series in sorted(kept, key=lambda s: s.id):
        end = series.end_month if series.end_month is not None else world.months
        for month in range(series.start_month, min(end, world.months)):
            first = world.month_date(month)
            for n in _slots(series.cadence):
                when = _occurrence(first, series.weekday, n)
                if when is None:
                    continue
                roll = r.random()
                status = (CANCELLED if roll < 0.06
                          else MOVED if roll < 0.11 else HELD)
                events.append({
                    "id": f"cal:{len(events):05d}",
                    "series": series.id,
                    "series_title": series.title,
                    "title": series.title,
                    "kind": series.kind,
                    "recurring": True,
                    "month": month,
                    "date": when.isoformat(),
                    "weekday": when.strftime("%A"),
                    "attendees": list(series.attendees),
                    "status": status,
                    # A moved instance keeps its original slot AND its new one.
                    # Overwriting the date loses the fact that it moved, which is
                    # exactly what "was the review rescheduled" asks about.
                    "moved_to": ((when + timedelta(days=2)).isoformat()
                                 if status == MOVED else None),
                })

    # ── one-off events, some of them anchored to the life events ──────────
    anchored = {
        "moved_apartment": "Moving day",
        "conference": "Conference talk",
        "promotion": "Annual review",
        "new_laptop": "Laptop pickup",
    }
    for event in world.events:
        title = anchored.get(event["kind"])
        if not title:
            continue
        first = world.month_date(event["month"])
        when = _occurrence(first, 2, 1) or first
        events.append({
            "id": f"cal:{len(events):05d}", "series": None, "series_title": None,
            "title": title, "kind": "personal", "recurring": False,
            "month": event["month"], "date": when.isoformat(),
            "weekday": when.strftime("%A"), "attendees": [world.subject["id"]],
            "status": HELD, "moved_to": None, "anchors": event["kind"],
        })

    remaining = max(0, budget - len(events))
    for i in range(remaining):
        month = i % world.months
        first = world.month_date(month)
        title, kind = ONE_OFF_KINDS[i % len(ONE_OFF_KINDS)]
        when = _occurrence(first, i % 5, (i // 5) % 4) or first
        cast = world.active_people(month) or world.people
        events.append({
            "id": f"cal:{len(events):05d}", "series": None, "series_title": None,
            "title": title, "kind": kind, "recurring": False,
            "month": month, "date": when.isoformat(),
            "weekday": when.strftime("%A"),
            "attendees": [world.subject["id"]] + (
                [cast[(i * 3) % len(cast)].id] if kind == "work" else []),
            "status": CANCELLED if r.random() < 0.05 else HELD,
            "moved_to": None,
        })

    return {"events": events, "series": kept,
            "dropped": [s.id for s in world.series if s not in kept]}


def series_ending_at(kept: list[Series], event_kind: str) -> list[Series]:
    return [s for s in kept if s.ended_by == event_kind]


def series_starting_at(kept: list[Series], event_kind: str) -> list[Series]:
    return [s for s in kept if s.started_by == event_kind]


def active_series(kept: list[Series], month: int) -> list[Series]:
    return [s for s in kept if s.runs_in(month)]
