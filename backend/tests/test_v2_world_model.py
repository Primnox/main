"""Tests for the world model: entities, relationships and durable facts.

The behaviours pinned here are the ones the architecture calls out as
non-negotiable — an update must not destroy historical truth, an inference
must not silently outrank something the user said, and "why do you remember
that?" must be answerable from recorded provenance rather than reconstructed.
"""

import pytest

from v2 import store, world_model as wm


@pytest.fixture
def db(tmp_path):
    store.reset_for_tests(tmp_path / "v2.db")
    yield wm
    store.reset_for_tests(None)


class TestEntities:
    def test_same_entity_observed_twice_is_one_row(self, db):
        first = db.upsert_entity("file", "backend/router.py", project="primnox")
        second = db.upsert_entity("file", "backend/router.py", project="primnox")
        assert first["id"] == second["id"]
        assert len(db.find_entities(type_="file")) == 1

    def test_same_key_in_different_projects_is_different_entities(self, db):
        a = db.upsert_entity("file", "src/main.py", project="alpha")
        b = db.upsert_entity("file", "src/main.py", project="beta")
        assert a["id"] != b["id"]

    def test_attributes_merge_rather_than_replace(self, db):
        db.upsert_entity("file", "a.py", attributes={"lines": 10, "lang": "python"})
        updated = db.upsert_entity("file", "a.py", attributes={"lines": 12})
        assert updated["attributes"] == {"lines": 12, "lang": "python"}

    def test_reobservation_records_confirmation(self, db):
        created = db.upsert_entity("file", "a.py", observed_at="2026-08-01T00:00:00+00:00")
        again = db.upsert_entity("file", "a.py", observed_at="2026-08-02T00:00:00+00:00")
        assert again["last_confirmed"] > created["last_confirmed"]

    def test_stronger_evidence_upgrades_provenance(self, db):
        """A file first guessed from a window title and later actually read
        should end up recorded as observed, not left as an inference."""
        db.upsert_entity("file", "a.py", prov=wm.MODEL_INFERRED)
        upgraded = db.upsert_entity("file", "a.py", prov=wm.provenance(source="file", origin="observed"))
        assert upgraded["origin"] == "observed"

    def test_weaker_evidence_does_not_downgrade_provenance(self, db):
        db.upsert_entity("file", "a.py", prov=wm.provenance(source="file", origin="observed"))
        later = db.upsert_entity("file", "a.py", prov=wm.MODEL_INFERRED)
        assert later["origin"] == "observed"

    def test_expiry_preserves_the_record(self, db):
        created = db.upsert_entity("file", "gone.py")
        assert db.expire_entity(created["id"])
        assert db.find_entities(type_="file") == []
        assert len(db.find_entities(type_="file", include_expired=True)) == 1

    def test_seeing_an_expired_entity_again_revives_it(self, db):
        created = db.upsert_entity("file", "gone.py")
        db.expire_entity(created["id"])
        db.upsert_entity("file", "gone.py")
        assert len(db.find_entities(type_="file")) == 1

    def test_unknown_type_is_rejected(self, db):
        with pytest.raises(wm.ValidationError):
            db.upsert_entity("spaceship", "x")

    def test_project_scope_resolves_from_name_or_id(self, db):
        project = db.upsert_entity("project", "primnox")
        from_name = db.entity_id("file", "a.py", "primnox")
        from_id = db.entity_id("file", "a.py", project["id"])
        assert from_name == from_id


