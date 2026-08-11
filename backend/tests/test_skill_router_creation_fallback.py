"""Tests for skill_router.get_skill_for_trigger's tolerant creation-intent
fallback — the exact-phrase TRIGGER_MAP check alone misses real phrasing
like the bug report's "craete me a pdf where...", which never routed to
PDFSkill and fell through to plain chat instead.

get_skill_for_trigger now returns a lazy _SkillMeta stub for most skills
(see skill_router.discover_skills) rather than the class directly, so these
resolve through `_resolve_skill_class` before checking identity — that
exercises the real end-to-end path route_skill() actually uses, including
the lazy-import step."""
from skills.skill_router import get_skill_for_trigger, _resolve_skill_class
from skills.pdf_skill import PDFSkill
from skills.ppt_skill import PPTSkill


def _resolved(text):
    entry = get_skill_for_trigger(text)
    return _resolve_skill_class(entry) if entry is not None else None


class TestGetSkillForTriggerCreationFallback:
    def test_the_actual_bug_report_message_routes_to_pdf_skill(self):
        text = "can you craete me a pdf where there is deiscusion about spiderman brand new day"
        assert _resolved(text) is PDFSkill

    def test_exact_trigger_phrase_still_works_unchanged(self):
        assert _resolved("create a pdf about cats") is PDFSkill

    def test_reordered_ppt_phrasing_routes_to_ppt_skill(self):
        assert _resolved("can you generate me a powerpoint about our roadmap") is PPTSkill

    def test_unrelated_message_does_not_match_anything(self):
        assert get_skill_for_trigger("what's the weather like today") is None

    def test_reading_intent_without_creation_verb_does_not_false_positive(self):
        # "what's in this pdf" is already an exact trigger phrase for PDFSkill
        # (read intent) — confirm the new fallback doesn't change that result.
        assert _resolved("what's in this pdf") is PDFSkill

    def test_empty_text_returns_none(self):
        assert get_skill_for_trigger("") is None
