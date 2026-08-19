"""The screenshot path must never claim to have seen something it didn't.

What the user actually saw on screen, three times in a row for three
different questions:

    ss saved bro. i see: ...

Nothing after the colon. The chain: sensor_vision hardcoded
`meta-llama/llama-4-scout-17b-16e-instruct`, the exact model brain.py had
already established 404s on this account. A 404 body carries no `choices`,
so the `.get()` chain fell through to "". That empty string was written to
the module-level debounce cache and returned as `{"description": ""}` —
key present, so screenshot_skill's `.get(..., "no visual description.")`
default never fired. Every later request matched the frame hash, hit the
poisoned cache, and produced the same blank claim forever.
"""
import pytest

import sensor_vision
from skills.base_skill import SkillContext
from skills.screenshot_skill import ScreenshotSkill


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    monkeypatch.setattr(sensor_vision, "last_frame_hash", None)
    monkeypatch.setattr(sensor_vision, "last_description", "no changes detected")


def _groq_settings(monkeypatch, vision_model="some-vision-model"):
    monkeypatch.setattr(sensor_vision, "get_api_key", lambda p: "sk-x")
    monkeypatch.setattr(sensor_vision, "_groq_vision_model", lambda: vision_model)
    monkeypatch.setattr(sensor_vision, "take_screenshot",
                        lambda crop_active=True: (None, "b64", "hash-1"))


class TestSensorVisionNeverInventsSuccess:
    def test_a_404_is_an_error_not_an_empty_description(self, monkeypatch):
        _groq_settings(monkeypatch)
        monkeypatch.setattr(sensor_vision.requests, "post",
                            lambda *a, **kw: _Resp(404, {"error": {"message": "model not found"}}))

        out = sensor_vision.describe_screen(force=True)

        assert "error" in out
        assert "description" not in out

    def test_a_failed_call_does_not_poison_the_cache(self, monkeypatch):
        # The bit that made it permanent: one failure and every later request
        # returned the same blank answer from cache.
        _groq_settings(monkeypatch)
        monkeypatch.setattr(sensor_vision.requests, "post",
                            lambda *a, **kw: _Resp(404, {"error": {"message": "nope"}}))

        sensor_vision.describe_screen(force=True)

        assert sensor_vision.last_description == "no changes detected"
        assert sensor_vision.last_frame_hash is None

    def test_a_200_with_empty_content_is_also_an_error(self, monkeypatch):
        _groq_settings(monkeypatch)
        monkeypatch.setattr(sensor_vision.requests, "post", lambda *a, **kw: _Resp(
            200, {"choices": [{"message": {"content": "   "}}]}))

        out = sensor_vision.describe_screen(force=True)

        assert "error" in out
        assert sensor_vision.last_description == "no changes detected"

    def test_a_real_description_is_returned_and_cached(self, monkeypatch):
        _groq_settings(monkeypatch)
        monkeypatch.setattr(sensor_vision.requests, "post", lambda *a, **kw: _Resp(
            200, {"choices": [{"message": {"content": "VS Code with a Python file open"}}]}))

        out = sensor_vision.describe_screen(force=True)

        assert out["description"] == "VS Code with a Python file open"
        assert sensor_vision.last_description == "VS Code with a Python file open"

    def test_groq_without_a_vision_model_says_so_before_calling(self, monkeypatch):
        _groq_settings(monkeypatch, vision_model="")

        def _never(*a, **kw):
            raise AssertionError("called the API with no vision model configured")

        monkeypatch.setattr(sensor_vision.requests, "post", _never)

        out = sensor_vision.describe_screen(force=True)

        assert "error" in out
        assert "Settings" in out["error"]

    def test_the_hardcoded_dead_model_is_gone(self):
        # It 404s. brain.GROQ_VISION_MODEL is the single source of truth.
        # Comments are allowed to name it — they explain why it was removed —
        # so strip them before checking that no CODE still sends it.
        import inspect
        code = "\n".join(
            line.split("#", 1)[0]
            for line in inspect.getsource(sensor_vision).splitlines()
        )
        assert "llama-4-scout" not in code


class TestScreenshotSkillTellsTheTruth:
    @pytest.fixture
    def _capture_ok(self, monkeypatch, tmp_path):
        import skills.screenshot_skill as mod
        monkeypatch.setattr(mod, "sandbox_dir", lambda: tmp_path, raising=False)

        class _Img:
            def save(self, p): open(p, "wb").write(b"png")

        import PIL.ImageGrab as ig
        monkeypatch.setattr(ig, "grab", lambda: _Img())
        monkeypatch.setattr("sandbox_manager.sandbox_dir", lambda: tmp_path)
        monkeypatch.setattr("sandbox_manager.enforce_quota", lambda *a, **kw: None)

    def test_it_does_not_claim_to_see_when_vision_failed(self, monkeypatch, _capture_ok):
        monkeypatch.setattr("sensor_vision.describe_screen",
                            lambda *a, **kw: {"error": "vision unavailable: model not found"})

        result = ScreenshotSkill().run(SkillContext(user_message="what do you see"))

        assert "i see:" not in result.output_text
        assert "couldn't read it" in result.output_text
        assert "model not found" in result.output_text

    def test_an_empty_description_is_treated_as_a_failure(self, monkeypatch, _capture_ok):
        # The exact shape that produced "ss saved bro. i see: ..." — key
        # present, value blank, so the .get() default never applied.
        monkeypatch.setattr("sensor_vision.describe_screen",
                            lambda *a, **kw: {"status": "updated", "description": ""})

        result = ScreenshotSkill().run(SkillContext(user_message="what do you see"))

        assert not result.output_text.rstrip().endswith("i see: ...")
        assert "couldn't read it" in result.output_text

    def test_a_short_description_is_not_ellipsised(self, monkeypatch, _capture_ok):
        monkeypatch.setattr("sensor_vision.describe_screen",
                            lambda *a, **kw: {"description": "A terminal window."})

        result = ScreenshotSkill().run(SkillContext(user_message="look"))

        assert result.output_text == "ss saved bro. i see: A terminal window."

    def test_a_long_description_is_ellipsised(self, monkeypatch, _capture_ok):
        monkeypatch.setattr("sensor_vision.describe_screen",
                            lambda *a, **kw: {"description": "x" * 400})

        result = ScreenshotSkill().run(SkillContext(user_message="look"))

        assert result.output_text.endswith("…")
        assert len(result.output_text) < 260