class TestRelationships:
    def test_repeated_assertion_is_idempotent(self, db):
        a = db.upsert_entity("project", "primnox")
        b = db.upsert_entity("file", "a.py", project="primnox")
        db.relate(a["id"], "contains", b["id"])
        db.relate(a["id"], "contains", b["id"])
        assert len(db.relations(a["id"])) == 1

    def test_direction_is_respected(self, db):
        a = db.upsert_entity("project", "primnox")
        b = db.upsert_entity("file", "a.py", project="primnox")
        db.relate(a["id"], "contains", b["id"])
        assert db.relations(a["id"], direction="out")
        assert db.relations(a["id"], direction="in") == []
        assert db.relations(b["id"], direction="in")

    def test_neighbors_returns_entities_with_the_edge_that_found_them(self, db):
        a = db.upsert_entity("project", "primnox")
        b = db.upsert_entity("file", "a.py", project="primnox")
        db.relate(a["id"], "contains", b["id"])
        [found] = db.neighbors(a["id"], rel="contains")
        assert found["key"] == "a.py" and found["via"] == "contains"

    def test_edges_to_unknown_entities_are_skipped_not_returned_as_holes(self, db):
        a = db.upsert_entity("project", "primnox")
        db.relate(a["id"], "contains", "ent_0000000000000000")
        assert db.neighbors(a["id"]) == []

    def test_retraction_closes_the_edge_but_keeps_history(self, db):
        a = db.upsert_entity("project", "primnox")
        b = db.upsert_entity("file", "a.py", project="primnox")
        db.relate(a["id"], "contains", b["id"])
        assert db.unrelate(a["id"], "contains", b["id"])
        assert db.relations(a["id"]) == []
        assert db.relations(a["id"], include_expired=True)

    def test_unknown_relationship_is_rejected(self, db):
        a = db.upsert_entity("project", "primnox")
        with pytest.raises(wm.ValidationError):
            db.relate(a["id"], "vibes_with", a["id"])

    def test_deleting_an_entity_removes_its_edges(self, db):
        a = db.upsert_entity("project", "primnox")
        b = db.upsert_entity("file", "a.py", project="primnox")
        db.relate(a["id"], "contains", b["id"])
        db.delete_entity(b["id"])
        assert db.relations(a["id"], include_expired=True) == []


class TestFacts:
    def test_a_stated_fact_is_scoped_to_its_project(self, db):
        db.record_fact("uses pnpm", project="alpha", slot="package_manager")
        assert db.current_facts(project="alpha")
        assert db.current_facts(project="beta") == []

    def test_a_new_statement_supersedes_the_old_one_in_the_same_slot(self, db):
        old = db.record_fact("uses pnpm", project="alpha", slot="package_manager")
        new = db.record_fact("uses npm", project="alpha", slot="package_manager")
        assert new["superseded"] == [old["id"]]
        assert [f["text"] for f in db.current_facts(project="alpha")] == ["uses npm"]

    def test_superseding_preserves_the_historical_record(self, db):
        old = db.record_fact("uses pnpm", project="alpha", slot="package_manager")
        db.record_fact("uses npm", project="alpha", slot="package_manager")
        assert db.get_fact(old["id"]) is not None
        assert db.explain(old["id"])["status"] == "superseded"
        assert len(db.history(project="alpha", slot="package_manager")) == 2

    def test_an_inference_cannot_overwrite_something_the_user_stated(self, db):
        stated = db.record_fact(
            "prefers the local model", project="alpha", slot="model_pref", prov=wm.USER_STATED
        )
        guess = db.record_fact(
            "prefers the cloud model", project="alpha", slot="model_pref", prov=wm.MODEL_INFERRED
        )
        assert guess["superseded"] == []
        assert guess["disputed"] == [stated["id"]]
        assert db.get_fact(stated["id"])["valid_until"] is None

    def test_weak_conflicts_preserve_uncertainty_instead_of_inventing_a_winner(self, db):
        first = db.record_fact("deploys on Friday", project="alpha", slot="deploy_day", prov=wm.MODEL_INFERRED)
        second = db.record_fact("deploys on Monday", project="alpha", slot="deploy_day", prov=wm.MODEL_INFERRED)
        # Same origin and confidence: the newer one wins on recency, but the
        # older belief is retained rather than deleted.
        assert second["superseded"] == [first["id"]]
        assert db.get_fact(first["id"]) is not None

    def test_explicit_correction_always_wins(self, db):
        stated = db.record_fact("uses pnpm", project="alpha", slot="package_manager", prov=wm.USER_STATED)
        correction = db.record_fact(
            "uses npm", project="alpha", slot="package_manager",
            prov=wm.MODEL_INFERRED, on_conflict="supersede",
        )
        assert correction["superseded"] == [stated["id"]]

    def test_keep_mode_reports_conflicts_without_acting(self, db):
        old = db.record_fact("uses pnpm", project="alpha", slot="package_manager")
        new = db.record_fact("uses npm", project="alpha", slot="package_manager", on_conflict="keep")
        assert new["disputed"] == [old["id"]]
        assert db.get_fact(old["id"])["valid_until"] is None

    def test_restating_the_same_fact_confirms_it_rather_than_duplicating(self, db):
        first = db.record_fact("uses pnpm", project="alpha", slot="package_manager")
        again = db.record_fact("uses pnpm", project="alpha", slot="package_manager")
        assert again["id"] == first["id"]
        assert again["reconfirmed"] is True
        assert len(db.history(project="alpha")) == 1

    def test_near_duplicate_text_conflicts_even_without_a_slot(self, db):
        old = db.record_fact("the build script lives in scripts/build.sh", project="alpha")
        new = db.record_fact("the build script lives in scripts/build.zsh", project="alpha")
        assert new["superseded"] == [old["id"]]

    def test_unrelated_facts_in_one_scope_do_not_conflict(self, db):
        db.record_fact("uses pnpm", project="alpha")
        db.record_fact("the API listens on port 4009", project="alpha")
        assert len(db.current_facts(project="alpha")) == 2

    def test_empty_text_is_rejected(self, db):
        with pytest.raises(wm.ValidationError):
            db.record_fact("   ", project="alpha")

    def test_procedural_and_semantic_memory_are_separable(self, db):
        db.record_fact("uses pnpm", project="alpha", kind="semantic")
        db.record_fact("release: run scripts/release.sh then tag", project="alpha", kind="procedural")
        assert len(db.current_facts(project="alpha", kind="procedural")) == 1


