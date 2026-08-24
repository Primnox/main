"""Benchmark packs — the same world at seven sizes.

A pack is a set of volumes, not a different dataset: every pack comes from the
same generator and the same seed, so a defect in the generator shows up in all of
them and a nightly run and a commit-hook run exercise the same code.

What a pack is NOT is a prefix of a larger one. Volumes and cast size are inputs
to the world, so memory-100's fifth chat message is not office-500's fifth
message — the months are spread across a different span and the people are drawn
from a different cast. Each pack is byte-identical from run to run, which is what
makes comparing two Primnox versions meaningful; comparing two PACKS to each
other is not something the data supports, and a test asserting otherwise would
be asserting a property nobody implemented.

Volumes are written out per pack rather than derived from a scale factor. A
single multiplier looks tidy and produces nonsense — an executive with 25,000
code symbols, a six-month pack carrying twelve life events — and the shape of
someone's data is the thing being simulated, not just its size.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pack:
    name: str
    purpose: str
    months: int
    people: int
    projects: int
    chats: int
    emails: int
    meetings: int
    documents: int
    symbols: int
    photos: int
    memories: int = 0
    # Everything below arrived with the SLDB specification. Defaulted so a pack
    # definition stays readable, and so an older caller constructing a Pack by
    # hand does not break.
    repos: int = 40
    calendar: int = 0
    tasks: int = 0
    notes: int = 0
    commits: int = 0
    issues: int = 0
    prs: int = 0
    todos: int = 0
    # Memory candidates are what a system is offered; `promoted` is what it
    # should keep. The gap between them is the whole point of the distinction:
    # a store that keeps everything scores the same as one that keeps nothing
    # unless the dataset says which facts were worth keeping.
    promoted: int = 0
    disputes: int = 24
    queries: int = 500

    def as_dict(self) -> dict:
        return dict(self.__dict__)


PACKS: dict[str, Pack] = {p.name: p for p in [
    Pack("memory-10", "Ten memories. A smoke test that runs in a second.",
         months=6, people=6, projects=4, chats=40, emails=8, meetings=4,
         documents=10, symbols=0, photos=0, memories=10, promoted=6,
         repos=4, calendar=40, tasks=20, notes=15, commits=60, issues=10,
         prs=8, todos=6, disputes=4, queries=60),

    Pack("memory-100", "A hundred memories with real supersession chains.",
         months=18, people=20, projects=12, chats=300, emails=40, meetings=20,
         documents=60, symbols=0, photos=0, memories=100, promoted=40,
         repos=8, calendar=200, tasks=120, notes=90, commits=600, issues=60,
         prs=45, todos=30, disputes=8, queries=150),

    Pack("office-500", "An office worker: meetings, documents, few repositories.",
         months=24, people=60, projects=30, chats=1_500, emails=200, meetings=80,
         documents=300, symbols=1_000, photos=400, memories=400, promoted=150,
         repos=12, calendar=700, tasks=500, notes=400, commits=1_500,
         issues=180, prs=140, todos=90, queries=400),

    Pack("developer-1k", "A developer: large codebase, heavy commit history.",
         months=24, people=60, projects=40, chats=2_000, emails=150, meetings=60,
         documents=250, symbols=25_000, photos=300, memories=500, promoted=200,
         repos=40, calendar=600, tasks=800, notes=500, commits=12_000,
         issues=700, prs=1_600, todos=400),

    Pack("executive-5k", "An executive: meeting-dominated, light code.",
         months=24, people=120, projects=80, chats=5_000, emails=400, meetings=120,
         documents=600, symbols=2_000, photos=800, memories=1_000, promoted=350,
         repos=16, calendar=900, tasks=1_200, notes=900, commits=2_000,
         issues=300, prs=240, todos=120),

    Pack("enterprise-50k", "Graph stress: heavy on every axis at once.",
         months=24, people=120, projects=80, chats=5_000, emails=400, meetings=120,
         documents=600, symbols=25_000, photos=2_000, memories=1_000,
         promoted=400, repos=40, calendar=900, tasks=2_000, notes=1_500,
         commits=18_000, issues=900, prs=2_200, todos=400),

    # The specification's own table, at full size. This is the one that answers
    # "does Graphify survive a real life" — a hundred thousand nodes and a third
    # of a million edges, generated from the same seed as memory-10.
    Pack("sldb-24m", "The full Synthetic Life Database: 24 months, everything.",
         months=24, people=120, projects=80, chats=120_000, emails=600,
         meetings=900, documents=680, symbols=25_000, photos=6_000,
         memories=12_000, promoted=1_000, repos=40, calendar=900, tasks=2_000,
         notes=1_500, commits=18_000, issues=900, prs=2_200, todos=400),
]}

DEFAULT = "office-500"


def get(name: str) -> Pack:
    if name not in PACKS:
        raise KeyError(f"unknown pack {name!r}; have {', '.join(sorted(PACKS))}")
    return PACKS[name]
