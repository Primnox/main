"""Security tests for privacy/mirror.py and its wiring into models/gateway.py
— the cloud-boundary PII scrubbing gate (CRS §13.2.2).

Pure unit tests against the regex fallback path (no network, no GPU, runs in
milliseconds) plus a gating test against gateway.stream_completion() with a
fake provider that records exactly what it was handed — which is the only way
to actually prove PII never crosses the boundary, rather than trusting that
some redaction happened somewhere.

Model-based (DeBERTa) detection is exercised separately and manually — it
downloads/loads a ~370MB model on first use, which is correct to keep out of
the default fast test loop but was verified during development (names, SSNs,
cities all detected; "exit code 137" correctly left alone).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from primnox2.privacy import mirror  # noqa: E402


# ── ScrubSession: regex-fallback detection ───────────────────────────────────

@pytest.fixture(autouse=True)
def _force_regex_fallback(monkeypatch):
    """Every test in this file must exercise the deterministic, instant regex
    path — not whatever state the DeBERTa model happens to be in (loaded from
    a previous test run, still loading, failed). Pinning `_pipeline` to None
    makes these tests reproducible in CI with no model downloaded."""
    monkeypatch.setattr(mirror, "_pipeline", None)
    monkeypatch.setattr(mirror, "_model_loading", False)


def test_email_is_scrubbed_and_never_appears_in_output():
    sess = mirror.ScrubSession()
    out = sess.scrub("reach me at attacker@target.example for details")
    assert "attacker@target.example" not in out
    assert sess.rehydrate(out) == "reach me at attacker@target.example for details"


def test_credit_card_is_scrubbed():
    sess = mirror.ScrubSession()
    out = sess.scrub("card number 4111-1111-1111-1111 expires soon")
    assert "4111-1111-1111-1111" not in out
    assert "4111111111111111" not in out.replace("-", "").replace(" ", "")


def test_ipv4_is_scrubbed():
    sess = mirror.ScrubSession()
    out = sess.scrub("connect to 10.0.0.42 on port 8080")
    assert "10.0.0.42" not in out


def test_api_key_value_is_redacted_but_key_name_survives():
    """The API_KEY pattern redacts the VALUE, not the surrounding
    `token=`/`key=` prose — the model still needs to know it's looking at a
    credential, just not the credential itself."""
    sess = mirror.ScrubSession()
    out = sess.scrub('token="NOT_A_REAL_KEY_0000000000000000"')
    assert "NOT_A_REAL_KEY_0000000000000000" not in out
    assert "token=" in out


def test_generic_long_token_is_scrubbed():
    sess = mirror.ScrubSession()
    secret = "a" * 40
    out = sess.scrub(f"the value is {secret} for reference")
    assert secret not in out


def test_known_city_is_scrubbed_by_gazetteer():
    sess = mirror.ScrubSession()
    out = sess.scrub("I'm flying from Mumbai to Tokyo next week")
    assert "Mumbai" not in out
    assert "Tokyo" not in out


def test_same_value_reuses_one_placeholder():
    """A repeated value must map to the SAME placeholder within a session —
    otherwise the cloud model sees inconsistent tokens for what is actually
    one entity, and answers worse."""
    sess = mirror.ScrubSession()
    out = sess.scrub("Contact a@b.com or reach a@b.com again")
    placeholders = set(mirror._LEFTOVER_PLACEHOLDER_RE.findall(out) +
                        [p for p in sess.to_original if p in out])
    # Both occurrences replaced with the identical placeholder string.
    assert out.count(sess._to_placeholder["a@b.com"]) == 2


def test_distinct_values_get_distinct_placeholders():
    sess = mirror.ScrubSession()
    sess.scrub("first@example.com and second@example.com")
    assert sess._to_placeholder["first@example.com"] != sess._to_placeholder["second@example.com"]


def test_empty_string_is_a_no_op():
    sess = mirror.ScrubSession()
    assert sess.scrub("") == ""
    assert sess.rehydrate("") == ""


def test_clean_text_is_unchanged():
    sess = mirror.ScrubSession()
    text = "just a normal sentence about nothing sensitive"
    assert sess.scrub(text) == text


# ── Rehydration safety nets ───────────────────────────────────────────────────

def test_unmapped_placeholder_is_stripped_not_leaked():
    """If the model echoes or invents a §LABEL_n§ token this session never
    produced, rehydrate() must never let that raw placeholder reach the user
    — the "safety net" the module docstring describes. A raw §EMAIL_1§
    leaking to a real user reads as a bug in the product's own syntax."""
    sess = mirror.ScrubSession()
    sess.scrub("nothing sensitive here")  # empty mapping
    out = sess.rehydrate("the model made up §EMAIL_1§ from nowhere")
    assert "§EMAIL_1§" not in out
    assert "§" not in out


