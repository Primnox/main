"""Tests for Graphify.

Two failure modes drive these tests. The first is the one found in testing:
a graph used for questions that needed lexical precision, and a corpus full
of vendored and generated files that buried the real answers. The second is
a stale index answering confidently from code that no longer exists.
"""

import pytest

from v2 import graphify, store


@pytest.fixture
def db(tmp_path):
    store.reset_for_tests(tmp_path / "v2.db")
    yield graphify
    store.reset_for_tests(None)


@pytest.fixture
def repo(tmp_path):
    """A small but realistic tree: a package, an importer, a test, and a
    pile of material that should never be indexed."""
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "dist").mkdir()

    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "vault.py").write_text(
        "import hashlib\n"
        "\n"
        "\n"
        "def derive_key(passphrase):\n"
        "    return hashlib.sha256(passphrase.encode()).digest()\n"
        "\n"
        "\n"
        "class Vault:\n"
        "    def unlock(self, passphrase):\n"
        "        return derive_key(passphrase)\n"
    )
    (root / "app" / "auth.py").write_text(
        "from app.vault import derive_key\n"
        "\n"
        "\n"
        "def authenticate(user, passphrase):\n"
        "    return derive_key(passphrase)\n"
        "\n"
        "\n"
        "def login(user, passphrase):\n"
        "    return authenticate(user, passphrase)\n"
        "\n"
        "\n"
        "def refresh_session(user, passphrase):\n"
        "    return authenticate(user, passphrase)\n"
    )
    (root / "tests" / "test_auth.py").write_text(
        "from app.auth import authenticate\n"
        "\n"
        "\n"
        "def test_authenticate():\n"
        "    assert authenticate('u', 'p')\n"
    )
    # Corpus pollution: a dependency, a build artefact, a minified bundle
    # and a generated stub — none of which anyone wrote.
    (root / "node_modules" / "left-pad" / "index.js").write_text("function authenticate(){}\n")
    (root / "dist" / "app.js").write_text("function authenticate(){}\n")
    (root / "app" / "bundle.min.js").write_text("function authenticate(){}\n")
    (root / "app" / "schema_pb2.py").write_text("def authenticate():\n    pass\n")
    (root / "app" / "huge.js").write_text("var x = 1;" * 5000)
    return root


class TestCorpusFiltering:
    def test_dependencies_and_build_output_are_not_indexed(self, db, repo):
        db.index(repo, project="demo")
        paths = {row["rel_path"] for row in db.search_symbols("authenticate", project="demo")}
        assert not any(p.startswith(("node_modules/", "dist/")) for p in paths)

    def test_minified_and_generated_files_are_skipped(self, db, repo):
        db.index(repo, project="demo")
        indexed = {s["rel_path"] for s in db.search_symbols("", project="demo", limit=500)}
        assert "app/bundle.min.js" not in indexed
        assert "app/schema_pb2.py" not in indexed

    def test_a_long_line_marks_a_file_as_generated_whatever_its_name(self, db, repo):
        """A bundle that dodges the glob rules still has no newlines."""
        db.index(repo, project="demo")
        assert "app/huge.js" not in {p.relative_to(repo).as_posix() for p in db.walk_corpus(repo)}
        assert "app/huge.js" not in {s["rel_path"] for s in db.search_symbols("", project="demo", limit=500)}

    def test_gitignore_is_honoured(self, db, repo):
        (repo / ".gitignore").write_text("generated/\n")
        (repo / "generated").mkdir()
        (repo / "generated" / "models.py").write_text("def authenticate():\n    pass\n")
        db.index(repo, project="demo")
        assert not any(
            s["rel_path"].startswith("generated/")
            for s in db.search_symbols("authenticate", project="demo")
        )

    def test_the_corpus_can_be_inspected_without_building_an_index(self, db, repo):
        found = {p.name for p in db.walk_corpus(repo)}
        assert "vault.py" in found
        assert "index.js" not in found

    def test_extra_exclusions_can_be_supplied(self, db, repo):
        db.index(repo, project="demo", exclude_dirs={"tests"})
        assert not any(
            s["rel_path"].startswith("tests/")
            for s in db.search_symbols("test_authenticate", project="demo")
        )

    def test_indexing_a_non_directory_is_an_error(self, db, repo):
        with pytest.raises(Exception):
            db.index(repo / "app" / "vault.py", project="demo")


