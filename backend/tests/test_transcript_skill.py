"""Tests for transcript_skill.py's `mode` handling — input_schema advertised
a summary/action_items/full enum that execute() previously ignored entirely."""
import brain
from skills.base_skill import SkillContext
from skills.transcript_skill import TranscriptSkill


def _fake_think_response(content: str = "some analysis") -> dict:
    return {"choices": [{"message": {"content": content}}]}


class TestTranscriptSkillMode:
    def _run(self, tmp_path, monkeypatch, mode=None):
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response()

        monkeypatch.setattr(brain, "think", fake_think)

        f = tmp_path / "call.txt"
        f.write_text("Alice: let's ship it. Bob: agreed, I'll handle deploy.", encoding="utf-8")

        metadata = {"mode": mode} if mode else {}
        result = TranscriptSkill().run(SkillContext(file_path=str(f), metadata=metadata))
        return result, captured.get("prompt", "")

    def test_default_mode_requests_all_three_sections(self, tmp_path, monkeypatch):
        result, prompt = self._run(tmp_path, monkeypatch)
        assert result.success is True
        assert "Summary" in prompt
        assert "Action Items" in prompt
        assert "Key Moments" in prompt

    def test_summary_mode_only_requests_summary(self, tmp_path, monkeypatch):
        result, prompt = self._run(tmp_path, monkeypatch, mode="summary")
        assert result.success is True
        assert "Summary" in prompt
        assert "Action Items" not in prompt
        assert "Key Moments" not in prompt

    def test_action_items_mode_only_requests_action_items(self, tmp_path, monkeypatch):
        result, prompt = self._run(tmp_path, monkeypatch, mode="action_items")
        assert result.success is True
        assert "Action Items" in prompt
        assert "Summary" not in prompt
        assert "Key Moments" not in prompt

    def test_unknown_mode_falls_back_to_full(self, tmp_path, monkeypatch):
        result, prompt = self._run(tmp_path, monkeypatch, mode="bogus")
        assert result.success is True
        assert "Summary" in prompt
        assert "Action Items" in prompt
        assert "Key Moments" in prompt
