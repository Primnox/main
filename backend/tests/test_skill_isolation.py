"""Isolation between skills, and between one skill invocation and the next.

Three separate boundaries, each with its own way of leaking:

  1. IMPORT isolation — a skill that isn't going to run must not be imported.
     Asserted through `sys.modules`, mirroring
     test_skill_lazy_loading.py::test_list_skills_does_not_import_code_skill_module.
  2. PROMPT isolation — a skill used once must not leave its SKILL.md
     instructions in the prompt built for a later, unrelated request. This is
     the one that actually changes model behaviour if it breaks: a stray
     "always output a .pptx" from a previous turn silently corrupts the next.
  3. WORKSPACE isolation — two skills running concurrently must not share a
     directory, or a deck and a spreadsheet overwrite each other's files
     mid-build.

Nothing here touches a real provider or a real sandbox: brain.think,
code_exec.run_* and runtime_capabilities.detect are all mocked at the
black-box boundary.
"""
import sys
import threading
from pathlib import Path

import pytest

import brain
import code_exec
import runtime_capabilities
from skills import skill_router
from skills.adapted_skill import (
    AdaptedClaudeSkill, ParsedSkill, make_adapted_skill_class,
)
from skills.base_skill import SkillContext
from skills.skill_router import (
    _SkillMeta, _extract_skill_meta, _resolve_skill_class,
    get_skill_for_extension, list_skills,
)

SKILLS_DIR = Path(skill_router.__file__).parent

