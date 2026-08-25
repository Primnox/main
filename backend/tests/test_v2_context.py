"""Tests for the context builder.

The target is the minimum context that preserves correctness. So these check
that the right sources are consulted, that every fragment says where it came
from, that duplicates across sources collapse, and that a budget is a budget
— including the case where a selected source has no tool wired up, which
must be reported rather than silently answered around.
"""

from datetime import datetime, timedelta, timezone

import pytest

from v2 import context, episodes, store, task_state as ts, world_model as wm


@pytest.fixture
def db(tmp_path):
    store.reset_for_tests(tmp_path / "v2.db")
    yield context
    store.reset_for_tests(None)


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
YESTERDAY = datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def world(db):
    wm.record_fact("This project uses npm", project="primnox", slot="package_manager")
    file_entity = wm.upsert_entity("file", "router.py", project="primnox")
    for offset, (kind, summary) in enumerate(
        [("file_modified", "modified router.py"), ("test_failed", "test_retrieval failed")]
    ):
        episodes.record_event(
            kind, summary, project="primnox", entities=[file_entity["id"]],
            occurred_at=YESTERDAY + timedelta(minutes=4 * offset),
        )
    episodes.consolidate(project="primnox")
    task = ts.start("reduce tool cost", project="primnox", plan=["benchmark", "compact"])
    ts.complete_action(task["actions"][0]["id"])
    return task


class TestSourceSelection:
    def test_a_temporal_question_reconstructs_from_episodes(self, db, world):
        built = db.build("What was I doing yesterday?", project="primnox", now=NOW)
        assert built.route.label == "H"
        assert any(f.source == "history" for f in built.fragments)
        assert "router.py" in built.render()

    def test_a_memory_question_returns_current_facts(self, db, world):
        built = db.build("What do you remember about this project?", project="primnox", now=NOW)
        assert "uses npm" in built.render()

    def test_resuming_returns_task_state_not_a_transcript(self, db, world):
        built = db.build("Continue what I was doing.", project="primnox", now=NOW)
        assert any(f.source == "task_state" for f in built.fragments)
        assert "Next: → compact" in built.render()

    def test_a_structural_question_uses_the_graph(self, db, tmp_path, world):
        from v2 import graphify

        repo = tmp_path / "repo"
        (repo / "app").mkdir(parents=True)
        (repo / "app" / "auth.py").write_text(
            "def authenticate():\n    pass\n\n\ndef login():\n    return authenticate()\n"
        )
        graphify.index(repo, project="primnox")
        built = db.build("What calls `authenticate`?", project="primnox", now=NOW)
        assert built.route.label == "G"
        assert any("calls authenticate" in f.text for f in built.fragments)

    def test_an_empty_world_produces_empty_context_not_an_error(self, db):
        built = db.build("What was I doing yesterday?", project="nothing", now=NOW)
        assert built.fragments == []
        assert built.render() == ""


class TestInjectedTools:
    def test_a_lexical_question_uses_the_supplied_searcher(self, db, world):
        built = db.build(
            "Where is the API key loaded?",
            project="primnox",
            searcher=lambda q: [{"text": "settings_manager.py:42 groq_api_key", "ref": "settings_manager.py:42"}],
            now=NOW,
        )
        assert any(f.source == "search" for f in built.fragments)
        assert "settings_manager.py:42" in built.render()

    def test_plain_strings_from_a_tool_are_accepted(self, db, world):
        built = db.build("Where is the key loaded?", project="primnox",
                         searcher=lambda q: ["settings_manager.py:42"], now=NOW)
        assert any("settings_manager.py:42" in f.text for f in built.fragments)

    def test_a_missing_tool_is_reported_not_worked_around(self, db, world):
        built = db.build("Where is the API key loaded?", project="primnox", now=NOW)
        assert any("no searcher" in note for note in built.notes)

    def test_a_failing_tool_does_not_lose_the_rest_of_the_context(self, db, world):
        def broken(question):
            raise RuntimeError("search index unavailable")

        built = db.build("What do you remember about this project?", project="primnox",
                         searcher=broken, now=NOW)
        assert "uses npm" in built.render()

    def test_a_document_question_uses_the_supplied_reader(self, db, world):
        built = db.build(
            "According to that PDF, what is the retention policy?",
            project="primnox",
            reader=lambda q: [{"text": "Retention: 30 days", "ref": "art_abc"}],
            now=NOW,
        )
        assert any(f.source == "read" for f in built.fragments)


