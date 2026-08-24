"""The Synthetic Life Database, tested on the properties it sells.

The generator already carries `validate.py`, which checks that a produced corpus
agrees with itself. These are the checks that live one level up: the guarantees a
CALLER relies on and that validation cannot see — determinism across processes,
the resolution rule matching its own answer key, the scorer refusing to reward a
confident guess, and ticks that mean the same thing whatever order they ran in.

Each one exists because getting it wrong produces a benchmark that still runs,
still reports a number, and is measuring something other than what it claims.
"""
from __future__ import annotations

import json

import pytest

from sdl import (recurrence as calendar_gen, code as code_gen, contradictions,
                 evolve, failure, generate, memory as memory_gen, score,
                 world as world_mod)


def _world(months=12, people=20, projects=10, repos=8, disputes=8):
    return world_mod.build(seed=4242, months=months, people_count=people,
                           project_count=projects, repo_count=repos,
                           dispute_count=disputes)


# ── determinism ──────────────────────────────────────────────────────────────
def test_two_builds_of_one_seed_are_identical():
    """A comparison between two Primnox versions measures the generator unless
    the generator is fixed. Any nondeterminism here shows up as a retrieval
    regression that nobody can reproduce."""
    a, b = _world(), _world()
    assert [p.name for p in a.people] == [p.name for p in b.people]
    assert [p.owner_id for p in a.projects] == [p.owner_id for p in b.projects]
    assert a.features == b.features
    assert [s.id for s in a.series] == [s.id for s in b.series]
    assert [d.resolved for d in a.disputes] == [d.resolved for d in b.disputes]


def test_a_new_stream_does_not_shift_the_existing_ones():
    """Artifact streams are salted per kind so adding emails cannot move the
    chat messages. Without it, one new volume knob rewrites the whole corpus and
    every diff between two packs is unreadable."""
    from sdl import artifacts
    world = _world()
    chats = artifacts.chats(world, 200)
    artifacts.emails(world, 999)
    assert artifacts.chats(world, 200) == chats


# ── the world's own rules ────────────────────────────────────────────────────
def test_every_feature_is_introduced_before_it_is_adopted():
    world = _world()
    for feature in world.features:
        for adopter in feature["adopters"]:
            assert adopter["month"] > feature["first_month"], feature["name"]
            assert adopter["repo"] != feature["first_repo"]


def test_no_chore_wording_collides_with_a_feature_name():
    """"Which repository introduced OAuth first" needs exactly one defensible
    answer. A filler commit reading "add response caching" would give it two."""
    assert code_gen.feature_vocabulary_is_disjoint()


def test_lapsed_series_never_end_in_a_life_event_month():
    """Otherwise "which meetings stopped because of the reorg" is unanswerable
    from the data, and a correct system is marked wrong for a distinction the
    corpus does not carry."""
    world = _world(months=24)
    event_months = {e["month"] for e in world.events}
    for series in world.series:
        if series.ended_by is None and series.end_month is not None:
            assert series.end_month not in event_months, series.id


def test_a_short_pack_scales_life_events_rather_than_dropping_them():
    """Truncating would silently remove the event several answers depend on."""
    short = _world(months=6)
    assert {e["kind"] for e in short.events} == {
        e["kind"] for e in _world(months=24).events}
    assert all(0 <= e["month"] < 6 for e in short.events)


# ── contradictions ───────────────────────────────────────────────────────────
def test_the_answer_key_agrees_with_the_resolution_rule():
    """The rule and the key must be the same thing. If they drift, the benchmark
    tests whichever one the reader happened to trust."""
    assert contradictions.rule_holds(_world())


def test_both_halves_of_the_rule_are_exercised():
    """A pure-recency implementation and a pure-authority one must not both
    pass. Each needs a case that only the correct rule gets right."""
    world = _world(disputes=12)
    built = contradictions.build(world)
    shapes = {r["tests"] for r in built["resolutions"]}
    assert shapes == {"authority", "recency"}

    authority = next(r for r in built["resolutions"] if r["tests"] == "authority")
    dispute = next(d for d in world.disputes if d.id == authority["dispute"])
    latest = max(dispute.claims, key=lambda c: c["month"])
    # The most recent claim is the WEAK one, so recency alone gets it wrong.
    assert latest["value"] != authority["answer"]
    assert authority["decided_by"] == "calendar"