# Every *_skill.py that discovery registers lazily. Island skills (calendar)
# are excluded on purpose — they are imported eagerly at boot by design.
LAZY_SKILL_MODULES = (
    "skills.code_skill",
    "skills.transcript_skill",
    "skills.daily_brief_skill",
    "skills.meeting_summary_skill",
    "skills.screenshot_skill",
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def stub_capabilities(monkeypatch):
    """_execution_contract() probes the sandbox for real — two sandboxed
    executions — the first time it's called in a process. Every test in this
    file builds prompts, so without this the file would be minutes slow and
    would depend on whether Node happens to work on this machine."""
    monkeypatch.setattr(
        runtime_capabilities, "detect",
        lambda force=False: runtime_capabilities.Capabilities(
            sandbox=True, python=True, node=False,
            libraries={"python-pptx": True, "reportlab": True}, node_modules={},
        ),
    )


@pytest.fixture
def isolated_workspaces(monkeypatch, tmp_path):
    """Redirect workspace_path() away from the user's real
    Documents\\Primnox\\CodeExecution — skills stage their whole package into
    it, so an unpatched test writes fixture skills into live user data."""
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(code_exec, "workspace_path", lambda wid: _mkdir(root / wid))
    return root


def _mkdir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def fresh_lazy_registry():
    """Put the registries back into their just-booted state — genuinely lazy
    `_SkillMeta` stubs — and evict the skill modules from `sys.modules`.

    Needed because `_resolve_skill_class()` caches the imported class back
    into the registry on first use, so by the time this file runs, an earlier
    test may already have turned the stubs into classes and "was it
    imported?" would be unanswerable. Everything is restored afterwards,
    including the original module objects, so class identity stays stable for
    every other test file.
    """
    saved_modules = {n: sys.modules.pop(n) for n in LAZY_SKILL_MODULES if n in sys.modules}
    saved_registry = dict(skill_router.SKILL_REGISTRY)
    saved_triggers = dict(skill_router.TRIGGER_MAP)

    for module_name in LAZY_SKILL_MODULES:
        stem = module_name.split(".", 1)[1]
        meta = _extract_skill_meta(SKILLS_DIR / f"{stem}.py", module_name)
        if meta is None or meta.is_island_skill:
            continue
        for ext in meta.supported_extensions:
            skill_router.SKILL_REGISTRY[ext.lower()] = meta
        for word in meta.trigger_words:
            skill_router.TRIGGER_MAP[word.lower()] = meta
    try:
        yield
    finally:
        skill_router.SKILL_REGISTRY.clear()
        skill_router.SKILL_REGISTRY.update(saved_registry)
        skill_router.TRIGGER_MAP.clear()
        skill_router.TRIGGER_MAP.update(saved_triggers)
        for name, module in saved_modules.items():
            sys.modules[name] = module


def _loaded_skill_modules() -> set:
    return {n for n in sys.modules if n in LAZY_SKILL_MODULES}


def _reply(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def _make_skill(folder: Path, name="Test Skill", body="Do the task.",
                description="does a thing"):
    """A SKILL.md-backed skill class built straight from a ParsedSkill —
    same shape make_adapted_skill_class() gets from real discovery."""
    folder.mkdir(parents=True, exist_ok=True)
    parsed = ParsedSkill(name=name, description=description, body=body)
    return make_adapted_skill_class(folder, parsed)()


# ── 4. Lazy loading ───────────────────────────────────────────────────────────

class TestUnrelatedQuestionsImportNothing:
    """A skill nobody invoked is a skill whose module — and whatever heavy
    third-party library it imports — should never have been loaded. This is
    the whole point of the `_SkillMeta` static-AST path."""

    def test_an_unrelated_question_imports_zero_skill_modules(
        self, fresh_lazy_registry, monkeypatch
    ):
        monkeypatch.setattr("skills.semantic_router.classify", lambda t: None)
        assert _loaded_skill_modules() == set()

        entry = skill_router.resolve_skill_for_message("What's the capital of Japan?")

        assert entry is None
        assert _loaded_skill_modules() == set(), (
            "a question that matches no skill still imported skill modules"
        )

    def test_routing_a_message_that_matches_nothing_imports_nothing(
        self, fresh_lazy_registry, monkeypatch
    ):
        monkeypatch.setattr("skills.semantic_router.classify", lambda t: None)
        result = skill_router.route_skill(user_message="What's the capital of Japan?")
        assert result["success"] is False
        assert _loaded_skill_modules() == set()

    def test_listing_every_skill_imports_none_of_them(self, fresh_lazy_registry):
        # The semantic router builds its catalog from list_skills() on EVERY
        # chat message, so if listing imported skills, laziness would buy
        # nothing at all in practice.
        names = {s["name"] for s in list_skills()}
        assert "code_analyst" in names
        assert _loaded_skill_modules() == set()

    def test_matching_a_trigger_word_still_imports_nothing_until_it_runs(
        self, fresh_lazy_registry, monkeypatch
    ):
        # Resolution and execution are separate: knowing WHICH skill matches
        # is metadata-only work.
        monkeypatch.setattr("skills.semantic_router.classify", lambda t: None)
        entry = skill_router.resolve_skill_for_message("explain this code")
        assert isinstance(entry, _SkillMeta)
        assert _loaded_skill_modules() == set()


class TestOnlyTheInvokedSkillIsImported:
    def test_resolving_the_code_skill_imports_exactly_one_module(self, fresh_lazy_registry):
        before = set(sys.modules)
        resolved = _resolve_skill_class(get_skill_for_extension("py"))

        assert resolved is not None
        newly_loaded_skills = (set(sys.modules) - before) & set(LAZY_SKILL_MODULES)
        assert newly_loaded_skills == {"skills.code_skill"}

    def test_a_pdf_request_does_not_drag_in_the_other_skills(self, fresh_lazy_registry):
        # The pdf/pptx/docx/xlsx skills are SKILL.md packages — real classes
        # built at discovery with no module to import — so a document request
        # should load nothing at all.
        entry = get_skill_for_extension("pdf")
        assert entry.name.lower() == "pdf"

        _resolve_skill_class(entry)

        assert _loaded_skill_modules() == set()

    def test_resolving_one_skill_leaves_the_others_lazy(self, fresh_lazy_registry):
        _resolve_skill_class(get_skill_for_extension("py"))

        assert _loaded_skill_modules() == {"skills.code_skill"}
        assert isinstance(get_skill_for_extension("srt"), _SkillMeta)


# ── 5/6. Persistence + unloading between turns ────────────────────────────────

class TestSkillInstructionsDoNotLeakAcrossRequests:
    """A skill's SKILL.md body is pasted verbatim into the prompt it runs
    with. If any of it survives into the NEXT, unrelated request, the model
    silently follows instructions the user never invoked — the failure is
    invisible in the transcript and looks like the model "going off script".

    Structurally this holds because `_parsed` is class-level per skill and
    `_build_prompt` rebuilds from scratch every call. These pin that down,
    because the obvious "optimisation" (cache the assembled prompt, or hang
    it off a module global) would break it silently.
    """

    MARKER_A = "ZZ_MARKER_ALWAYS_END_EVERY_ANSWER_WITH_ARRR"
    MARKER_B = "ZZ_MARKER_NEVER_MENTION_PIRATES"

    def _capture(self, monkeypatch):
        prompts = []
        monkeypatch.setattr(
            brain, "think",
            lambda prompt, *a, **kw: (prompts.append(prompt), _reply("done"))[1],
        )
        return prompts

    def test_a_second_skill_does_not_inherit_the_first_skills_body(
        self, monkeypatch, tmp_path, isolated_workspaces
    ):
        prompts = self._capture(monkeypatch)
        skill_a = _make_skill(tmp_path / "a", name="Skill A", body=self.MARKER_A)
        skill_b = _make_skill(tmp_path / "b", name="Skill B", body=self.MARKER_B)

        skill_a.run(SkillContext(user_message="first request", session_id="s1"))
        skill_b.run(SkillContext(user_message="second request", session_id="s1"))

        assert self.MARKER_A in prompts[0]
        assert self.MARKER_A not in prompts[1], "skill A's instructions leaked into skill B's turn"
        assert self.MARKER_B in prompts[1]

    def test_reusing_one_skill_does_not_replay_the_previous_user_request(
        self, monkeypatch, tmp_path, isolated_workspaces
    ):
        prompts = self._capture(monkeypatch)
        skill = _make_skill(tmp_path / "a", name="Skill A", body="body")

        skill.run(SkillContext(user_message="build the Q3 revenue deck", session_id="s1"))
        skill.run(SkillContext(user_message="what is 2 + 2", session_id="s1"))

        assert "Q3 revenue" in prompts[0]
        assert "Q3 revenue" not in prompts[1], "a previous turn's request survived into the next"

    def test_a_fresh_instance_of_the_same_class_starts_clean(
        self, monkeypatch, tmp_path, isolated_workspaces
    ):
        # route_skill() constructs a NEW instance per turn (skill_cls()), so
        # anything stashed on `self` during one run is gone by the next —
        # this asserts nothing has quietly migrated to the class.
        prompts = self._capture(monkeypatch)
        cls = make_adapted_skill_class(
            _mkdir(tmp_path / "a"),
            ParsedSkill(name="Skill A", description="d", body="body"),
        )

        cls().run(SkillContext(user_message="remember: the codeword is HALIBUT", session_id="s1"))
        cls().run(SkillContext(user_message="unrelated", session_id="s1"))

        assert "HALIBUT" not in prompts[1]

    def test_multi_step_follow_ups_never_re_paste_the_skill_body(
        self, monkeypatch, tmp_path, isolated_workspaces
    ):
        # The follow-up prompt is deliberately small (result + budget). If it
        # re-sent the body, a 10-step run would send ~60k chars ten times.
        prompts = []
        replies = iter([
            _reply("```python\nprint(1)\n```"),
            _reply("all done"),
        ])
        monkeypatch.setattr(
            brain, "think",
            lambda prompt, *a, **kw: (prompts.append(prompt), next(replies))[1],
        )
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: {
                "success": True, "stdout": "1", "stderr": "", "files_created": [],
            },
        )

        _make_skill(tmp_path / "a", body=self.MARKER_A).run(
            SkillContext(user_message="go", session_id="s1")
        )

        assert self.MARKER_A in prompts[0]
        assert self.MARKER_A not in prompts[1]

    def test_only_caller_supplied_history_carries_between_turns(
        self, monkeypatch, tmp_path, isolated_workspaces
    ):
        # Cross-turn context exists, but only via ctx.chat_history, which the
        # caller assembles explicitly. The skill never remembers on its own.
        prompts = self._capture(monkeypatch)
        skill = _make_skill(tmp_path / "a")

        skill.run(SkillContext(user_message="one", session_id="s1"))
        skill.run(SkillContext(
            user_message="two", session_id="s1",
            chat_history=[{"speaker": "User", "text": "one"}],
        ))

        assert "RECENT CONVERSATION" not in prompts[0]
        assert "RECENT CONVERSATION" in prompts[1]


class TestStagedFilesDoNotBleedBetweenSkills:
    def test_each_skill_stages_into_its_own_directory(
        self, monkeypatch, tmp_path, isolated_workspaces
    ):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _reply("done"))

        folder_a = _mkdir(tmp_path / "pkg_a")
        (folder_a / "secret_a.txt").write_text("A", encoding="utf-8")
        folder_b = _mkdir(tmp_path / "pkg_b")
        (folder_b / "secret_b.txt").write_text("B", encoding="utf-8")

        skill_a = make_adapted_skill_class(folder_a, ParsedSkill("Skill A", "d", "body"))()
        skill_b = make_adapted_skill_class(folder_b, ParsedSkill("Skill B", "d", "body"))()

        ctx = SkillContext(user_message="x", session_id="s1")
        skill_a.run(ctx)
        skill_b.run(ctx)

        ws_a = isolated_workspaces / skill_a._workspace_id(ctx) / "skill"
        ws_b = isolated_workspaces / skill_b._workspace_id(ctx) / "skill"
        assert (ws_a / "secret_a.txt").exists()
        assert not (ws_a / "secret_b.txt").exists()
        assert (ws_b / "secret_b.txt").exists()
        assert not (ws_b / "secret_a.txt").exists()

    def test_the_same_skill_in_two_sessions_gets_two_directories(self, tmp_path):
        skill = _make_skill(tmp_path / "a")
        a = skill._workspace_id(SkillContext(session_id="session-one"))
        b = skill._workspace_id(SkillContext(session_id="session-two"))
        assert a != b

    def test_a_missing_session_id_does_not_collapse_skills_together(self, tmp_path):
        # ctx.session_id defaults to "default" — two DIFFERENT skills with no
        # session must still not share a workspace.
        a = _make_skill(tmp_path / "a", name="Skill A")
        b = _make_skill(tmp_path / "b", name="Skill B")
        ctx = SkillContext(user_message="x")
        assert a._workspace_id(ctx) != b._workspace_id(ctx)


