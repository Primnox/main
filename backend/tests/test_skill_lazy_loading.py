"""Tests for skill_router.py's lazy skill loading: discover_skills()
extracts routing metadata (name, triggers, extensions, pip deps) via static
AST parsing instead of importing every *_skill.py module up front. A skill
module — and whatever heavy third-party libraries it imports inside
execute() — is only actually imported the first time it's invoked.

Two deliberate exceptions to the lazy path, both covered below:
  - Island skills (BaseIslandSkill subclasses): FeedManager needs a live
    instance from boot to poll on a timer.
  - Claude Skills (SKILL.md packages): built as real classes at discovery,
    since there's no module to defer importing.

Uses code_skill as the lazy exemplar. It used to be pdf_skill, but the
homegrown PDF/PPT skills were deleted in favour of Anthropic's own pdf/pptx
Claude Skills, which now own those file extensions (see
TestClaudeSkillsClaimDocumentExtensions).
"""
import sys

from skills import skill_router
from skills.skill_router import (
    _SkillMeta, _extract_skill_meta, _resolve_skill_class,
    get_skill_for_extension, get_skill_by_name, list_skills,
)
from skills.code_skill import CodeSkill
from skills.calendar_skill import CalendarIslandSkill
from pathlib import Path

SKILLS_DIR = Path(skill_router.__file__).parent


class TestDiscoverSkillsRegistersLazyStubs:
    def test_code_skill_is_registered_as_a_lazy_stub_not_a_class(self):
        entry = get_skill_for_extension("py")
        assert isinstance(entry, _SkillMeta)
        assert entry.class_name == "CodeSkill"
        assert entry.module_name == "skills.code_skill"

    def test_island_skill_is_registered_as_a_real_class_not_a_stub(self):
        # Calendar needs a live instance from boot for background polling —
        # laziness doesn't apply to it.
        entry = get_skill_by_name("calendar")
        assert entry is CalendarIslandSkill

    def test_lazy_stub_exposes_the_same_attributes_a_real_class_would(self):
        entry = get_skill_for_extension("py")
        assert entry.name == "Code Analyst"
        assert "py" in entry.supported_extensions
        assert "explain this code" in entry.trigger_words

    def test_lazy_stub_carries_requires_pip_with_mismatched_names_intact(self):
        meta = _extract_skill_meta(SKILLS_DIR / "screenshot_skill.py", "skills.screenshot_skill")
        assert ("PIL", "Pillow") in meta.REQUIRES_PIP


class TestClaudeSkillsClaimDocumentExtensions:
    """The SKILL.md packages own the document file types now that the
    homegrown PDF/PPT skills are gone. Extension lookup is exact, so it
    resolves without the semantic router (and without a model call)."""

    def test_pdf_extension_resolves_to_the_claude_pdf_skill(self):
        entry = get_skill_for_extension("pdf")
        assert entry is not None
        assert entry.name.lower() == "pdf"

    def test_office_extensions_resolve_to_their_claude_skills(self):
        for ext, expected in (("docx", "docx"), ("xlsx", "xlsx"), ("pptx", "pptx"), ("csv", "xlsx")):
            entry = get_skill_for_extension(ext)
            assert entry is not None, f"no skill registered for .{ext}"
            assert entry.name.lower() == expected

    def test_claude_skills_carry_no_trigger_words(self):
        # They're routed semantically off `description`, not by substring
        # matching — a stray trigger word would resurrect the exact
        # over-triggering the semantic router replaced.
        entry = get_skill_for_extension("pdf")
        assert tuple(entry.trigger_words) == ()


class TestResolveSkillClass:
    def test_resolving_a_stub_returns_the_real_class(self):
        entry = get_skill_for_extension("py")
        resolved = _resolve_skill_class(entry)
        assert resolved is CodeSkill

    def test_resolving_a_real_class_returns_it_unchanged(self):
        assert _resolve_skill_class(CodeSkill) is CodeSkill

    def test_resolution_caches_the_real_class_back_into_the_registry(self):
        # Force re-registration of a fresh stub so this test doesn't depend
        # on whichever earlier test already resolved and cached CodeSkill.
        stub = _SkillMeta(
            module_name="skills.code_skill", class_name="CodeSkill", name="Code Analyst",
            supported_extensions=("__test_code_alias__",),
        )
        skill_router.SKILL_REGISTRY["__test_code_alias__"] = stub
        try:
            resolved = _resolve_skill_class(stub)
            assert resolved is CodeSkill
            # The registry entry should now be the real class, not the stub.
            assert skill_router.SKILL_REGISTRY["__test_code_alias__"] is CodeSkill
        finally:
            del skill_router.SKILL_REGISTRY["__test_code_alias__"]

    def test_resolving_an_unimportable_stub_returns_none_not_a_crash(self):
        stub = _SkillMeta(module_name="skills.does_not_exist_at_all", class_name="Nope", name="Broken")
        assert _resolve_skill_class(stub) is None


class TestListSkillsNeverImportsAnything:
    def test_list_skills_does_not_import_code_skill_module(self):
        sys.modules.pop("skills.code_skill", None)
        try:
            result = list_skills()
            assert any(s["name"] == "code_analyst" for s in result)
            assert "skills.code_skill" not in sys.modules
        finally:
            # Re-import so later tests relying on an already-loaded module aren't affected.
            import importlib
            importlib.import_module("skills.code_skill")

    def test_list_skills_includes_description_and_triggers_from_metadata(self):
        result = list_skills()
        entry = next(s for s in result if s["name"] == "code_analyst")
        assert "code" in entry["description"].lower()
        assert "py" in entry["triggers"]["extensions"]

    def test_list_skills_includes_claude_skills(self):
        # The semantic router builds its catalog from list_skills(), so a
        # Claude Skill missing here is a Claude Skill that can never be routed.
        names = {s["name"] for s in list_skills()}
        assert {"pdf", "pptx", "docx", "xlsx"} <= names


class TestExtractSkillMetaStaticParsing:
    def test_extracts_code_skill_metadata_correctly(self):
        meta = _extract_skill_meta(SKILLS_DIR / "code_skill.py", "skills.code_skill")
        assert meta is not None
        assert meta.class_name == "CodeSkill"
        assert meta.name == "Code Analyst"
        assert meta.is_island_skill is False
        assert "explain this code" in meta.trigger_words

    def test_extracts_calendar_skill_as_island_skill(self):
        meta = _extract_skill_meta(SKILLS_DIR / "calendar_skill.py", "skills.calendar_skill")
        assert meta is not None
        assert meta.is_island_skill is True

    def test_extracts_requires_pip_tuple_entries(self):
        meta = _extract_skill_meta(SKILLS_DIR / "screenshot_skill.py", "skills.screenshot_skill")
        assert meta is not None
        assert ("PIL", "Pillow") in meta.REQUIRES_PIP

    def test_returns_none_for_a_file_with_no_recognizable_skill_class(self, tmp_path):
        f = tmp_path / "not_really_a_skill.py"
        f.write_text("x = 1\n", encoding="utf-8")
        assert _extract_skill_meta(f, "irrelevant") is None
