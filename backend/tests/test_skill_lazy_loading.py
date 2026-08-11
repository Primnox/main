"""Tests for skill_router.py's lazy skill loading: discover_skills() now
extracts routing metadata (name, triggers, extensions, pip deps) via static
AST parsing instead of importing every *_skill.py module up front. A skill
module — and whatever heavy third-party libraries it imports inside
execute() — is only actually imported the first time it's invoked.

Island skills (BaseIslandSkill subclasses) are the deliberate exception:
FeedManager needs a live instance from boot to poll on a timer, so they're
still registered eagerly, same as before this file gained the lazy path."""
import sys

from skills import skill_router
from skills.skill_router import (
    _SkillMeta, _extract_skill_meta, _resolve_skill_class,
    get_skill_for_extension, get_skill_by_name, list_skills, route_skill,
)
from skills.pdf_skill import PDFSkill
from skills.calendar_skill import CalendarIslandSkill
from pathlib import Path

SKILLS_DIR = Path(skill_router.__file__).parent


class TestDiscoverSkillsRegistersLazyStubs:
    def test_pdf_skill_is_registered_as_a_lazy_stub_not_a_class(self):
        entry = get_skill_for_extension("pdf")
        assert isinstance(entry, _SkillMeta)
        assert entry.class_name == "PDFSkill"
        assert entry.module_name == "skills.pdf_skill"

    def test_island_skill_is_registered_as_a_real_class_not_a_stub(self):
        # Calendar needs a live instance from boot for background polling —
        # laziness doesn't apply to it.
        entry = get_skill_for_extension("__nonexistent__")  # calendar has no extensions
        # Look it up via name instead, since it has no supported_extensions.
        entry = get_skill_by_name("calendar")
        assert entry is CalendarIslandSkill

    def test_lazy_stub_exposes_the_same_attributes_a_real_class_would(self):
        entry = get_skill_for_extension("pdf")
        assert entry.name == "PDF Specialist"
        assert "pdf" in entry.supported_extensions
        assert entry.creation_artifact_words == ("pdf",)
        assert ("pypdf", "pypdf") in [skill_router._normalize_pip_dep(d) for d in entry.REQUIRES_PIP]


class TestResolveSkillClass:
    def test_resolving_a_stub_returns_the_real_class(self):
        entry = get_skill_for_extension("pdf")
        resolved = _resolve_skill_class(entry)
        assert resolved is PDFSkill

    def test_resolving_a_real_class_returns_it_unchanged(self):
        assert _resolve_skill_class(PDFSkill) is PDFSkill

    def test_resolution_caches_the_real_class_back_into_the_registry(self):
        # Force re-registration of a fresh stub so this test doesn't depend
        # on whichever earlier test already resolved and cached PDFSkill.
        stub = _SkillMeta(
            module_name="skills.pdf_skill", class_name="PDFSkill", name="PDF Specialist",
            supported_extensions=("__test_pdf_alias__",),
        )
        skill_router.SKILL_REGISTRY["__test_pdf_alias__"] = stub
        try:
            resolved = _resolve_skill_class(stub)
            assert resolved is PDFSkill
            # The registry entry should now be the real class, not the stub.
            assert skill_router.SKILL_REGISTRY["__test_pdf_alias__"] is PDFSkill
        finally:
            del skill_router.SKILL_REGISTRY["__test_pdf_alias__"]

    def test_resolving_an_unimportable_stub_returns_none_not_a_crash(self):
        stub = _SkillMeta(module_name="skills.does_not_exist_at_all", class_name="Nope", name="Broken")
        assert _resolve_skill_class(stub) is None


class TestListSkillsNeverImportsAnything(object):
    def test_list_skills_does_not_import_pdf_skill_module(self):
        sys.modules.pop("skills.pdf_skill", None)
        try:
            result = list_skills()
            assert any(s["name"] == "pdf_specialist" for s in result)
            assert "skills.pdf_skill" not in sys.modules
        finally:
            # Re-import so later tests relying on an already-loaded module aren't affected.
            import importlib
            importlib.import_module("skills.pdf_skill")

    def test_list_skills_includes_description_and_triggers_from_metadata(self):
        result = list_skills()
        pdf_entry = next(s for s in result if s["name"] == "pdf_specialist")
        assert "PDF" in pdf_entry["description"] or "pdf" in pdf_entry["description"].lower()
        assert "pdf" in pdf_entry["triggers"]["extensions"]


class TestExtractSkillMetaStaticParsing:
    def test_extracts_pdf_skill_metadata_correctly(self):
        meta = _extract_skill_meta(SKILLS_DIR / "pdf_skill.py", "skills.pdf_skill")
        assert meta is not None
        assert meta.class_name == "PDFSkill"
        assert meta.name == "PDF Specialist"
        assert meta.is_island_skill is False
        assert "create pdf" in meta.trigger_words

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


class TestRouteSkillStillWorksEndToEnd:
    def test_route_skill_by_extension_resolves_and_runs_the_lazy_skill(self, tmp_path):
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"%PDF-1.4\n%%EOF")
        result = route_skill(file_path=str(f))
        # Real pypdf will likely fail to extract anything meaningful from
        # this minimal stub PDF and/or brain.think will fail without a
        # configured API key — the point here is only that routing resolved
        # to a real, callable skill instead of "No matching skill found."
        assert result.get("error") != "No matching skill found."

    def test_route_skill_by_trigger_word_resolves_the_lazy_skill(self):
        result = route_skill(user_message="what's in this pdf")
        assert result.get("error") != "No matching skill found."
