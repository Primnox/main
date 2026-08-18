"""Loading a Synthetic Life pack into the memory store.

The generator has its own self-tests. What those cannot check is the crossing
into Primnox: whether a two-year corpus still reads as two years once it is
rows in a table. It is the chronology that is fragile — it survives generation
and dies on insert — and a store where everything happened at once answers
"which preference is current" by accident.
"""
from __future__ import annotations

from datetime import datetime, timezone

from primnox2.memory import service as memory
from sdl import inject, memory as memory_gen, world as world_mod

import pytest

from primnox2.storage import db


@pytest.fixture
def clean_memory():
    with db.tx() as c:
        c.execute("DELETE FROM memories")
    yield
    with db.tx() as c:
        c.execute("DELETE FROM memories")


def _world():
    return world_mod.build(seed=7, months=6, people_count=8, project_count=5)


def test_every_memory_lands_inside_its_own_month():
    """The spread that keeps same-month memories orderable must not push one
    into the next month, or the timeline the pack asserts stops being true."""
    world = _world()
    rows = sorted(memory_gen.generate(world, volume=60),
                  key=lambda m: (m["month"], m["id"]))
    stamps = inject._timestamps(rows, world.month_date)

    for row, stamp in zip(rows, stamps):
        when = datetime.fromtimestamp(stamp / 1000, timezone.utc).date()
        assert when.year == world.month_date(row["month"]).year
        assert when.month == world.month_date(row["month"]).month


def test_memories_in_one_month_are_ordered_not_simultaneous():
    """`ORDER BY created_at DESC` is how the store reads back. Identical
    timestamps make that ordering arbitrary, which looks like a sorting bug in
    the UI and is really a loss of information at import."""
    world = _world()
    rows = sorted(memory_gen.generate(world, volume=60),
                  key=lambda m: (m["month"], m["id"]))
    stamps = inject._timestamps(rows, world.month_date)

    by_month: dict[int, list[int]] = {}
    for row, stamp in zip(rows, stamps):
        by_month.setdefault(row["month"], []).append(stamp)

    crowded = [v for v in by_month.values() if len(v) > 1]
    assert crowded, "the fixture should put several memories in one month"
    for stamps_in_month in crowded:
        assert stamps_in_month == sorted(stamps_in_month)
        assert len(set(stamps_in_month)) == len(stamps_in_month)


def test_every_injected_memory_is_marked_imported():
    """Nobody said any of this and no conversation inferred it.

    This previously mapped SDL confidence onto provenance, so `stated` rows
    landed as `explicit` — which the memory list renders as "you said". The
    result was a screen attributing ninety-odd sentences about fictional people
    to the user as their own statements. Provenance records WHERE a fact came
    from, and for a synthetic pack there is exactly one true answer.
    """
    assert set(inject.PROVENANCE.values()) == {"imported"}
    for confidence in (memory_gen.STATED, memory_gen.OBSERVED, memory_gen.REPORTED):
        assert inject.PROVENANCE[confidence] == "imported"


def test_no_injected_memory_is_ever_attributed_to_the_user():
    """The guarantee stated end to end, over a real generated pack: not one row
    may claim the user said it or that a chat inferred it."""
    world = _world()
    rows = memory_gen.generate(world, volume=60)
    provenances = {inject.PROVENANCE.get(r["confidence"], "imported") for r in rows}
    assert "explicit" not in provenances, "a synthetic row claimed the user said it"
    assert "inferred_chat" not in provenances, "a synthetic row claimed a chat inferred it"


def test_a_loaded_pack_can_still_answer_what_is_current(clean_memory):
    """End to end: load a pack, then ask the store the question the ground
    truth answers. The newest memory on a topic has to come back first."""
    world = _world()
    rows = sorted(memory_gen.generate(world, volume=40),
                  key=lambda m: (m["month"], m["id"]))
    stamps = inject._timestamps(rows, world.month_date)
    memory.import_many([
        {"text": r["text"], "category": r["category"],
         "provenance": inject.PROVENANCE.get(r["confidence"], "imported"),
         "created_at": s}
        for r, s in zip(rows, stamps)])

    current = memory_gen.current_preferences(rows)
    theme = current.get("theme")
    assert theme, "the fixture world should carry a theme preference arc"

    stored = memory.live(limit=10_000)
    texts = [m["text"] for m in stored]
    # Both statements are kept — the contradiction is the point — but the one
    # that is true now must be the more recent row.
    assert theme["text"] in texts
    on_theme = [m for m in stored if "mode" in m["text"]]
    assert on_theme[0]["text"] == theme["text"]


# ── Where a pack is allowed to land ──────────────────────────────────────────
# `--pack memory-100` used to be a complete command, and it wrote to the app's
# real database. The store was found holding a hundred synthetic rows and zero
# real ones. These tests exist so a default can never grow back: the failure
# was not a bad path, it was no path at all being typed.
def test_injecting_without_a_destination_refuses():
    with pytest.raises(SystemExit) as e:
        inject.main(["--pack", "memory-100"])
    assert "no destination" in str(e.value)


def test_the_refusal_names_both_ways_to_be_explicit():
    """An error that only says no teaches nothing. This one has to hand back
    the two flags, or the next person guesses and guesses wrong."""
    with pytest.raises(SystemExit) as e:
        inject.main(["--pack", "memory-100"])
    message = str(e.value)
    assert "--db" in message
    assert "--app-db" in message


def test_naming_both_destinations_refuses_rather_than_picking_one():
    with pytest.raises(SystemExit) as e:
        inject.main(["--pack", "memory-100", "--db", "x.db", "--app-db"])
    assert "one" in str(e.value)


def test_a_dry_run_needs_no_destination_and_says_it_has_none(capsys):
    """A dry run opens nothing, so the guard would only cost the cheap way to
    read a pack. It must not print a path it would not actually have used."""
    assert inject.main(["--pack", "memory-100", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "nowhere" in out
    assert "primnox.db" not in out


def test_a_dry_run_with_a_destination_names_it(capsys):
    inject.main(["--pack", "memory-100", "--dry-run", "--db", "scratch.db"])
    assert "scratch.db" in capsys.readouterr().out
