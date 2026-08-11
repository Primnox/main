"""Tests for skill_router.py's SKILL.md (Claude Skill package) discovery
pass — _discover_claude_skills(), and its integration with
list_skills()/get_skill_by_name()/route_skill(). Fully additive to the
existing *_skill.py discovery, so also spot-checks that existing skills are
unaffected.

Deliberately calls _discover_claude_skills() directly rather than the full
discover_skills() wherever possible — the latter mutates the real, shared
SKILL_REGISTRY/TRIGGER_MAP for every *_skill.py file as a side effect, which
collides with other test modules that pop/reimport skill modules from
sys.modules (e.g. test_skill_lazy_loading.py) and makes class-identity
assertions elsewhere order-dependent. _discover_claude_skills() only ever
touches CLAUDE_SKILLS_REGISTRY, so it's safe to call freely."""
import brain
import code_exec
from skills import skill_router
from skills.skill_router import (
    get_skill_by_name, list_skills, route_skill, CLAUDE_SKILLS_REGISTRY,
)


def _write_valid_skill(root, folder_name, name, description="does a thing"):
    d = root / folder_name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nInstructions here.",
        encoding="utf-8",
    )
    return d


def _write_malformed_skill(root, folder_name):
    d = root / folder_name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: broken\n---\nno description, invalid", encoding="utf-8")
    return d


class TestDiscoverClaudeSkills:
    def test_valid_skill_registers_and_appears_in_list_skills(self, monkeypatch, tmp_path):
        _write_valid_skill(tmp_path, "greeter", "Sample Greeter", "greets the user warmly")
        monkeypatch.setattr(skill_router, "_claude_skills_dir", lambda: tmp_path)
        CLAUDE_SKILLS_REGISTRY.clear()

        skill_router._discover_claude_skills()

        assert "sample_greeter" in CLAUDE_SKILLS_REGISTRY
        names = [s["name"] for s in list_skills()]
        assert "sample_greeter" in names

    def test_registered_skill_resolves_by_name(self, monkeypatch, tmp_path):
        _write_valid_skill(tmp_path, "greeter", "Sample Greeter")
        monkeypatch.setattr(skill_router, "_claude_skills_dir", lambda: tmp_path)
        CLAUDE_SKILLS_REGISTRY.clear()

        skill_router._discover_claude_skills()

        resolved = get_skill_by_name("sample_greeter")
        assert resolved is not None
        assert resolved().name == "Sample Greeter"

    def test_malformed_skill_is_skipped_valid_one_still_registers(self, monkeypatch, tmp_path):
        _write_malformed_skill(tmp_path, "broken_one")
        _write_valid_skill(tmp_path, "good_one", "Good Skill")
        monkeypatch.setattr(skill_router, "_claude_skills_dir", lambda: tmp_path)
        CLAUDE_SKILLS_REGISTRY.clear()

        skill_router._discover_claude_skills()

        assert "good_skill" in CLAUDE_SKILLS_REGISTRY
        assert "broken" not in CLAUDE_SKILLS_REGISTRY

    def test_missing_claude_skills_directory_does_not_raise(self, monkeypatch, tmp_path):
        monkeypatch.setattr(skill_router, "_claude_skills_dir", lambda: tmp_path / "does_not_exist")
        skill_router._discover_claude_skills()  # must not raise

    def test_folder_without_skill_md_is_ignored(self, monkeypatch, tmp_path):
        (tmp_path / "not_a_skill").mkdir()
        (tmp_path / "not_a_skill" / "notes.txt").write_text("nothing here", encoding="utf-8")
        monkeypatch.setattr(skill_router, "_claude_skills_dir", lambda: tmp_path)
        CLAUDE_SKILLS_REGISTRY.clear()

        skill_router._discover_claude_skills()  # must not raise, registers nothing

        assert CLAUDE_SKILLS_REGISTRY == {}


class TestExistingDiscoveryUnaffected:
    def test_existing_skills_still_present_after_claude_skills_discovery_runs(self):
        # discover_skills() (the *_skill.py pass) already ran once at module
        # import time. Running _discover_claude_skills() again on top of that
        # must not disturb existing skills' registration — it only ever
        # touches CLAUDE_SKILLS_REGISTRY.
        skill_router._discover_claude_skills()
        names = [s["name"] for s in list_skills()]
        assert "pdf_specialist" in names


class TestUseSkillIntegration:
    def test_route_skill_by_name_runs_the_adapted_skill_end_to_end(self, monkeypatch, tmp_path):
        _write_valid_skill(tmp_path, "greeter", "Integration Greeter")
        monkeypatch.setattr(skill_router, "_claude_skills_dir", lambda: tmp_path)
        CLAUDE_SKILLS_REGISTRY.clear()
        skill_router._discover_claude_skills()

        monkeypatch.setattr(brain, "think", lambda *a, **kw: {
            "choices": [{"message": {"content": "hello there!"}}]
        })
        run_python_calls = []
        monkeypatch.setattr(code_exec, "run_python", lambda *a, **kw: run_python_calls.append(1))

        result = route_skill(skill_name="integration_greeter", user_message="say hi")

        assert result["success"] is True
        assert result["output_text"] == "hello there!"
        assert run_python_calls == []