def test_a_claim_is_written_for_every_source_in_a_dispute():
    """The conflict has to exist in the corpus, not only in the answer key. A
    system cannot reproduce a file it was never given."""
    world = _world(disputes=6)
    built = contradictions.build(world)
    for dispute in world.disputes:
        written = [c for c in built["claims"] if c["dispute"] == dispute.id]
        assert len(written) == len(dispute.claims)
        assert sum(1 for c in written if c["authoritative"]) == 1


def test_claim_text_names_the_thing_under_dispute():
    """Regression: the subject was recovered by searching the question for
    "the ", which picked "the week" out of "which day of the week is the Atlas
    sync on" and wrote every claim about the wrong noun."""
    world = _world(disputes=6)
    for claim in contradictions.build(world)["claims"]:
        dispute = next(d for d in world.disputes if d.id == claim["dispute"])
        assert dispute.about in claim["text"]
        assert "the week" not in claim["text"]


# ── the calendar ─────────────────────────────────────────────────────────────
def test_retained_series_are_expanded_in_full():
    """A recurring meeting missing occurrences is indistinguishable from one
    repeatedly cancelled, so a thinned series makes the benchmark score its own
    sampling."""
    world = _world(months=24)
    built = calendar_gen.build(world, budget=400)
    for series in built["series"]:
        end = series.end_month if series.end_month is not None else world.months
        expected = set(range(series.start_month, min(end, world.months)))
        seen = {e["month"] for e in built["events"] if e["series"] == series.id}
        assert expected <= seen, series.id


def test_a_tight_budget_drops_whole_series_and_keeps_the_event_linked_ones():
    world = _world(months=24)
    built = calendar_gen.build(world, budget=120)
    assert built["dropped"], "a tight budget should leave something out"
    kept = {s.id for s in built["series"]}
    for series in world.series:
        if series.ended_by == "reorg":
            assert series.id in kept, "the reorg series carries its own queries"


def test_a_moved_event_keeps_both_dates():
    """Overwriting the date loses the fact that it moved, which is what "was the
    review rescheduled" asks about."""
    built = calendar_gen.build(_world(months=24), budget=400)
    moved = [e for e in built["events"] if e["status"] == calendar_gen.MOVED]
    assert moved
    assert all(e["moved_to"] and e["moved_to"] != e["date"] for e in moved)


# ── memory ───────────────────────────────────────────────────────────────────
def test_promotion_separates_what_to_keep_from_what_was_merely_observed():
    """A store that keeps everything must not score the same as one that keeps
    the right things."""
    world = _world(months=24)
    rows = memory_gen.generate(world, volume=300, promote=60)
    promoted = memory_gen.promoted_ids(rows)
    assert len(promoted) == 60
    assert len(promoted) < len(rows)
    # Preferences and life events are worth keeping; "had lunch with someone in
    # week 3" is not.
    kept = [m for m in rows if m["promoted"]]
    assert all(m["salient"] for m in kept), "a routine encounter was promoted " \
        "while a salient fact was not"


def test_supersession_never_points_at_a_later_memory():
    rows = memory_gen.generate(_world(months=24), volume=200, promote=50)
    by_id = {m["id"]: m for m in rows}
    for row in rows:
        prior = row.get("supersedes")
        if prior:
            assert by_id[prior]["month"] <= row["month"]


# ── ground truth ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    out = tmp_path_factory.mktemp("sldb") / "memory-100"
    manifest = generate.generate("memory-100", out, seed=4242)
    return out, manifest


def test_a_generated_pack_passes_its_own_validation(pack):
    _, manifest = pack
    assert manifest["validation"]["failed"] == 0, \
        manifest["validation"]["failures"]


def test_all_six_levels_are_present(pack):
    out, _ = pack
    queries = json.loads((out / "queries.json").read_text(encoding="utf-8"))
    assert {q["level"] for q in queries} == {1, 2, 3, 4, 5, 6}


def test_the_questions_file_never_contains_the_answers(pack):
    """A system under test may read queries.json. Handing it the answers, the
    evidence or the expected path in the same file would let it score without
    retrieving anything."""
    out, _ = pack
    raw = (out / "queries.json").read_text(encoding="utf-8")
    for query in json.loads(raw):
        assert "answer" not in query
        assert "evidence" not in query
        assert "graph_path" not in query


