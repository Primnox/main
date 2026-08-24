"""Routing, health and failover — the chain the gate walks.

Covers the three questions the ported OmniRoute logic exists to answer:
what kind of failure was that (failures.py), should this endpoint be called at
all (health.py), and who answers this turn (routing.py + the gate).

The scrubbing tests live in test_privacy_mirror.py and are the reason several
of the fakes here set `is_local = True`: a local provider skips the Privacy
Mirror, which keeps these tests about routing rather than about a model load.
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from primnox2.models import failures, gateway, health, routing   # noqa: E402


@pytest.fixture(autouse=True)
def clean_circuits():
    """Health is process-global by design, so each test starts from nothing."""
    health.reset()
    yield
    health.reset()


class FakeProvider:
    """A local provider, so nothing here touches the Privacy Mirror."""
    name = "fake"
    is_local = True
    # Separate from is_local on purpose: a gateway is off-device and still
    # needs no credential. Tests that set is_local = False set this too when
    # they mean "cloud endpoint that demands a key".
    requires_key = False

    def __init__(self, base_url="http://127.0.0.1:9/v1", tokens=("hello ", "world"),
                 raises=None, raise_after=0):
        self.base_url = base_url
        self.api_key = ""
        self.tokens = tokens
        self.raises = raises
        self.raise_after = raise_after
        self.calls = 0

    def stream(self, messages, model=None, usage=None, thinking=False, on_thinking=None):
        self.calls += 1
        for i, tok in enumerate(self.tokens):
            if self.raises is not None and i == self.raise_after:
                raise self.raises
            yield tok
        if self.raises is not None and self.raise_after >= len(self.tokens):
            raise self.raises


def http_error(status: int, body: str = "", retry_after: str | None = None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://p.example/v1", status, body, headers, None)


def candidate(label, provider, model="m"):
    return routing.Candidate(label=label, provider=provider, model=model)


def chain_of(*cands):
    def _chain(limit=None):
        for c in cands:
            yield c
    return _chain


# ── Classification (port of failureClassification.ts) ────────────────────────
@pytest.mark.parametrize("status, message, expected", [
    (401, "Invalid API key", failures.AUTHENTICATION_ERROR),
    (403, "forbidden", failures.PERMISSION_ERROR),
    (429, "Rate limit reached", failures.RATE_LIMIT),
    (429, "You have insufficient balance", failures.QUOTA_EXHAUSTED),
    (408, "", failures.TIMEOUT),
    (504, "", failures.TIMEOUT),
    (500, "internal", failures.PROVIDER_5XX),
    (503, "unavailable", failures.PROVIDER_5XX),
    (400, "invalid request", failures.INVALID_REQUEST),
    (404, "model not found", failures.MODEL_UNAVAILABLE),
    (None, "ECONNREFUSED", failures.NETWORK_ERROR),
    (None, "something nobody predicted", failures.UNKNOWN),
])
def test_failures_are_named_the_way_omniroute_names_them(status, message, expected):
    assert failures.classify("p", "m", status=status, message=message).type == expected


def test_a_429_about_money_is_not_a_rate_limit():
    """The distinction the whole chain turns on: waiting fixes one and not the
    other, and retrying an empty balance spends the turn's budget on the single
    provider that certainly cannot answer."""
    rate = failures.classify("p", "m", status=429, message="rate limit, slow down")
    quota = failures.classify("p", "m", status=429, message="credits exhausted")
    assert rate.retryable and not quota.retryable


def test_status_beats_message_text():
    """A 401 whose body happens to say 'timeout' is still an auth failure."""
    assert failures.classify("p", "m", status=401,
                             message="request timed out").type == failures.AUTHENTICATION_ERROR


def test_retry_after_is_read_off_the_header():
    failure = failures.from_exception(http_error(429, retry_after="42"), "p", "m")
    assert failure.retry_after_s == 42.0


def test_an_http_date_retry_after_is_ignored_not_guessed():
    failure = failures.from_exception(
        http_error(429, retry_after="Wed, 21 Oct 2026 07:28:00 GMT"), "p", "m")
    assert failure.retry_after_s is None
    assert failure.type == failures.RATE_LIMIT


def test_a_malformed_request_stops_the_chain():
    """Primnox's own bug. Every provider rejects it identically, so trying five
    turns one clear error into five confusing ones."""
    bad = failures.classify("p", "m", status=400, message="invalid request")
    assert not failures.should_failover(bad)


def test_a_rejected_key_does_not_stop_the_chain():
    """Primnox's documented divergence from OmniRoute: all the accounts belong
    to one person, so another provider should answer."""
    dead = failures.classify("p", "m", status=401, message="invalid api key")
    assert failures.should_failover(dead)


# ── The breaker (port of adaptiveCircuit.ts) ─────────────────────────────────
def test_the_breaker_opens_on_the_threshold_and_not_before():
    lockout = health.Lockout(threshold=2, base_cooldown_s=30)
    failure = failures.classify("p", "m", status=500, message="boom")

    assert health.record_failure("k", failure, lockout).state == health.CLOSED
    assert not health.is_open("k")
    assert health.record_failure("k", failure, lockout).state == health.OPEN
    assert health.is_open("k")


def test_a_rejected_credential_opens_it_immediately():
    lockout = health.Lockout(threshold=5, base_cooldown_s=30)
    dead = failures.classify("p", "m", status=401, message="invalid api key")
    assert health.record_failure("k", dead, lockout).state == health.OPEN


def test_cooldown_doubles_per_trip_and_respects_the_ceiling():
    lockout = health.Lockout(base_cooldown_s=10, max_cooldown_s=45, threshold=1)
    assert lockout.cooldown_s(1) == 10
    assert lockout.cooldown_s(2) == 20
    assert lockout.cooldown_s(3) == 40
    assert lockout.cooldown_s(4) == 45          # capped, not 80
    assert lockout.cooldown_s(99) == 45


def test_a_longer_retry_after_wins_over_our_curve():
    lockout = health.Lockout(base_cooldown_s=10, max_cooldown_s=1000, threshold=1)
    assert lockout.cooldown_s(1, failures.RATE_LIMIT, retry_after_s=120) == 120
    # ...but a provider claiming three hours does not get three hours.
    assert lockout.cooldown_s(1, failures.RATE_LIMIT,
                              retry_after_s=10_800) == health.RETRY_AFTER_CAP_S


def test_expired_cooldown_goes_half_open_and_one_probe_gets_through():
    lockout = health.Lockout(threshold=1, base_cooldown_s=30)
    health.record_failure("k", failures.classify("p", "m", status=500), lockout)
    circuit = health.circuit("k")
    circuit.next_probe_at = health.now_ms() - 1          # cooldown has passed

    assert not health.is_open("k")
    assert health.circuit("k").state == health.HALF_OPEN


def test_a_failed_probe_reopens_immediately_whatever_the_threshold():
    lockout = health.Lockout(threshold=10, base_cooldown_s=30)
    circuit = health.circuit("k")
    circuit.state = health.HALF_OPEN
    assert health.record_failure("k", failures.classify("p", "m", status=500),
                                 lockout).state == health.OPEN


def test_success_closes_it_and_decays_the_trip_count():
    lockout = health.Lockout(threshold=1, base_cooldown_s=30)
    health.record_failure("k", failures.classify("p", "m", status=500), lockout)
    health.record_failure("k", failures.classify("p", "m", status=500), lockout)
    assert health.circuit("k").trips == 2

    circuit = health.record_success("k", latency_ms=120)
    assert circuit.state == health.CLOSED
    # Decayed rather than reset: a provider that recovers for exactly one call
    # and fails again is flapping, and must not get the shortest cooldown back.
    assert circuit.trips == 1


def test_health_score_penalises_state_not_success_rate():
    """The ported penalty model. Success rate and latency are reported
    separately and multiplied in by routing.score(); folding them in here too
    would count each of them twice."""
    circuit = health.circuit("k")
    assert circuit.health_score == 1.0

    health.record_failure("k", failures.classify("p", "m", status=500),
                          health.Lockout(threshold=1, base_cooldown_s=60))
    open_score = health.circuit("k").health_score
    assert open_score < 0.5                      # 0.4 open + 0.2 cooldown + trip

    health.reset("k")
    health.record_failure("k", failures.classify("p", "m", status=401, message="bad key"),
                          health.Lockout(threshold=1, base_cooldown_s=60))
    # A dead credential is penalised harder than a provider that is merely down.
    assert health.circuit("k").health_score < open_score


# ── Scoring (port of adaptiveRouting.ts) ─────────────────────────────────────
def test_an_open_circuit_scores_zero_and_is_ineligible():
    """The property that makes the multiplicative model worth porting: no other
    factor can carry a candidate whose breaker is open."""
    cand = candidate("p", FakeProvider())
    health.record_failure(cand.key, failures.classify("p", "m", status=500),
                          health.Lockout(threshold=1, base_cooldown_s=60))
    explanation = routing.score(cand)
    assert explanation.score == 0.0
    assert not explanation.eligible
    assert explanation.factors["circuit"] == 0.0


def test_every_factor_is_reported_for_debugging():
    explanation = routing.score(candidate("p", FakeProvider()))
    assert set(explanation.factors) == {
        "capability", "allocation", "health", "reliability",
        "latency", "preference", "cost", "quota", "circuit"}


def test_ranking_puts_the_healthier_provider_first():
    good, bad = candidate("good", FakeProvider()), candidate("bad", FakeProvider("http://127.0.0.1:8/v1"))
    health.record_failure(bad.key, failures.classify("bad", "m", status=500),
                          health.Lockout(threshold=1, base_cooldown_s=60))
    assert [c.label for c, _ in routing.rank([bad, good])] == ["good", "bad"]


# ── The gate ─────────────────────────────────────────────────────────────────
def test_a_dead_first_provider_fails_over_before_any_token_is_seen(monkeypatch):
    dead = FakeProvider(raises=http_error(503, "unavailable"))
    alive = FakeProvider(base_url="http://127.0.0.1:8/v1", tokens=("second ", "answer"))
    monkeypatch.setattr(routing, "chain", chain_of(candidate("dead", dead),
                                                   candidate("alive", alive)))

    route: list = []
    assert "".join(gateway.stream_completion([{"role": "user", "content": "hi"}],
                                             route=route)) == "second answer"
    assert [(r["provider"], r["status"]) for r in route] == [("dead", "failed"), ("alive", "ok")]
    assert route[0]["reason"] == failures.PROVIDER_5XX


def test_a_provider_that_dies_mid_stream_is_not_failed_over(monkeypatch):
    """The commit point. Swapping providers after a token has shipped would
    splice two half-answers into one reply with no seam anyone could see."""
    flaky = FakeProvider(tokens=("half ", "an ", "answer"),
                         raises=http_error(500, "died"), raise_after=2)
    spare = FakeProvider(base_url="http://127.0.0.1:8/v1", tokens=("whole answer",))
    monkeypatch.setattr(routing, "chain", chain_of(candidate("flaky", flaky),
                                                   candidate("spare", spare)))

    got = []
    with pytest.raises(urllib.error.HTTPError):
        for token in gateway.stream_completion([{"role": "user", "content": "hi"}]):
            got.append(token)
    assert "".join(got) == "half an "
    assert spare.calls == 0


def test_an_open_breaker_is_skipped_without_being_called(monkeypatch):
    benched = FakeProvider(tokens=("should not run",))
    alive = FakeProvider(base_url="http://127.0.0.1:8/v1", tokens=("ok",))
    first, second = candidate("benched", benched), candidate("alive", alive)
    health.record_failure(first.key, failures.classify("benched", "m", status=500),
                          health.Lockout(threshold=1, base_cooldown_s=600))
    monkeypatch.setattr(routing, "chain", chain_of(first, second))

    route: list = []
    assert "".join(gateway.stream_completion([{"role": "user", "content": "hi"}],
                                             route=route)) == "ok"
    assert benched.calls == 0
    assert route[0]["status"] == "skipped" and route[0]["reason"] == "circuit_open"


def test_a_skipped_candidate_does_not_spend_the_attempt_budget(monkeypatch):
    """Being skipped is not an attempt. If it were, one open breaker plus a
    budget of two would leave a single real attempt for the whole chain."""
    benched = FakeProvider(tokens=("no",))
    dead = FakeProvider(base_url="http://127.0.0.1:8/v1", raises=http_error(503))
    alive = FakeProvider(base_url="http://127.0.0.1:7/v1", tokens=("yes",))
    a, b, c = candidate("benched", benched), candidate("dead", dead), candidate("alive", alive)
    health.record_failure(a.key, failures.classify("benched", "m", status=500),
                          health.Lockout(threshold=1, base_cooldown_s=600))
    monkeypatch.setattr(routing, "chain", chain_of(a, b, c))
    monkeypatch.setattr(gateway, "_failover_attempts", lambda: 2)

    assert "".join(gateway.stream_completion([{"role": "user", "content": "hi"}])) == "yes"


def test_a_malformed_request_is_raised_rather_than_retried_everywhere(monkeypatch):
    broken = FakeProvider(raises=http_error(400, "invalid request"))
    spare = FakeProvider(base_url="http://127.0.0.1:8/v1", tokens=("unused",))
    monkeypatch.setattr(routing, "chain", chain_of(candidate("broken", broken),
                                                   candidate("spare", spare)))

    with pytest.raises(urllib.error.HTTPError):
        list(gateway.stream_completion([{"role": "user", "content": "hi"}]))
    assert spare.calls == 0


def test_when_everything_fails_the_error_names_the_users_own_provider(monkeypatch):
    """The first failure is raised, not the last: 'your Groq key is rejected'
    beats a connection error from the third fallback they never chose."""
    chosen = FakeProvider(raises=http_error(401, "invalid api key"))
    other = FakeProvider(base_url="http://127.0.0.1:8/v1", raises=http_error(503, "down"))
    monkeypatch.setattr(routing, "chain", chain_of(candidate("chosen", chosen),
                                                   candidate("other", other)))

    with pytest.raises(RuntimeError, match="chosen"):
        list(gateway.stream_completion([{"role": "user", "content": "hi"}]))


def test_failover_can_be_turned_off_entirely(monkeypatch):
    dead = FakeProvider(raises=http_error(503))
    spare = FakeProvider(base_url="http://127.0.0.1:8/v1", tokens=("unused",))
    monkeypatch.setattr(gateway, "_failover_attempts", lambda: 1)
    monkeypatch.setattr(routing, "chain",
                        lambda limit=None: iter([candidate("dead", dead)] if limit == 1
                                                else [candidate("dead", dead),
                                                      candidate("spare", spare)]))

    with pytest.raises(urllib.error.HTTPError):
        list(gateway.stream_completion([{"role": "user", "content": "hi"}]))
    assert spare.calls == 0


def test_cancellation_is_not_recorded_as_a_provider_failure(monkeypatch):
    """The user pressed stop. Benching a healthy provider for that would make
    the next turn slower for no reason."""
    cancelled = FakeProvider(raises=KeyboardInterrupt())
    cand = candidate("cancelled", cancelled)
    monkeypatch.setattr(routing, "chain", chain_of(cand))

    with pytest.raises(KeyboardInterrupt):
        list(gateway.stream_completion([{"role": "user", "content": "hi"}]))
    assert health.circuit(cand.key).failures == 0


def test_a_local_session_never_falls_back_to_the_cloud(monkeypatch):
    """The trust boundary. Answering a local outage by shipping the
    conversation to a hosted API would be the worst thing this chain could do,
    and it would do it silently, mid-turn."""
    monkeypatch.setattr(routing, "head_candidate",
                        lambda: routing.Candidate("active", FakeProvider(), "m", origin="active"))
    seen = {}

    def spy(allow_cloud):
        seen["allow_cloud"] = allow_cloud
        return []

    monkeypatch.setattr(routing, "fallback_candidates", spy)
    list(routing.chain(3))
    assert seen["allow_cloud"] is False


def test_a_cloud_session_may_fall_back_to_a_local_model(monkeypatch):
    """The other direction only ever reduces what leaves the device."""
    cloud = FakeProvider(base_url="https://api.example.com/v1")
    cloud.is_local = False
    monkeypatch.setattr(routing, "head_candidate",
                        lambda: routing.Candidate("active", cloud, "m", origin="active"))
    seen = {}
    monkeypatch.setattr(routing, "fallback_candidates",
                        lambda allow_cloud: seen.setdefault("allow_cloud", allow_cloud) and [])
    list(routing.chain(3))
    assert seen["allow_cloud"] is True


def test_a_missing_key_on_the_active_provider_is_named_precisely(monkeypatch):
    """Loud for the profile the user chose, silent for fallbacks — a missing
    key is the answer they need for one and noise for the other."""
    keyless = FakeProvider(base_url="https://api.example.com/v1")
    keyless.is_local = False
    keyless.requires_key = True
    monkeypatch.setattr(routing, "chain", chain_of(candidate("active", keyless)))

    with pytest.raises(RuntimeError, match="No API key is configured"):
        list(gateway.stream_completion([{"role": "user", "content": "hi"}]))
    assert keyless.calls == 0


def test_the_route_log_records_latency_for_the_provider_that_answered(monkeypatch):
    monkeypatch.setattr(routing, "chain", chain_of(candidate("only", FakeProvider())))
    route: list = []
    list(gateway.stream_completion([{"role": "user", "content": "hi"}], route=route))
    assert route[0]["status"] == "ok" and "ms" in route[0]
    assert route[0]["failed_over"] is False


# ── The trust boundary: a localhost gateway is not a local model ─────────────
"""OmniRoute listens on 127.0.0.1 and forwards to 290 cloud providers. Every
test below exists because the URL heuristic alone answers "local" for it, and
"local" is what turns the Privacy Mirror off."""


def test_a_gateway_on_localhost_is_not_treated_as_on_device():
    """The whole hazard in one assertion. The address says loopback; the
    destination is somebody else's server."""
    assert gateway.on_device_for("gateway", "http://127.0.0.1:20128/v1") is False
    assert gateway.on_device_for("ollama", "http://127.0.0.1:11434/v1") is True
    assert gateway.on_device_for("local", "http://127.0.0.1:1234/v1") is True
    assert gateway.on_device_for("cloud", "https://api.openai.com/v1") is False


