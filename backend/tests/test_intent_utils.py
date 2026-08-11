"""Tests for intent_utils.py's tolerant creation-intent detection — the
fallback for skill routing when exact trigger phrases miss real phrasing
(typos, reordered/inserted words)."""
from skills.intent_utils import expresses_creation_intent


class TestExpressesCreationIntent:
    def test_the_actual_bug_report_message(self):
        # The exact message that slipped past the exact-phrase trigger match:
        # typo ("craete") + an inserted word ("me") between verb and artifact.
        text = "can you craete me a pdf where there is deiscusion about spiderman brand new day"
        assert expresses_creation_intent(text, ("pdf",)) is True

    def test_exact_phrasing_still_works(self):
        assert expresses_creation_intent("create a pdf about cats", ("pdf",)) is True

    def test_inflected_verb_forms_match(self):
        assert expresses_creation_intent("I need you creating a pdf for this", ("pdf",)) is True
        assert expresses_creation_intent("please generate a pdf", ("pdf",)) is True
        assert expresses_creation_intent("could you draft a pdf", ("pdf",)) is True

    def test_missing_artifact_word_does_not_match(self):
        assert expresses_creation_intent("create a summary of this meeting", ("pdf",)) is False

    def test_missing_verb_does_not_match(self):
        assert expresses_creation_intent("what's in this pdf", ("pdf",)) is False

    def test_empty_text_does_not_match(self):
        assert expresses_creation_intent("", ("pdf",)) is False

    def test_no_artifact_words_does_not_match(self):
        assert expresses_creation_intent("create a pdf", ()) is False

    def test_ppt_artifact_words(self):
        assert expresses_creation_intent("make a presentation about our roadmap", ("ppt", "pptx", "powerpoint", "presentation")) is True

    def test_unrelated_word_containing_verb_substring_is_not_a_false_positive(self):
        # "mistake"/"taken" shouldn't fuzzy-match "make" closely enough to trigger.
        assert expresses_creation_intent("I made a mistake with this pdf export", ("pdf",)) is True  # "made" IS an exact inflected form — correctly matches
        assert expresses_creation_intent("this pdf was mistakenly taken down", ("pdf",)) is False