class TestStaleness:
    def test_stale_is_not_erased(self, db):
        fact = db.record_fact("uses pnpm", project="alpha")
        assert db.mark_stale(fact["id"], reason="repo now has package-lock.json")
        [current] = db.current_facts(project="alpha")
        assert current["stale"] is True
        assert db.explain(fact["id"])["stale_reason"] == "repo now has package-lock.json"

    def test_fresh_facts_rank_above_stale_ones(self, db):
        stale = db.record_fact("uses pnpm", project="alpha")
        db.mark_stale(stale["id"])
        db.record_fact("the API listens on port 4009", project="alpha")
        assert db.current_facts(project="alpha")[0]["stale"] is False


class TestForgetting:
    def test_forget_retracts_but_keeps_history_by_default(self, db):
        fact = db.record_fact("uses pnpm", project="alpha")
        assert db.forget(fact["id"])
        assert db.current_facts(project="alpha") == []
        assert db.get_fact(fact["id"]) is not None
        assert db.explain(fact["id"])["status"] == "retracted"

    def test_hard_delete_removes_the_row(self, db):
        fact = db.record_fact("uses pnpm", project="alpha")
        assert db.forget(fact["id"], mode="delete")
        assert db.get_fact(fact["id"]) is None

    def test_purging_a_project_covers_entities_edges_and_facts(self, db):
        project = db.upsert_entity("project", "alpha")
        file_entity = db.upsert_entity("file", "a.py", project="alpha")
        db.relate(project["id"], "contains", file_entity["id"])
        db.record_fact("uses pnpm", project="alpha")
        db.upsert_entity("project", "beta")
        db.record_fact("uses yarn", project="beta")

        report = db.purge_project("alpha")

        assert report["facts_deleted"] == 1
        assert report["relationships_deleted"] == 1
        assert report["entities_deleted"] == 2
        assert db.current_facts(project="alpha") == []
        assert db.find_entities(project="alpha") == []
        # The neighbouring project is untouched.
        assert len(db.current_facts(project="beta")) == 1