class TestRankingAndBudget:
    def test_every_fragment_carries_its_provenance(self, db, world):
        built = db.build("What do you remember about this project?", project="primnox", now=NOW)
        for record in built.provenance():
            assert record["source"] and record["origin"] and record["ref"]

    def test_stated_facts_outrank_inferences(self, db):
        wm.record_fact("uses npm", project="p", prov=wm.USER_STATED)
        wm.record_fact("probably deploys on Friday", project="p", prov=wm.MODEL_INFERRED)
        built = db.build("What do you remember about p?", project="p", now=NOW)
        assert built.fragments[0].origin == "stated"

    def test_duplicates_across_sources_collapse(self, db, world):
        built = db.build(
            "What do you remember about this project?",
            project="primnox",
            searcher=lambda q: ["This project uses npm"],
            now=NOW,
        )
        texts = [f.text for f in built.fragments]
        assert len([t for t in texts if "uses npm" in t]) == 1

    def test_the_budget_is_respected_and_the_remainder_counted(self, db):
        # Deliberately unrelated statements: near-identical ones would be
        # treated as corrections of each other by the fact store.
        subjects = [
            "the retrieval router lives in v2/router.py",
            "the vault is unlocked from the OS keychain",
            "meetings are recorded to Documents/Primnox",
            "the dashboard polls every thirty seconds",
            "PII scrubbing happens before any cloud call",
            "the island overlay is optional",
            "backups are written as encrypted .prx files",
            "calendar sync supports CalDAV",
        ]
        for subject in subjects:
            wm.record_fact(subject, project="p")
        built = db.build("What do you remember about p?", project="p", budget_tokens=20, now=NOW)
        assert built.tokens <= 40
        assert built.dropped > 0
        assert "omitted" in built.render()

    def test_at_least_one_fragment_survives_a_tiny_budget(self, db):
        wm.record_fact("a very long fact " * 50, project="p")
        built = db.build("What do you remember about p?", project="p", budget_tokens=5, now=NOW)
        assert len(built.fragments) == 1

    def test_rendering_groups_by_source(self, db, world):
        built = db.build("Continue what I was doing.", project="primnox", now=NOW)
        assert "── task_state ──" in built.render()


class TestQuestionAnalysis:
    def test_filenames_are_extracted(self):
        assert "backend/router.py" in context.extract_targets("what imports backend/router.py?")["files"]

    def test_called_symbols_are_extracted(self):
        assert "authenticate" in context.extract_targets("what calls authenticate()?")["symbols"]

    def test_backticked_names_are_treated_as_explicit(self):
        assert "unlock_vault" in context.extract_targets("who calls `unlock_vault`?")["explicit"]

    def test_english_words_are_not_mistaken_for_identifiers(self):
        identifiers = context.extract_targets("what could break if this changes?")["identifiers"]
        assert identifiers == []

    def test_yesterday_resolves_to_a_local_day(self):
        window = context.temporal_window("what was I doing yesterday?", now=NOW)
        assert window == episodes.local_day_bounds(1, now=NOW)

    def test_this_week_resolves_to_a_range(self):
        start, end = context.temporal_window("what have I been doing lately?", now=NOW)
        assert start < end

    def test_a_question_with_no_time_reference_has_no_window(self):
        assert context.temporal_window("what calls authenticate()?", now=NOW) is None