class TestStructuralQueries:
    def test_callers_answers_the_question_grep_cannot(self, db, repo):
        db.index(repo, project="demo")
        found = {c["caller"] for c in db.callers("authenticate", project="demo")}
        assert {"login", "refresh_session"} <= found

    def test_a_test_file_shows_up_as_a_caller(self, db, repo):
        db.index(repo, project="demo")
        assert any(c["rel_path"] == "tests/test_auth.py" for c in db.callers("authenticate", project="demo"))

    def test_callees_are_scoped_to_the_function(self, db, repo):
        db.index(repo, project="demo")
        targets = {c["target"] for c in db.callees("login", project="demo")}
        assert targets == {"authenticate"}

    def test_methods_are_addressable_by_qualified_name(self, db, repo):
        db.index(repo, project="demo")
        targets = {c["target"] for c in db.callees("Vault.unlock", project="demo")}
        assert "derive_key" in targets

    def test_dependents_finds_what_imports_a_module(self, db, repo):
        db.index(repo, project="demo")
        importers = {d["rel_path"] for d in db.dependents("app/vault.py", project="demo")}
        assert importers == {"app/auth.py"}

    def test_dependencies_separates_internal_from_external(self, db, repo):
        db.index(repo, project="demo")
        deps = {d["module"]: d["internal"] for d in db.dependencies("app/vault.py", project="demo")}
        assert deps["hashlib"] is False

    def test_definitions_report_where_a_symbol_lives(self, db, repo):
        db.index(repo, project="demo")
        [definition] = db.definitions("derive_key", project="demo")
        assert definition["rel_path"] == "app/vault.py"
        assert definition["kind"] == "function"

    def test_symbols_in_a_file_are_returned_in_source_order(self, db, repo):
        db.index(repo, project="demo")
        names = [s["name"] for s in db.symbols_in("app/auth.py", project="demo")]
        assert names == ["authenticate", "login", "refresh_session"]

    def test_projects_are_isolated(self, db, repo):
        db.index(repo, project="demo")
        assert db.callers("authenticate", project="other") == []


class TestImpact:
    def test_impact_reaches_transitively(self, db, repo):
        db.index(repo, project="demo")
        result = db.impact("app/vault.py", project="demo", depth=2)
        reached = {d["rel_path"] for d in result["dependents"]}
        assert "app/auth.py" in reached
        assert "tests/test_auth.py" in reached

    def test_distance_records_how_far_the_effect_travelled(self, db, repo):
        db.index(repo, project="demo")
        result = db.impact("app/vault.py", project="demo", depth=2)
        by_path = {d["rel_path"]: d["distance"] for d in result["dependents"]}
        assert by_path["app/auth.py"] == 1
        assert by_path["tests/test_auth.py"] == 2

    def test_depth_bounds_the_closure(self, db, repo):
        db.index(repo, project="demo")
        result = db.impact("app/vault.py", project="demo", depth=1)
        assert {d["rel_path"] for d in result["dependents"]} == {"app/auth.py"}

    def test_affected_tests_are_called_out(self, db, repo):
        db.index(repo, project="demo")
        assert "tests/test_auth.py" in db.impact("app/vault.py", project="demo")["tests"]

    def test_impact_on_a_symbol_includes_its_callers(self, db, repo):
        db.index(repo, project="demo")
        result = db.impact("authenticate", project="demo")
        assert {c["caller"] for c in result["callers"]} >= {"login", "refresh_session"}

    def test_impact_is_labelled_as_an_inference(self, db, repo):
        """Reachability is evidence that something could break, not a claim
        that it will."""
        db.index(repo, project="demo")
        assert db.impact("app/vault.py", project="demo")["origin"] == "inferred"


class TestFreshness:
    def test_a_fresh_index_is_healthy(self, db, repo):
        db.index(repo, project="demo")
        assert db.health(repo, project="demo")["healthy"] is True

    def test_an_edited_file_is_detected(self, db, repo):
        db.index(repo, project="demo")
        (repo / "app" / "auth.py").write_text("def authenticate():\n    return None\n")
        status = db.health(repo, project="demo")
        assert status["healthy"] is False
        assert "app/auth.py" in status["changed"]

    def test_a_deleted_file_is_detected(self, db, repo):
        db.index(repo, project="demo")
        (repo / "app" / "auth.py").unlink()
        assert "app/auth.py" in db.health(repo, project="demo")["missing"]

    def test_a_new_file_is_detected(self, db, repo):
        db.index(repo, project="demo")
        (repo / "app" / "router.py").write_text("def route():\n    pass\n")
        assert "app/router.py" in db.health(repo, project="demo")["new"]

    def test_query_results_are_flagged_when_their_file_moved_on(self, db, repo):
        """Never confidently return obsolete graph data."""
        db.index(repo, project="demo")
        (repo / "app" / "auth.py").write_text("# rewritten\n")
        assert all(c["stale"] for c in db.callers("authenticate", project="demo")
                   if c["rel_path"] == "app/auth.py")

    def test_refresh_reindexes_only_what_changed(self, db, repo):
        db.index(repo, project="demo")
        (repo / "app" / "auth.py").write_text(
            "from app.vault import derive_key\n"
            "\n"
            "\n"
            "def authenticate(user, passphrase):\n"
            "    return derive_key(passphrase)\n"
        )
        report = db.refresh(repo, project="demo")
        assert report["reindexed"] == 1
        assert report["healthy"] is True
        assert {c["caller"] for c in db.callers("authenticate", project="demo")} == {"test_authenticate"}

    def test_refresh_drops_symbols_from_deleted_files(self, db, repo):
        db.index(repo, project="demo")
        (repo / "app" / "auth.py").unlink()
        report = db.refresh(repo, project="demo")
        assert report["removed"] == 1
        assert db.definitions("login", project="demo") == []

    def test_refresh_picks_up_new_files(self, db, repo):
        db.index(repo, project="demo")
        (repo / "app" / "router.py").write_text("from app.auth import login\n\n\ndef route():\n    return login\n")
        db.refresh(repo, project="demo")
        assert {d["rel_path"] for d in db.dependents("app/auth.py", project="demo")} >= {"app/router.py"}

    def test_refresh_on_a_healthy_index_does_nothing(self, db, repo):
        db.index(repo, project="demo")
        assert db.refresh(repo, project="demo")["reindexed"] == 0