def test_an_unclassified_endpoint_still_falls_back_to_the_url():
    """A profile saved before `kind` existed, or one typed in by hand."""
    assert gateway.on_device_for("", "http://127.0.0.1:1234/v1") is True
    assert gateway.on_device_for("", "https://api.example.com/v1") is False


def test_the_provider_object_honours_the_trust_class_over_its_url():
    forwarding = gateway.OpenAICompatProvider("http://127.0.0.1:20128/v1", "", "auto",
                                              on_device=False)
    assert forwarding.is_local is False
    real_local = gateway.OpenAICompatProvider("http://127.0.0.1:11434/v1", "", "qwen")
    assert real_local.is_local is True


def test_a_gateway_payload_is_scrubbed_like_any_cloud_provider(monkeypatch):
    """The consequence that matters: if this regresses, prompts reach 290
    providers with the PII still in them."""
    seen = {}

    def fake_scrub(messages):
        seen["scrubbed"] = True
        return None, messages

    monkeypatch.setattr(gateway, "_scrub_outbound", fake_scrub)
    forwarding = FakeProvider(base_url="http://127.0.0.1:20128/v1", tokens=("ok",))
    forwarding.is_local = False          # off-device: scrubbed
    forwarding.requires_key = False      # ...but keyless, like the real thing
    monkeypatch.setattr(routing, "chain", chain_of(candidate("OmniRoute", forwarding, "auto")))

    list(gateway.stream_completion([{"role": "user", "content": "my email is a@b.example"}]))
    assert seen.get("scrubbed"), (
        "a localhost gateway skipped the Privacy Mirror — the address was "
        "trusted instead of the destination")


