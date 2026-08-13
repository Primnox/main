"""Guard: EVERY provider failure path in brain.think() must set an "error" key.

Background — a real bug found live. think() reports provider failures as a
200-shaped dict: a well-formed ``choices[0].message.content`` whose text is a
human-readable apology ("ollama isn't running bro...", "Gemini API key not
set..."). Callers cannot tell that apart from a genuine completion unless an
"error" key sits alongside it. brain.resolve_think_text() is the shared guard
(see test_smart_paste_resolve.py) but it is only as good as the "error" key —
with no key it happily returns the apology as if it were real output, which is
how Smart Paste (server.py `/api/smart_paste`) overwrote the user's OS
clipboard with an apology and reported success.

That was fixed for Groq/OpenAI/Anthropic missing-key paths. This file
parametrises the SAME assertion across every provider and every way each one
can fail, so a newly-added provider (or a new failure branch on an existing
one) cannot reintroduce the class of bug.

The contract under test, stated once:

    A think() return value that is not a genuine model completion MUST carry a
    truthy "error" key.

Failure paths are driven by monkeypatching settings + requests.post — no
network, no keys, no real provider. See test_e2e_pdf_to_pptx_pipeline.py for
the live-model counterpart.
"""
import pytest
import requests

import brain
import settings_manager


# ── harness ──────────────────────────────────────────────────────────────────

def _install_settings(monkeypatch, **overrides):
    """think() reads settings via a late `from settings_manager import
    load_settings`, so patching the module attribute is what takes effect."""
    base = {"privacy_mirror_enabled": False}
    base.update(overrides)
    monkeypatch.setattr(settings_manager, "load_settings", lambda: base)


def _no_keys(monkeypatch):
    """Make every API key lookup come back empty, so 'missing key' branches
    fire regardless of what is in the real settings.json or the environment.
    Critically this also means a stray real key on the dev machine can never
    turn one of these into an actual billed network call."""
    monkeypatch.setattr(brain, "get_api_key", lambda provider: "")
    monkeypatch.setattr(brain, "get_groq_api_key", lambda: "")


def _post_raises(exc):
    def _post(*a, **kw):
        raise exc
    return _post


class _Resp:
    """Minimal requests.Response stand-in."""

    def __init__(self, payload, status_code=200, raise_on_json=False):
        self._payload = payload
        self.status_code = status_code
        self._raise_on_json = raise_on_json
        self.headers = {}
        self.text = str(payload)

    def json(self):
        if self._raise_on_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


# Each case: (id, setup(monkeypatch) -> None). After setup, calling
# brain.think("hi") must return a dict with a truthy "error" key.
def _case_openai_missing_key(monkeypatch):
    _install_settings(monkeypatch, active_model="OpenAI_GPT_4o")
    _no_keys(monkeypatch)


def _case_anthropic_missing_key(monkeypatch):
    _install_settings(monkeypatch, active_model="Anthropic_Claude_3")
    _no_keys(monkeypatch)


def _case_groq_missing_key(monkeypatch):
    _install_settings(monkeypatch, active_model="Groq_Llama_3")
    _no_keys(monkeypatch)


def _case_gemini_missing_key(monkeypatch):
    _install_settings(monkeypatch, active_model="Gemini_Flash")
    _no_keys(monkeypatch)


def _case_gemini_non_json_body(monkeypatch):
    # e.g. a Cloudflare HTML 502 in front of the API — body is not JSON.
    _install_settings(monkeypatch, active_model="Gemini_Flash")
    monkeypatch.setattr(brain, "get_api_key", lambda provider: "sk-fake")
    monkeypatch.setattr(brain.requests, "post",
                        lambda *a, **kw: _Resp("<html>502</html>", status_code=502, raise_on_json=True))


def _case_ollama_timeout(monkeypatch):
    _install_settings(monkeypatch, active_model="Ollama_Local",
                      ollama_base_url="http://localhost:11434", ollama_model="llama3.2")
    monkeypatch.setattr(brain.requests, "post", _post_raises(requests.exceptions.Timeout()))


def _case_ollama_unreachable(monkeypatch):
    _install_settings(monkeypatch, active_model="Ollama_Local",
                      ollama_base_url="http://localhost:11434", ollama_model="llama3.2")
    monkeypatch.setattr(brain.requests, "post", _post_raises(requests.exceptions.ConnectionError()))


