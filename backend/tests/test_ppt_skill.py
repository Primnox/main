"""Tests for ppt_skill.py's execution-verification guard: python-pptx saves
a valid-but-empty .pptx instead of raising when there are no slides, so a
model reply that parses as valid JSON but isn't a real slide array (`[]`,
or a dict instead of a list) must be caught explicitly rather than reported
as a successful generation."""
import brain
from skills.base_skill import SkillContext
from skills.ppt_skill import PPTSkill


def _fake_think_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


class TestPPTSkillEmptyContentGuard:
    def test_empty_slide_array_fails_without_saving(self, monkeypatch, tmp_path):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response("[]"))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = PPTSkill().run(SkillContext(user_message="a talk about nothing"))

        assert result.success is False
        assert "no slides" in result.error.lower()
        assert not list((tmp_path / "Documents" / "Primnox" / "Generated").glob("*.pptx"))

    def test_non_list_json_fails_without_saving(self, monkeypatch, tmp_path):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response('{"title": "oops, a dict not a list"}'))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = PPTSkill().run(SkillContext(user_message="a talk about nothing"))

        assert result.success is False
        assert "no slides" in result.error.lower()

    def test_valid_slides_still_succeed(self, monkeypatch, tmp_path):
        slides_json = '[{"title": "Intro", "content": ["point one", "point two"]}]'
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response(slides_json))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = PPTSkill().run(SkillContext(user_message="a real talk"))

        assert result.success is True
        assert result.output_path is not None
        from pathlib import Path
        assert Path(result.output_path).exists()
        assert Path(result.output_path).stat().st_size > 0

    def test_malformed_json_still_fails_as_before(self, monkeypatch, tmp_path):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response("not json at all"))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = PPTSkill().run(SkillContext(user_message="whatever"))

        assert result.success is False
        assert "structure" in result.error.lower()


class TestPPTSkillChatHistoryContext:
    def test_chat_history_is_included_in_the_generation_prompt(self, monkeypatch, tmp_path):
        captured = {}
        slides_json = '[{"title": "Intro", "content": ["point one"]}]'

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response(slides_json)

        monkeypatch.setattr(brain, "think", fake_think)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        history = [{"speaker": "User", "text": "let's talk about our Q3 roadmap"}]
        result = PPTSkill().run(SkillContext(user_message="make me a ppt about that", chat_history=history))

        assert result.success is True
        assert "Q3 roadmap" in captured["prompt"]

    def test_no_chat_history_still_works_as_before(self, monkeypatch, tmp_path):
        captured = {}
        slides_json = '[{"title": "Intro", "content": ["point one"]}]'

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response(slides_json)

        monkeypatch.setattr(brain, "think", fake_think)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        result = PPTSkill().run(SkillContext(user_message="a talk about cats"))

        assert result.success is True
        assert "RECENT CONVERSATION" not in captured["prompt"]
