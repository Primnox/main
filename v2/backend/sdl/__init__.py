"""Synthetic Digital Life — a coherent person, generated.

Crucible breaks subsystems. This gives it something real to break them WITH.

The difference from mock data is coherence. A pile of fake emails tests that a
parser does not crash; a person whose job changes in month 9, whose colleague
leaves in month 14, and whose coffee preference reverses twice tests whether
memory respects chronology, whether the graph survives a rename, and whether
retrieval can answer "which project changed owners after the reorg" — questions
that only exist because the artifacts agree with each other.

Four properties the whole package is built around.

DETERMINISTIC. One seed, one world. The same bytes on every machine and every
build, or a comparison between two Primnox versions measures the generator.

COHERENT. Every artifact references the same people, projects and dates. A
name in an email is a person in the graph is an attendee in a meeting.

TIMESTAMPED. Everything happens on a date, and the dataset is generated as
monthly snapshots. Nothing resets: month 14 contains month 1's history.

ANSWERABLE. `ground_truth.json` carries the correct answer to every query,
derived from the generator rather than written by hand — so retrieval can be
SCORED instead of eyeballed. That is what makes a different answer next release
a regression rather than a difference of opinion.
"""
from . import (code, contradictions, failure, graph, memory, recurrence,  # noqa: F401
               packs, score, truth, validate, world)

VERSION = "2.0.0"