class TestLanguagesAndConfidence:
    def test_python_edges_are_exact(self, db, repo):
        db.index(repo, project="demo")
        assert all(c["confidence"] == graphify.CONFIDENCE_AST for c in db.callers("authenticate", project="demo"))

    def test_typescript_is_indexed_at_lower_confidence(self, db, repo):
        (repo / "app" / "ui.ts").write_text(
            "import { authenticate } from './auth';\n"
            "\n"
            "export function signIn(user: string) {\n"
            "  return authenticate(user);\n"
            "}\n"
        )
        db.index(repo, project="demo")
        ts_callers = [c for c in db.callers("authenticate", project="demo") if c["rel_path"] == "app/ui.ts"]
        assert ts_callers and ts_callers[0]["confidence"] == graphify.CONFIDENCE_REGEX

    def test_arrow_functions_are_found(self, db, repo):
        (repo / "app" / "ui.ts").write_text("export const signIn = (user: string) => authenticate(user);\n")
        db.index(repo, project="demo")
        assert [s["name"] for s in db.symbols_in("app/ui.ts", project="demo")] == ["signIn"]

    def test_a_file_that_does_not_parse_is_reported_not_half_indexed(self, db, repo):
        (repo / "app" / "broken.py").write_text("def oops(:\n    pass\n")
        report = db.index(repo, project="demo")
        assert any(e["file"] == "app/broken.py" for e in report["errors"])
        assert db.symbols_in("app/broken.py", project="demo") == []


class TestResolutionHonesty:
    def test_an_ambiguous_name_stays_unresolved_rather_than_guessed(self, db, repo):
        """Two functions named `run` must not make one of them the answer to
        every call of that name."""
        (repo / "app" / "a.py").write_text("def run():\n    pass\n")
        (repo / "app" / "b.py").write_text("def run():\n    pass\n")
        (repo / "app" / "c.py").write_text("from app.a import run\n\n\ndef go():\n    return run()\n")
        db.index(repo, project="demo")
        rows = store.connect().execute(
            "SELECT target_symbol FROM code_edges WHERE kind='calls' AND target_name='run'"
        ).fetchall()
        assert all(r["target_symbol"] is None for r in rows)
        # Still answerable by name, which is the honest fallback.
        assert db.callers("run", project="demo")


class TestWorldModelLinking:
    def test_linking_is_off_by_default(self, db, repo):
        from v2 import world_model

        db.index(repo, project="demo")
        assert world_model.find_entities(type_="file", project="demo") == []

    def test_linked_files_become_world_model_entities(self, db, repo):
        from v2 import world_model

        db.index(repo, project="demo", link_world_model=True)
        files = {e["key"] for e in world_model.find_entities(type_="file", project="demo", limit=100)}
        assert "app/vault.py" in files

    def test_graph_and_world_model_agree_on_identity(self, db, repo):
        from v2 import world_model

        db.index(repo, project="demo", link_world_model=True)
        entity = world_model.find_entities(type_="file", project="demo", key="app/vault.py")[0]
        row = store.connect().execute(
            "SELECT id FROM code_files WHERE rel_path = ?", ("app/vault.py",)
        ).fetchone()
        assert entity["id"] == row["id"]


class TestMaintenance:
    def test_stats_describe_the_index(self, db, repo):
        db.index(repo, project="demo")
        totals = db.stats(project="demo")
        assert totals["files"]["python"] >= 4
        assert totals["edges"]["calls"] > 0

    def test_purging_a_project_clears_its_index(self, db, repo):
        db.index(repo, project="demo")
        report = db.purge_project("demo")
        assert report["files_deleted"] > 0
        assert db.callers("authenticate", project="demo") == []
