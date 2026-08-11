"""Tests for skill_router.py's REQUIRES_PIP handling — specifically the
import-name vs pip-install-name distinction (e.g. `import PIL` comes from
`pip install Pillow`; a bare string previously meant the auto-generated
"pip install X" hint could be wrong)."""
from skills import skill_router


class DummySkillPlainStrings:
    name = "Dummy Plain"
    REQUIRES_PIP = ["this_module_does_not_exist_xyz"]


class DummySkillTuple:
    name = "Dummy Tuple"
    REQUIRES_PIP = [("PIL", "Pillow")]


class DummySkillAllPresent:
    name = "Dummy Present"
    REQUIRES_PIP = ["os", "sys"]  # always importable stdlib modules


class TestNormalizePipDep:
    def test_plain_string_maps_to_itself_for_both(self):
        assert skill_router._normalize_pip_dep("reportlab") == ("reportlab", "reportlab")

    def test_tuple_is_passed_through(self):
        assert skill_router._normalize_pip_dep(("pptx", "python-pptx")) == ("pptx", "python-pptx")


class TestCheckPipDeps:
    def test_missing_plain_string_dep_reports_same_name_for_both(self):
        missing = skill_router._check_pip_deps(DummySkillPlainStrings)
        assert missing == [("this_module_does_not_exist_xyz", "this_module_does_not_exist_xyz")]

    def test_tuple_dep_reports_correct_pip_name_when_present(self):
        # PIL/Pillow is an actual installed dependency in this environment
        # (screenshot_skill.py uses it) — should NOT show up as missing.
        missing = skill_router._check_pip_deps(DummySkillTuple)
        assert missing == []

    def test_no_missing_deps_returns_empty_list(self):
        assert skill_router._check_pip_deps(DummySkillAllPresent) == []

    def test_real_skills_declare_correct_pip_names_for_known_mismatches(self):
        # Regression guard for the actual bug: these two skills' import name
        # differs from their pip package name.
        from skills.screenshot_skill import ScreenshotSkill
        from skills.ppt_skill import PPTSkill

        assert ("PIL", "Pillow") in ScreenshotSkill.REQUIRES_PIP
        assert ("pptx", "python-pptx") in PPTSkill.REQUIRES_PIP
