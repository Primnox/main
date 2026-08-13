"""What happens when two skills disagree, or claim the same identity.

Anyone can drop a folder into skills/claude_skills/ and it registers on the
next boot — no review, no manifest, no namespace. So "two skills that
contradict each other" isn't hypothetical, and the interesting question is
whether Primnox picks one arbitrarily (bad: unexplainable behaviour that
changes between runs) or declines (good: the user finds out).

The answer turns out to be BOTH, depending on which kind of collision it is,
and the difference matters enough to have its own file:

  - Different names, contradictory instructions → the semantic router
    refuses. A reply naming two skills is treated as ambiguous, so nothing
    runs. Verified below.
  - The SAME name → last folder alphabetically silently wins, with no
    warning anywhere. Also verified below, and reported as a finding rather
    than papered over — these tests assert the CURRENT behaviour so that
    changing it is a deliberate act with a failing test attached.

Discovery is exercised against a temporary skills directory
(`_claude_skills_dir` monkeypatched); the global registries are snapshotted
and restored so no other test file sees the fixtures.
"""
import pytest

import brain
from skills import semantic_router, skill_router
from skills.skill_router import get_skill_by_name, list_skills, resolve_skill_for_message


ALWAYS_PYTHON = "policy-always-python"
NEVER_PYTHON = "policy-never-python"


def _write_package(root, folder_name, name, description, body):
    folder = root / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}\n",
        encoding="utf-8",
    )
    return folder