def test_rehydrate_restores_only_whats_actually_mapped():
    sess = mirror.ScrubSession()
    scrubbed = sess.scrub("email me at real@example.com")
    injected = scrubbed + " also §PHONENUMBER_99§"
    out = sess.rehydrate(injected)
    assert "real@example.com" in out          # the real mapping restored
    assert "§PHONENUMBER_99§" not in out      # the invented one stripped


def test_longer_placeholder_ids_not_clobbered_by_shorter_prefix():
    """§EMAIL_1§ and §EMAIL_10§ must not collide — rehydrate() replaces
    longest placeholders first specifically to prevent this."""
    sess = mirror.ScrubSession()
    for i in range(11):
        sess.scrub(f"user{i}@example.com")
    scrubbed_all = " ".join(sess._to_placeholder[f"user{i}@example.com"] for i in range(11))
    out = sess.rehydrate(scrubbed_all)
    for i in range(11):
        assert f"user{i}@example.com" in out


# ── StreamRehydrator: chunked/streamed rehydration ───────────────────────────

def test_stream_rehydrator_restores_placeholder_split_across_chunks():
    sess = mirror.ScrubSession()
    scrubbed = sess.scrub("contact leak@example.com now")
    placeholder = sess._to_placeholder["leak@example.com"]
    mid = len(placeholder) // 2

    rehy = mirror.StreamRehydrator(sess)
    out = ""
    # Feed the placeholder split across two chunks, as a real token stream
    # would — the whole point of the buffering logic under test.
    out += rehy.feed(scrubbed[: scrubbed.index(placeholder) + mid])
    out += rehy.feed(scrubbed[scrubbed.index(placeholder) + mid:])
    out += rehy.flush()
    assert out == "contact leak@example.com now"


def test_stream_rehydrator_flush_drops_dangling_partial():
    """A stream that ends mid-placeholder (the model's reply got cut off)
    must not leak the dangling fragment — flush() strips it rather than
    emitting a truncated §EMAIL_ with no closing §."""
    sess = mirror.ScrubSession()
    sess.scrub("contact cut@example.com")
    placeholder = sess._to_placeholder["cut@example.com"]

    rehy = mirror.StreamRehydrator(sess)
    rehy.feed("reply ends mid " + placeholder[:-1])  # missing the closing §
    out = rehy.flush()
    assert "§" not in out
    assert placeholder[:-1] not in out or placeholder[:-1].rstrip("§") not in out


def test_stream_rehydrator_never_emits_raw_placeholder_across_feeds():
    sess = mirror.ScrubSession()
    scrubbed = sess.scrub("email dana@example.com")
    rehy = mirror.StreamRehydrator(sess)
    accumulated = ""
    for ch in scrubbed:
        accumulated += rehy.feed(ch)
    accumulated += rehy.flush()
    assert accumulated == "email dana@example.com"
    assert "§" not in accumulated


# ── The gate itself: gateway.stream_completion() ─────────────────────────────

class _RecordingProvider:
    """A fake non-local provider that records exactly what it was handed, so
    a test can assert on the actual bytes crossing the boundary rather than
    trusting a side-effect."""
    name = "recording-fake"
    base_url = "https://fake.example"
    is_local = False
    api_key = "fake-key-for-tests"

    def __init__(self):
        self.received_messages: list[dict] | None = None

    def stream(self, messages, model=None, usage=None):
        self.received_messages = messages
        yield "ok "
        yield "done"


class _LocalRecordingProvider(_RecordingProvider):
    name = "recording-fake-local"
    is_local = True


