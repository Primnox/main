"""Tests for code_skill.py's size cap — every other file-reading skill
(pdf_skill: 10000 chars, transcript_skill: 12000 chars) truncates before
handing content to think(); this one previously didn't."""
import brain
from skills.base_skill import SkillContext
from skills.code_skill import CodeSkill


def _fake_think_response(content: str = "looks fine") -> dict:
    return {"choices": [{"message": {"content": content}}]}


class TestCodeSkillTruncation:
    def test_small_file_is_sent_untruncated(self, tmp_path, monkeypatch):
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response()

        monkeypatch.setattr(brain, "think", fake_think)

        f = tmp_path / "small.py"
        f.write_text("print('hi')", encoding="utf-8")

        result = CodeSkill().run(SkillContext(file_path=str(f), user_message="explain this"))

        assert result.success is True
        assert "print('hi')" in captured["prompt"]
        assert "truncated" not in captured["prompt"]

    def test_large_file_is_truncated_before_reaching_think(self, tmp_path, monkeypatch):
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response()

        monkeypatch.setattr(brain, "think", fake_think)

        f = tmp_path / "huge.py"
        f.write_text("x = 1\n" * 10000, encoding="utf-8")  # ~60000 chars

        result = CodeSkill().run(SkillContext(file_path=str(f), user_message="explain this"))

        assert result.success is True
        assert "truncated for length" in captured["prompt"]
        # The prompt should be much smaller than the full file content.
        assert len(captured["prompt"]) < 20000

    def test_no_file_attached_fails_cleanly(self):
        result = CodeSkill().run(SkillContext(user_message="explain this"))
        assert result.success is False
        assert "no file attached" in result.error