def _case_llamacpp_timeout(monkeypatch):
    _install_settings(monkeypatch, active_model="LlamaCpp_Local",
                      llamacpp_base_url="http://localhost:8080")
    monkeypatch.setattr(brain.requests, "post", _post_raises(requests.exceptions.Timeout()))


def _case_llamacpp_unreachable(monkeypatch):
    _install_settings(monkeypatch, active_model="LlamaCpp_Local",
                      llamacpp_base_url="http://localhost:8080")
    monkeypatch.setattr(brain.requests, "post", _post_raises(requests.exceptions.ConnectionError()))


def _custom_settings(monkeypatch, **profile_overrides):
    profile = {"id": "p1", "name": "local box", "base_url": "http://localhost:9999",
               "api_type": "openai", "model": "m", "api_key": ""}
    profile.update(profile_overrides)
    _install_settings(monkeypatch, active_model="Custom",
                      custom_providers=[profile], active_custom_provider_id="p1")


def _case_custom_no_base_url(monkeypatch):
    _custom_settings(monkeypatch, base_url="")


def _case_custom_timeout(monkeypatch):
    _custom_settings(monkeypatch)
    monkeypatch.setattr(brain.requests, "post", _post_raises(requests.exceptions.Timeout()))


def _case_custom_unreachable(monkeypatch):
    _custom_settings(monkeypatch)
    monkeypatch.setattr(brain.requests, "post", _post_raises(requests.exceptions.ConnectionError()))


def _case_custom_anthropic_error_body(monkeypatch):
    # An Anthropic-shaped host returning an API error object rather than
    # content blocks — the mapper reads res["content"][0]["text"], finds
    # nothing, and must not present that as a completion.
    _custom_settings(monkeypatch, api_type="anthropic")
    monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: _Resp(
        {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}},
        status_code=401))


def _case_anthropic_error_body(monkeypatch):
    _install_settings(monkeypatch, active_model="Anthropic_Claude_3")
    monkeypatch.setattr(brain, "get_api_key", lambda provider: "sk-fake")
    monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: _Resp(
        {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
        status_code=529))


def _case_openai_error_body(monkeypatch):
    _install_settings(monkeypatch, active_model="OpenAI_GPT_4o")
    monkeypatch.setattr(brain, "get_api_key", lambda provider: "sk-fake")
    monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: _Resp(
        {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}},
        status_code=401))


def _case_groq_all_models_failed(monkeypatch):
    _install_settings(monkeypatch, active_model="Groq_Llama_3")
    monkeypatch.setattr(brain, "get_api_key", lambda provider: "" if provider == "gemini" else "sk-fake")
    monkeypatch.setattr(brain, "get_groq_api_key", lambda: "sk-fake")
    monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: _Resp(
        {"error": {"message": "rate limit", "type": "rate_limit_exceeded"}}, status_code=429))


def _case_offline(monkeypatch):
    _install_settings(monkeypatch, active_model="Groq_Llama_3")
    monkeypatch.setattr(brain, "get_api_key", lambda provider: "sk-fake")
    monkeypatch.setattr(brain, "get_groq_api_key", lambda: "sk-fake")
    monkeypatch.setattr(brain.requests, "post",
                        _post_raises(requests.exceptions.ConnectionError("no route to host")))


def _case_unexpected_crash(monkeypatch):
    _install_settings(monkeypatch, active_model="Groq_Llama_3")
    monkeypatch.setattr(brain, "get_api_key", lambda provider: "sk-fake")
    monkeypatch.setattr(brain, "get_groq_api_key", lambda: "sk-fake")
    monkeypatch.setattr(brain.requests, "post", _post_raises(RuntimeError("boom")))