def test_every_query_carries_resolvable_evidence(pack):
    out, _ = pack
    truth_rows = json.loads((out / "ground_truth.json").read_text(encoding="utf-8"))
    assert truth_rows
    for query_id, row in truth_rows.items():
        assert row["evidence"], query_id


def test_graph_rows_survive_a_round_trip_through_the_file(pack):
    """Regression: a document node carried its own `kind` attribute, which
    overwrote the row marker separating nodes from edges. Every document came
    back from the file as an edge with no source."""
    out, manifest = pack
    nodes = edges = 0
    for line in (out / "graph.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["kind"] == "node":
            nodes += 1
            assert row["id"] and row["type"]
        else:
            edges += 1
            assert row["source"] and row["target"]
    assert nodes == manifest["counts"]["graph_nodes"]
    assert edges == manifest["counts"]["graph_edges"]


# ── scoring ──────────────────────────────────────────────────────────────────
def _queries_from(pack_dir):
    truth_rows = json.loads(
        (pack_dir / "ground_truth.json").read_text(encoding="utf-8"))
    return [{"id": k, **v} for k, v in truth_rows.items()]


def test_a_perfect_answer_sheet_scores_a_hundred(pack):
    """If the oracle cannot score full marks, the suite is unanswerable and
    every number it produces is measuring the scorer."""
    out, _ = pack
    queries = _queries_from(out)
    perfect = {q["id"]: {"answer": q["answer"], "evidence": q["evidence"],
                         "as_of_month": q["as_of_month"],
                         "graph_path": q["graph_path"], "latency_ms": 100}
               for q in queries}
    report = score.run(queries, perfect)
    assert report["overall"] == 100.0
    assert report["grade"] == "EXCELLENT"


def test_a_correct_answer_with_no_evidence_cannot_reach_good(pack):
    """The whole reason evidence is weighted at 25%. A system that returns the
    right string while citing nothing has guessed, and next month it guesses
    wrong."""
    out, _ = pack
    queries = _queries_from(out)
    guessing = {q["id"]: {"answer": q["answer"], "evidence": [],
                          "as_of_month": q["as_of_month"],
                          "graph_path": q["graph_path"], "latency_ms": 100}
                for q in queries}
    report = score.run(queries, guessing)
    assert report["overall"] < 85.0
    assert report["grade"] in ("NEEDS WORK", score.REGRESSION)


def test_an_unanswered_query_scores_zero_rather_than_being_declined():
    """Declining is for axes the ANSWER KEY cannot test. A system that stays
    quiet must not be excused for it, or silence becomes a strategy."""
    query = {"id": "q:1", "level": 1, "kind": "recall", "subsystem": "Memory",
             "answer": "x", "evidence": ["a"], "as_of_month": 3, "graph_path": []}
    result = score.score_one(query, None)
    assert result.percent == 0.0
    assert result.answered is False
    assert result.declined == []


def test_an_axis_the_key_cannot_test_is_declined_not_zeroed():
    """A query with no expected graph path must not drag a system's score down
    for failing to produce one."""
    query = {"id": "q:1", "level": 1, "kind": "recall", "subsystem": "Memory",
             "answer": "x", "evidence": ["a"], "as_of_month": 3, "graph_path": []}
    result = score.score_one(query, {"answer": "x", "evidence": ["a"],
                                     "as_of_month": 3, "latency_ms": 10})
    assert "path" in result.declined
    assert result.percent == 100.0


def test_partial_credit_tracks_partial_recall():
    """A binary score cannot see the difference between ten of eleven and none
    of eleven, so it cannot see an improvement either."""
    expected = ["a", "b", "c", "d"]
    assert score.compare_answer(expected, ["a", "b", "c", "d"]) == 1.0
    assert 0.5 < score.compare_answer(expected, ["a", "b", "c"]) < 1.0
    assert score.compare_answer(expected, ["x", "y"]) == 0.0


def test_a_partly_right_dictionary_does_not_score_full_marks():
    """Regression guard: scoring only the keys present in the response let an
    answer containing one correct field score 100%."""
    expected = {"role": "Engineer", "org": "Halcyon", "meetings": 4}
    assert score.compare_answer(expected, {"role": "Engineer"}) < 0.5


# ── failure injection ────────────────────────────────────────────────────────
def test_damage_is_written_to_a_copy_and_classified(pack, tmp_path):
    """What matters is not that the system survives — anything survives a
    missing file by returning nothing — but that the manifest says which
    answers should now degrade."""
    import shutil
    out, _ = pack
    damaged = tmp_path / "damaged"
    shutil.copytree(out, damaged)
    report = failure.apply(damaged, list(failure.MODES), seed=5)

    assert (damaged / "failures.json").exists()
    assert {d["mode"] for d in report["damage"]} == set(failure.MODES)
    # The clean pack is untouched, so the benchmark can be run again.
    assert len(json.loads((out / "documents.jsonl").read_text(encoding="utf-8")
                          .splitlines()[0])) > 0
    for affected in report["affected_queries"]:
        assert affected["expect"] in (failure.STILL, failure.DEGRADE)
        if affected["expect"] == failure.DEGRADE:
            assert not affected["surviving_evidence"]


def test_ocr_damage_looks_like_ocr_rather_than_random_bytes(pack, tmp_path):
    """Glyph confusions survive review and then break exact matching, which is
    the failure mode worth simulating. Random noise is caught immediately."""
    import shutil
    out, _ = pack
    damaged = tmp_path / "ocr"
    shutil.copytree(out, damaged)
    failure.apply(damaged, ["ocr_noise"], seed=5)

    rows = [json.loads(line) for line in
            (damaged / "photos.jsonl").read_text(encoding="utf-8").splitlines()]
    changed = [r for r in rows if "ocr_text_was" in r]
    for row in changed:
        assert row["ocr_text"] != row["ocr_text_was"]
        assert abs(len(row["ocr_text"]) - len(row["ocr_text_was"])) <= 1


# ── evolution ────────────────────────────────────────────────────────────────
def test_a_tick_is_the_same_whatever_ran_before_it(pack):
    """Ticks are seeded by tick NUMBER. A generator whose output depends on how
    many times it has been called cannot compare two versions of anything."""
    out, _ = pack
    world, pack_def, _ = evolve.load_world(out)
    base = evolve._base_queries(out)

    alone = evolve.tick(world, pack_def, 3, base)
    evolve.tick(world, pack_def, 1, base)
    evolve.tick(world, pack_def, 2, base)
    after = evolve.tick(world, pack_def, 3, base)
    assert alone["rows"] == after["rows"]
    assert alone["ground_truth"] == after["ground_truth"]


def test_a_tick_lands_in_the_month_after_the_pack_ends(pack):
    """Regression: an open-coded label put tick 1 of a 24-month pack in 2028."""
    out, _ = pack
    world, pack_def, _ = evolve.load_world(out)
    result = evolve.tick(world, pack_def, 1, evolve._base_queries(out))
    assert result["month"] == pack_def.months
    assert result["label"] == world.month_label(pack_def.months)


def test_a_tick_reports_which_base_answers_it_invalidated(pack):
    """The reason the whole module exists: a system that indexed once will keep
    answering these correctly-as-of-generation, and be confidently wrong."""
    out, _ = pack
    world, pack_def, _ = evolve.load_world(out)
    base = evolve._base_queries(out)
    stale = [row for n in range(1, 5)
             for row in evolve.tick(world, pack_def, n, base)["stale"]]
    assert stale, "four ticks should invalidate something"
    assert any(row["kind"] == "fact_changed" for row in stale)
    for row in stale:
        assert row["was"] != row["now"]
        assert row["kind"] in ("fact_changed", "evidence_moved")


# ── the packs ────────────────────────────────────────────────────────────────
def test_every_pack_generates_and_validates(tmp_path):
    """Cheap packs only. The full pack is a seven-second, 380,000-edge run and
    belongs in a nightly job, not in a suite people run before committing."""
    for name in ("memory-10", "memory-100"):
        manifest = generate.generate(name, tmp_path / name, seed=11)
        assert manifest["validation"]["failed"] == 0, \
            (name, manifest["validation"]["failures"])
        assert manifest["counts"]["queries"] > 0


def test_the_smallest_pack_still_asks_something_at_every_level(tmp_path):
    """A pack that quietly becomes recall-only would report an overall score for
    capabilities it never tested."""
    generate.generate("memory-10", tmp_path / "tiny", seed=11)
    queries = json.loads(
        (tmp_path / "tiny" / "queries.json").read_text(encoding="utf-8"))
    assert {q["level"] for q in queries} == {1, 2, 3, 4, 5, 6}