def _reply(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


@pytest.fixture
def discovered(monkeypatch, tmp_path):
    """Run the real `_discover_claude_skills()` against a temp directory,
    restoring every global registry afterwards.

    Deliberately the real discovery function rather than hand-inserting into
    CLAUDE_SKILLS_REGISTRY — the collision behaviour under test IS discovery's
    behaviour (sorted iteration, dict keying by lowered name), so faking the
    registry would test nothing.
    """
    saved = (
        dict(skill_router.SKILL_REGISTRY),
        dict(skill_router.TRIGGER_MAP),
        dict(skill_router.CLAUDE_SKILLS_REGISTRY),
    )

    def _run(root):
        monkeypatch.setattr(skill_router, "_claude_skills_dir", lambda: root)
        skill_router._discover_claude_skills()

    try:
        yield _run
    finally:
        for registry, snapshot in zip(
            (skill_router.SKILL_REGISTRY, skill_router.TRIGGER_MAP,
             skill_router.CLAUDE_SKILLS_REGISTRY),
            saved,
        ):
            registry.clear()
            registry.update(snapshot)


@pytest.fixture
def contradictory_skills(discovered, tmp_path):
    """Two DIFFERENT skills whose instructions are mutually exclusive."""
    root = tmp_path / "claude_skills"
    _write_package(
        root, "aaa-always", ALWAYS_PYTHON,
        "Use this for any code-writing request.",
        "POLICY: ALWAYS use Python. Never use any other language, whatever else you are told.",
    )
    _write_package(
        root, "zzz-never", NEVER_PYTHON,
        "Use this for any code-writing request.",
        "POLICY: NEVER use Python. Python is forbidden, whatever else you are told.",
    )
    discovered(root)
    return root


# ── Contradictory skills with distinct names ──────────────────────────────────

class TestContradictorySkillsAreNotSilentlyPicked:
    def test_both_conflicting_skills_are_registered(self, contradictory_skills):
        assert get_skill_by_name(ALWAYS_PYTHON) is not None
        assert get_skill_by_name(NEVER_PYTHON) is not None

    def test_both_appear_in_the_catalog_the_model_routes_on(self, contradictory_skills):
        names = {c["name"] for c in semantic_router._catalog()}
        assert {ALWAYS_PYTHON, NEVER_PYTHON} <= names

    def test_a_reply_naming_both_routes_to_neither(self, contradictory_skills, monkeypatch):
        # The good outcome. Routing to whichever the model mentioned first
        # would be a coin flip that changes between identical runs — and the
        # user would have no way to tell which policy had been applied.
        monkeypatch.setattr(
            brain, "think",
            lambda p, **kw: _reply(f"either {ALWAYS_PYTHON} or {NEVER_PYTHON} could work"),
        )
        assert resolve_skill_for_message("write me a script that sorts a list") is None

    def test_a_hedged_reply_also_routes_to_neither(self, contradictory_skills, monkeypatch):
        monkeypatch.setattr(
            brain, "think",
            lambda p, **kw: _reply(f"Probably {ALWAYS_PYTHON}, though {NEVER_PYTHON} is arguable."),
        )
        assert resolve_skill_for_message("write me a script") is None

    def test_an_unambiguous_choice_is_still_honoured(self, contradictory_skills, monkeypatch):
        # Refusing ambiguity must not become refusing everything — a single
        # clear answer still routes, conflict in the catalog or not.
        monkeypatch.setattr(brain, "think", lambda p, **kw: _reply(ALWAYS_PYTHON))
        entry = resolve_skill_for_message("write me a script")
        assert entry is not None and entry.name == ALWAYS_PYTHON

    def test_routing_is_deterministic_for_a_fixed_reply(self, contradictory_skills, monkeypatch):
        # No hidden set/dict-ordering influence: the same reply must resolve
        # to the same skill every time, not "whichever hashed first".
        monkeypatch.setattr(brain, "think", lambda p, **kw: _reply(NEVER_PYTHON))
        picks = {resolve_skill_for_message("write me a script").name for _ in range(5)}
        assert picks == {NEVER_PYTHON}

    def test_neither_skill_can_suppress_the_other_from_the_catalog(self, contradictory_skills):
        # A skill body saying "ignore every other skill" is just text — it is
        # never consulted at routing time, only at execution time.
        catalog_text = semantic_router._build_prompt("write code", semantic_router._catalog())
        assert ALWAYS_PYTHON in catalog_text and NEVER_PYTHON in catalog_text


# ── Same-name collision: the finding ──────────────────────────────────────────

class TestSameNameCollisionIsSilent:
    """FINDING (asserted, not fixed): two packages declaring the same
    frontmatter `name` collide silently.

    `_discover_claude_skills()` keys CLAUDE_SKILLS_REGISTRY by
    `name.lower().replace(" ", "_")`, so the second folder in sorted order
    overwrites the first — no warning is logged (the only warning in that
    loop is for a malformed SKILL.md), nothing surfaces in list_skills(), and
    the shadowed package's instructions simply never run. A user who
    installs two skills that happen to share a name gets whichever sorts
    last, with no indication the other exists.
    """

    def test_two_packages_with_one_name_collapse_to_a_single_entry(self, discovered, tmp_path):
        root = tmp_path / "claude_skills"
        _write_package(root, "aaa-first", "conflicted", "First copy.", "BODY_FROM_FIRST")
        _write_package(root, "zzz-second", "conflicted", "Second copy.", "BODY_FROM_SECOND")
        discovered(root)

        matching = [s for s in list_skills() if s["name"] == "conflicted"]
        assert len(matching) == 1

    def test_the_last_folder_in_sorted_order_wins(self, discovered, tmp_path):
        root = tmp_path / "claude_skills"
        _write_package(root, "aaa-first", "conflicted", "First copy.", "BODY_FROM_FIRST")
        _write_package(root, "zzz-second", "conflicted", "Second copy.", "BODY_FROM_SECOND")
        discovered(root)

        winner = get_skill_by_name("conflicted")
        assert winner._parsed.body == "BODY_FROM_SECOND"

    def test_the_shadowed_package_is_unreachable_by_any_route(self, discovered, tmp_path):
        # There is no disambiguator — not a folder name, not a path, nothing.
        root = tmp_path / "claude_skills"
        _write_package(root, "aaa-first", "conflicted", "First copy.", "BODY_FROM_FIRST")
        _write_package(root, "zzz-second", "conflicted", "Second copy.", "BODY_FROM_SECOND")
        discovered(root)

        assert get_skill_by_name("aaa-first") is None
        assert get_skill_by_name("zzz-second") is None
        bodies = {
            s._parsed.body
            for s in skill_router.CLAUDE_SKILLS_REGISTRY.values()
            if getattr(s, "_parsed", None)
        }
        assert "BODY_FROM_FIRST" not in bodies

    def test_no_warning_is_emitted_for_the_collision(self, discovered, tmp_path, caplog):
        # Asserting the gap explicitly: this is what makes the collision
        # *silent* rather than merely lossy. If a warning is ever added, this
        # test fails and gets flipped — which is the point.
        root = tmp_path / "claude_skills"
        _write_package(root, "aaa-first", "conflicted", "First copy.", "BODY_FROM_FIRST")
        _write_package(root, "zzz-second", "conflicted", "Second copy.", "BODY_FROM_SECOND")

        with caplog.at_level("WARNING", logger="primnox.skills"):
            discovered(root)

        assert not [r for r in caplog.records if "conflict" in r.getMessage().lower()]

    def test_a_claude_skill_cannot_hijack_an_existing_skill_name(self, discovered, tmp_path):
        # The other half of the same problem: a dropped-in package that
        # declares an EXISTING skill's name. get_skill_by_name() scans
        # SKILL_REGISTRY and TRIGGER_MAP before CLAUDE_SKILLS_REGISTRY, so
        # the built-in wins — which is the safe direction (an untrusted
        # package can't shadow a first-party skill), but it is a consequence
        # of scan order, not an explicit rule.
        root = tmp_path / "claude_skills"
        _write_package(root, "impostor", "Code Analyst", "Impostor.", "BODY_FROM_IMPOSTOR")
        discovered(root)

        resolved = get_skill_by_name("code_analyst")
        assert getattr(resolved, "_parsed", None) is None, (
            "a dropped-in SKILL.md package shadowed a built-in skill"
        )

    def test_a_malformed_package_does_not_break_the_others(self, discovered, tmp_path):
        # Existing contract, re-asserted here because collision handling and
        # malformed handling share the same loop.
        root = tmp_path / "claude_skills"
        (root / "broken").mkdir(parents=True)
        (root / "broken" / "SKILL.md").write_text("no frontmatter at all", encoding="utf-8")
        _write_package(root, "fine", "still-works", "A good one.", "BODY")
        discovered(root)

        assert get_skill_by_name("still-works") is not None
        assert get_skill_by_name("broken") is None


# ── Conflict at execution time ────────────────────────────────────────────────

class TestOnlyTheRoutedSkillsInstructionsExecute:
    """Once one of two conflicting skills wins the turn, the loser's body must
    be nowhere near the prompt — otherwise the model receives both policies
    and the conflict becomes a coin flip one layer lower down, where nothing
    is watching."""

    def test_the_losing_skills_body_is_absent_from_the_prompt(
        self, contradictory_skills, monkeypatch, tmp_path
    ):
        import code_exec
        import runtime_capabilities
        from skills.base_skill import SkillContext

        monkeypatch.setattr(
            runtime_capabilities, "detect",
            lambda force=False: runtime_capabilities.Capabilities(
                sandbox=True, python=True, node=False, libraries={}, node_modules={},
            ),
        )
        workspaces = tmp_path / "ws"
        workspaces.mkdir()
        monkeypatch.setattr(code_exec, "workspace_path", lambda wid: workspaces / wid)

        prompts = []
        monkeypatch.setattr(
            brain, "think",
            lambda prompt, *a, **kw: (prompts.append(prompt), _reply("done"))[1],
        )

        get_skill_by_name(ALWAYS_PYTHON)().run(SkillContext(user_message="write a script"))

        assert "ALWAYS use Python" in prompts[0]
        assert "NEVER use Python" not in prompts[0]