# ── 37. Concurrent skills ─────────────────────────────────────────────────────

class TestConcurrentSkillsDoNotCollide:
    """`_workspace_id` is (session, skill), not just session — a deck and a
    spreadsheet built in the same conversation must not inherit each other's
    half-finished files. These run the two skills genuinely in parallel, since
    a sequential test can't distinguish "scoped per skill" from "scoped per
    session and the second run happened to clean up"."""

    def test_two_skills_running_at_once_get_separate_workspaces(
        self, monkeypatch, tmp_path, isolated_workspaces
    ):
        skill_a = _make_skill(tmp_path / "a", name="Deck Skill")
        skill_b = _make_skill(tmp_path / "b", name="Sheet Skill")

        seen = []
        lock = threading.Lock()
        barrier = threading.Barrier(2, timeout=10)

        def fake_run_python(code, session_id="", workspace_id="", **kw):
            barrier.wait()  # both skills are inside execute() at the same moment
            with lock:
                seen.append((code.strip(), workspace_id))
            return {"success": True, "stdout": "", "stderr": "", "files_created": []}

        monkeypatch.setattr(code_exec, "run_python", fake_run_python)

        replies = {
            "Deck Skill": iter([_reply("```python\nprint('deck')\n```"), _reply("done")]),
            "Sheet Skill": iter([_reply("```python\nprint('sheet')\n```"), _reply("done")]),
        }
        state = threading.local()

        def fake_think(prompt, *a, **kw):
            return next(replies[state.name])

        monkeypatch.setattr(brain, "think", fake_think)

        errors = []

        def _worker(skill):
            state.name = skill.name
            try:
                skill.run(SkillContext(user_message="go", session_id="shared-session"))
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=_worker, args=(s,)) for s in (skill_a, skill_b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        assert errors == []
        assert len(seen) == 2
        workspaces = {ws for _, ws in seen}
        assert len(workspaces) == 2, f"concurrent skills shared a workspace: {seen}"
        # And each skill's own code landed in its own workspace, not the other's.
        by_code = dict(seen)
        assert by_code["print('deck')"] != by_code["print('sheet')"]

    def test_concurrent_workspaces_are_separate_directories_on_disk(
        self, monkeypatch, tmp_path, isolated_workspaces
    ):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _reply("done"))
        folder_a = _mkdir(tmp_path / "pkg_a")
        (folder_a / "a.txt").write_text("a", encoding="utf-8")
        folder_b = _mkdir(tmp_path / "pkg_b")
        (folder_b / "b.txt").write_text("b", encoding="utf-8")

        skills = [
            make_adapted_skill_class(folder_a, ParsedSkill("Skill A", "d", "body"))(),
            make_adapted_skill_class(folder_b, ParsedSkill("Skill B", "d", "body"))(),
        ]
        threads = [
            threading.Thread(
                target=s.run,
                args=(SkillContext(user_message="x", session_id="shared"),),
            )
            for s in skills
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        staged = sorted(p.name for p in isolated_workspaces.iterdir())
        assert len(staged) == 2, f"expected one workspace per skill, got {staged}"

    def test_workspace_ids_are_filesystem_safe(self, tmp_path):
        # The id becomes a directory name via code_exec._workspace_dir, which
        # strips anything outside [A-Za-z0-9_-]. A skill name full of spaces
        # and punctuation must not be able to produce a traversal or a
        # collision after sanitisation.
        skill = _make_skill(tmp_path / "a", name="Weird / Skill: name!")
        workspace_id = skill._workspace_id(SkillContext(session_id="s1"))
        assert "/" not in workspace_id and "\\" not in workspace_id
        assert ".." not in workspace_id

    def test_a_traversal_flavoured_session_id_lands_inside_code_exec_dir(
        self, monkeypatch, tmp_path
    ):
        # A session id is not user-controlled today, but it is the only
        # caller-supplied half of the workspace id — so a "../../settings"
        # value must still resolve inside CodeExecution, not beside it.
        # code_exec._workspace_dir strips everything outside [A-Za-z0-9_-].
        import sandbox_manager
        monkeypatch.setattr(sandbox_manager, "code_exec_dir", lambda: _mkdir(tmp_path / "ce"))

        skill = _make_skill(tmp_path / "a", name="Skill A")
        workspace_id = skill._workspace_id(SkillContext(session_id="../../settings"))
        _, directory = code_exec._workspace_dir(workspace_id)

        assert directory.resolve().parent == (tmp_path / "ce").resolve()


class TestExecutionContractIsRebuiltPerCall:
    """The contract half of the prompt is derived from probed capabilities at
    call time. Caching it across skills would mean a document skill's OUTPUT
    QUALITY section following a capability skill around."""

    def test_quality_guidance_does_not_persist_onto_the_next_skill(self):
        document = AdaptedClaudeSkill._execution_contract(False, "pptx")
        capability = AdaptedClaudeSkill._execution_contract(False, "webapp-testing")
        assert "OUTPUT QUALITY" in document
        assert "OUTPUT QUALITY" not in capability

    def test_staging_state_does_not_persist_between_calls(self, tmp_path):
        staged = AdaptedClaudeSkill._execution_contract(True, "pdf")
        unstaged = AdaptedClaudeSkill._execution_contract(False, "pdf")
        assert "staged at" in staged
        assert "staged at" not in unstaged