class TestSearchAndProvenance:
    def test_search_finds_facts_by_word(self, db):
        db.record_fact("the retrieval router lives in v2/router.py", project="alpha")
        assert db.search_facts("router", project="alpha")

    def test_search_handles_punctuated_terms(self, db):
        """V1 stripped punctuation before matching, which turned `router.py`
        into `routerpy` and silently lost the term."""
        db.record_fact("the entry point is backend/server.py", project="alpha")
        assert db.search_facts("server.py", project="alpha")

    def test_search_excludes_superseded_facts_by_default(self, db):
        db.record_fact("uses pnpm", project="alpha", slot="pm")
        db.record_fact("uses npm", project="alpha", slot="pm")
        assert [f["text"] for f in db.search_facts("uses", project="alpha")] == ["uses npm"]
        assert len(db.search_facts("uses", project="alpha", include_superseded=True)) == 2

    def test_secrets_are_withheld_unless_explicitly_requested(self, db):
        db.record_fact("the deploy token is in the vault", project="alpha", sensitivity="secret")
        assert db.search_facts("token", project="alpha") == []
        assert db.current_facts(project="alpha") == []
        assert db.current_facts(project="alpha", include_sensitive=True)

    def test_explain_reports_recorded_evidence_only(self, db):
        fact = db.record_fact(
            "uses pnpm", project="alpha",
            prov=wm.provenance(source="file", source_ref="res_abc123", origin="observed", confidence=0.7),
        )
        explained = db.explain(fact["id"])
        assert explained["source"] == "file"
        assert explained["source_ref"] == "res_abc123"
        assert explained["origin"] == "observed"
        assert explained["confidence"] == 0.7
        assert explained["status"] == "current"

    def test_explain_links_the_supersession_chain(self, db):
        old = db.record_fact("uses pnpm", project="alpha", slot="pm")
        new = db.record_fact("uses npm", project="alpha", slot="pm")
        assert db.explain(old["id"])["superseded_by"] == new["id"]
        assert db.explain(new["id"])["supersedes"] == [old["id"]]

    def test_explain_on_an_unknown_id_returns_none(self, db):
        assert db.explain("mem_0000000000000000") is None

    def test_recall_is_counted(self, db):
        db.record_fact("the API listens on port 4009", project="alpha")
        db.search_facts("port", project="alpha")
        db.search_facts("port", project="alpha")
        assert db.current_facts(project="alpha")[0]["access_count"] == 2


class TestEvidenceStrength:
    def test_stated_outranks_observed_outranks_inferred(self):
        stated = {"origin": "stated", "confidence": 0.5, "observed_at": "2026-01-01"}
        observed = {"origin": "observed", "confidence": 0.9, "observed_at": "2026-06-01"}
        inferred = {"origin": "inferred", "confidence": 1.0, "observed_at": "2026-12-01"}
        assert wm.strength(stated) > wm.strength(observed) > wm.strength(inferred)

    def test_recency_breaks_ties_within_an_origin(self):
        older = {"origin": "observed", "confidence": 0.8, "observed_at": "2026-01-01"}
        newer = {"origin": "observed", "confidence": 0.8, "observed_at": "2026-02-01"}
        assert wm.is_stronger(newer, older)
        assert not wm.is_stronger(older, newer)

    def test_a_newer_guess_does_not_beat_an_older_statement(self):
        stated = {"origin": "stated", "confidence": 0.95, "observed_at": "2026-01-01"}
        guess = {"origin": "inferred", "confidence": 0.99, "observed_at": "2026-12-01"}
        assert not wm.is_stronger(guess, stated)


class TestProvenanceValidation:
    def test_unknown_source_is_rejected(self):
        with pytest.raises(wm.ValidationError):
            wm.provenance(source="telepathy")

    def test_unknown_origin_is_rejected(self):
        with pytest.raises(wm.ValidationError):
            wm.provenance(origin="vibes")

    def test_confidence_defaults_follow_origin(self):
        assert wm.provenance(origin="stated").confidence > wm.provenance(origin="inferred").confidence

    def test_out_of_range_confidence_is_rejected(self):
        with pytest.raises(wm.ValidationError):
            wm.provenance(confidence=1.5)