def test_a_gateway_session_may_still_fall_back_to_the_cloud(monkeypatch):
    """The other half: OmniRoute is a cloud head, so the chain is not confined
    to this machine the way a real local session is."""
    forwarding = FakeProvider(base_url="http://127.0.0.1:20128/v1")
    forwarding.is_local = False
    monkeypatch.setattr(routing, "head_candidate",
                        lambda: routing.Candidate("active", forwarding, "auto", origin="active"))
    seen = {}
    monkeypatch.setattr(routing, "fallback_candidates",
                        lambda allow_cloud: seen.setdefault("allow_cloud", allow_cloud) and [])
    list(routing.chain(3))
    assert seen["allow_cloud"] is True


def test_a_keyless_gateway_is_called_and_a_keyless_cloud_endpoint_is_not():
    """The two questions, kept apart. OmniRoute serves its free tier with
    nothing configured; api.openai.com with no key is a 401 with extra steps."""
    assert gateway.requires_key_for("gateway", "http://127.0.0.1:20128/v1") is False
    assert gateway.requires_key_for("cloud", "https://api.openai.com/v1") is True
    assert gateway.requires_key_for("ollama", "http://127.0.0.1:11434/v1") is False
    # Unclassified falls back to the address, which is the old behaviour.
    assert gateway.requires_key_for("", "https://api.example.com/v1") is True