@pytest.fixture
def gateway_module(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from primnox2.models import gateway
    return gateway


def test_cloud_route_scrubs_pii_before_reaching_the_provider(gateway_module, monkeypatch):
    monkeypatch.setattr(mirror, "_pipeline", None)
    provider = _RecordingProvider()
    monkeypatch.setattr(gateway_module, "active_provider", lambda: (provider, "fake-model"))

    secret_email = "realvictim@personal-domain.example"
    messages = [{"role": "user", "content": f"my email is {secret_email}, remember it"}]

    list(gateway_module.stream_completion(messages))

    assert provider.received_messages is not None
    sent_text = " ".join(
        m["content"] for m in provider.received_messages if isinstance(m.get("content"), str)
    )
    assert secret_email not in sent_text, (
        "PII reached a cloud provider's stream() call unscrubbed — this is "
        "the exact failure the Privacy Mirror gate exists to prevent."
    )


def test_local_route_is_never_scrubbed(gateway_module, monkeypatch):
    """Local providers must see the FULL, unmodified payload — scrubbing a
    request that never leaves the device is pure fidelity loss with no
    privacy benefit."""
    provider = _LocalRecordingProvider()
    monkeypatch.setattr(gateway_module, "active_provider", lambda: (provider, "local-model"))

    secret_email = "onlyfor@localmodel.example"
    messages = [{"role": "user", "content": f"my email is {secret_email}"}]

    list(gateway_module.stream_completion(messages))

    assert provider.received_messages is not None
    sent_text = provider.received_messages[0]["content"]
    assert secret_email in sent_text


def test_reply_is_rehydrated_before_leaving_stream_completion(gateway_module, monkeypatch):
    """The other half of the gate: whatever placeholder the cloud model
    echoes back must be restored to the real value before a single token
    reaches the caller — never leaked as a raw §LABEL_n§ token."""
    monkeypatch.setattr(mirror, "_pipeline", None)

    class _EchoingProvider(_RecordingProvider):
        def stream(self, messages, model=None, usage=None):
            self.received_messages = messages
            # Echo back whatever placeholder the scrubber assigned, split
            # across two yields the way a real token stream would arrive.
            content = messages[0]["content"]
            import re
            m = re.search(r"§[A-Z_]+\d+§", content)
            placeholder = m.group(0) if m else "NO_PLACEHOLDER_FOUND"
            half = len(placeholder) // 2
            yield f"got it: {placeholder[:half]}"
            yield placeholder[half:]

    provider = _EchoingProvider()
    monkeypatch.setattr(gateway_module, "active_provider", lambda: (provider, "fake-model"))

    secret = "leak-me-not@example.com"
    messages = [{"role": "user", "content": f"email is {secret}"}]

    out = "".join(gateway_module.stream_completion(messages))
    assert secret in out, "the echoed placeholder was not rehydrated back to the real value"
    assert "§" not in out, "a raw placeholder token leaked to the caller"


def test_scrub_map_output_param_carries_the_reveal(gateway_module, monkeypatch):
    monkeypatch.setattr(mirror, "_pipeline", None)
    provider = _RecordingProvider()
    monkeypatch.setattr(gateway_module, "active_provider", lambda: (provider, "fake-model"))

    messages = [{"role": "user", "content": "email pii@example.com please"}]
    scrub_map: list = []
    list(gateway_module.stream_completion(messages, scrub_map=scrub_map))

    assert len(scrub_map) == 1
    assert scrub_map[0]["original"] == "pii@example.com"
    assert scrub_map[0]["label"] == "EMAIL"


def test_privacy_mirror_disabled_setting_sends_unscrubbed(gateway_module, monkeypatch):
    """The off switch must actually work — settings_service returning "off"
    should skip scrubbing entirely, matching V1's `privacy_mirror_enabled`
    toggle semantics."""
    from primnox2.settings import service as settings_service
    monkeypatch.setattr(settings_service, "get",
                         lambda key, default=None: "off" if key == "privacy.mirror_enabled" else default)
    provider = _RecordingProvider()
    monkeypatch.setattr(gateway_module, "active_provider", lambda: (provider, "fake-model"))

    secret = "shouldnotbescrubbed@example.com"
    messages = [{"role": "user", "content": f"email {secret}"}]
    list(gateway_module.stream_completion(messages))

    assert provider.received_messages[0]["content"] == f"email {secret}"


def test_scrub_failure_fails_open_with_a_warning_not_a_crash(gateway_module, monkeypatch, caplog):
    """If the scrubber itself raises (a bug, a missing dependency), the turn
    must still complete — V1's own documented choice at this exact boundary
    ("log and continue unscrubbed" rather than block the user's message
    entirely). Verified here for the failure path specifically, since a
    swallowed exception is exactly the kind of thing that stops looking
    tested once the happy path is proven."""
    provider = _RecordingProvider()
    monkeypatch.setattr(gateway_module, "active_provider", lambda: (provider, "fake-model"))

    def _boom(*a, **kw):
        raise RuntimeError("simulated scrubber failure")
    monkeypatch.setattr(mirror, "ensure_model_ready", _boom)

    messages = [{"role": "user", "content": "hello"}]
    result = "".join(gateway_module.stream_completion(messages))
    assert result == "ok done"
    assert provider.received_messages == messages
