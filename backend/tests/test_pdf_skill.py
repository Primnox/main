"""Tests for pdf_skill.py's `intent` handling — input_schema advertised a
read/generate enum that execute() previously ignored, always re-deriving
intent by keyword-scanning user_message instead."""
import brain
from skills.base_skill import SkillContext
from skills.pdf_skill import PDFSkill


def _fake_think_response(content: str = "# hello\nsome generated content") -> dict:
    return {"choices": [{"message": {"content": content}}]}


class TestPDFSkillIntent:
    def test_explicit_generate_intent_generates_even_without_trigger_words(self, tmp_path, monkeypatch):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response())
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        # No "create pdf"/"generate pdf" phrasing in user_message at all —
        # only the explicit metadata intent should drive this.
        result = PDFSkill().run(SkillContext(user_message="a report about Q3 sales", metadata={"intent": "generate"}))

        assert result.success is True
        assert result.output_path is not None

    def test_explicit_read_intent_requires_a_file_even_with_generate_wording(self):
        # user_message contains "create pdf" wording, but explicit intent=read
        # should override the keyword heuristic and require a file instead.
        result = PDFSkill().run(SkillContext(user_message="create pdf summary of this", metadata={"intent": "read"}))

        assert result.success is False
        assert "no pdf file provided" in result.error

    def test_no_explicit_intent_falls_back_to_keyword_heuristic(self, tmp_path, monkeypatch):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response())
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        # No metadata at all (today's only real caller) — behavior must be
        # unchanged: "create pdf" in the message still triggers generation.
        result = PDFSkill().run(SkillContext(user_message="create pdf about the weather"))

        assert result.success is True
        assert result.output_path is not None

    def test_no_explicit_intent_and_no_trigger_words_requires_a_file(self):
        result = PDFSkill().run(SkillContext(user_message="what does this say"))
        assert result.success is False
        assert "no pdf file provided" in result.error


class TestPDFSkillChatHistoryContext:
    """Regression coverage for a real bug: 'create me a pdf for the debate'
    generated a PDF with zero knowledge of the actual debate discussed
    earlier in the same session, because core.py never passed chat_history
    into route_skill() — SkillContext.chat_history was always empty."""

    def test_chat_history_is_included_in_the_generation_prompt(self, tmp_path, monkeypatch):
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response()

        monkeypatch.setattr(brain, "think", fake_think)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        history = [
            {"speaker": "User", "text": "let's debate AI replacing jobs"},
            {"speaker": "Primnox", "text": "sure — AI could replace routine jobs but create new ones in other sectors..."},
        ]
        result = PDFSkill().run(SkillContext(
            user_message="create me a pdf for the debate",
            chat_history=history,
        ))

        assert result.success is True
        assert "AI replacing jobs" in captured["prompt"]
        assert "create new ones in other sectors" in captured["prompt"]

    def test_no_chat_history_still_works_as_before(self, tmp_path, monkeypatch):
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response()

        monkeypatch.setattr(brain, "think", fake_think)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = PDFSkill().run(SkillContext(user_message="create a pdf about cats"))

        assert result.success is True
        assert "RECENT CONVERSATION" not in captured["prompt"]