FAILURE_CASES = [
    ("openai/missing-key", _case_openai_missing_key),
    ("openai/error-body", _case_openai_error_body),
    ("anthropic/missing-key", _case_anthropic_missing_key),
    ("anthropic/error-body", _case_anthropic_error_body),
    ("groq/missing-key", _case_groq_missing_key),
    ("groq/all-models-failed", _case_groq_all_models_failed),
    ("gemini/missing-key", _case_gemini_missing_key),
    ("gemini/non-json-body", _case_gemini_non_json_body),
    ("ollama/timeout", _case_ollama_timeout),
    ("ollama/unreachable", _case_ollama_unreachable),
    ("llamacpp/timeout", _case_llamacpp_timeout),
    ("llamacpp/unreachable", _case_llamacpp_unreachable),
    ("custom/no-base-url", _case_custom_no_base_url),
    ("custom/timeout", _case_custom_timeout),
    ("custom/unreachable", _case_custom_unreachable),
    ("custom-anthropic/error-body", _case_custom_anthropic_error_body),
    ("transport/offline", _case_offline),
    ("transport/unexpected-crash", _case_unexpected_crash),
]


@pytest.mark.parametrize("case_id,setup", FAILURE_CASES, ids=[c[0] for c in FAILURE_CASES])
class TestEveryProviderFailurePathSetsErrorKey:
    def test_sets_error_key(self, case_id, setup, monkeypatch):
        """The core contract. A missing "error" key here means resolve_think_text()
        will hand the caller a fabricated apology as if it were model output."""
        setup(monkeypatch)
        res = brain.think("transform this text")
        assert isinstance(res, dict), f"{case_id}: think() must always return a dict"
        assert res.get("error"), (
            f"{case_id}: provider failure returned no 'error' key — "
            f"resolve_think_text() cannot distinguish this from a real completion. "
            f"Got: {res!r}"
        )

    def test_resolve_think_text_falls_back_to_the_caller_value(self, case_id, setup, monkeypatch):
        """The user-visible consequence, asserted directly: Smart Paste passes the
        user's clipboard as the fallback. On any failure it must get that exact
        text back — never an apology, never an empty string."""
        setup(monkeypatch)
        original_clipboard = "Hey team — moving standup to 3pm, see you there."
        res = brain.think("rewrite this professionally")
        assert brain.resolve_think_text(res, original_clipboard) == original_clipboard, (
            f"{case_id}: Smart Paste would have overwritten the user's clipboard. Got: {res!r}"
        )


class TestErrorKeyContractIsMeaningful:
    """Negative controls — the guard above must not be trivially satisfiable
    (e.g. by an implementation that stamps "error" onto every response)."""

    def test_a_genuine_completion_has_no_error_key(self, monkeypatch):
        _install_settings(monkeypatch, active_model="OpenAI_GPT_4o")
        monkeypatch.setattr(brain, "get_api_key", lambda provider: "sk-fake")
        monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: _Resp(
            {"choices": [{"message": {"content": "Hey team, standup moves to 3pm."}}]}))

        res = brain.think("rewrite this professionally")

        assert not res.get("error")
        assert brain.resolve_think_text(res, "fallback") == "Hey team, standup moves to 3pm."

    def test_a_genuine_local_completion_has_no_error_key(self, monkeypatch):
        # Local providers are the ones whose failure paths regressed, so prove
        # their success path still reads as success.
        _install_settings(monkeypatch, active_model="Ollama_Local",
                          ollama_base_url="http://localhost:11434", ollama_model="llama3.2")
        monkeypatch.setattr(brain.requests, "post", lambda *a, **kw: _Resp(
            {"choices": [{"message": {"content": "rewritten locally"}}]}))

        res = brain.think("rewrite this")

        assert not res.get("error")
        assert brain.resolve_think_text(res, "fallback") == "rewritten locally"


class TestFailurePathsStillCarryAHumanReadableMessage:
    """Adding the "error" key must not cost the user the friendly explanation —
    the chat UI renders choices[].content, so both have to be present."""

    @pytest.mark.parametrize("case_id,setup", FAILURE_CASES, ids=[c[0] for c in FAILURE_CASES])
    def test_error_is_a_non_empty_string_or_truthy_value(self, case_id, setup, monkeypatch):
        setup(monkeypatch)
        res = brain.think("hello")
        err = res.get("error")
        assert err, f"{case_id}: empty error value"
        # Whatever shape the provider used, it must stringify to something a
        # log line or an error banner can actually show.
        assert str(err).strip(), f"{case_id}: error stringifies to blank"
