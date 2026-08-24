"""Which provider answers this turn, and why.

Ported from OmniRoute (MIT) — `src/lib/routing/adaptiveRouting.ts`. The scoring
model is theirs and is kept faithfully, including the part that looks odd:
every factor MULTIPLIES. A weighted sum would let a great capability score
carry a provider whose circuit is open; a product cannot, because any factor at
zero takes the whole score to zero. That is the property that makes one
`score > 0` test enough to answer "may this provider serve this turn".

Primnox has no quota ledger and no cost model, so `quota` and `cost` are
present, documented, and pinned at 1.0 rather than deleted — they are where a
future free-tier tracker plugs in, and removing them would mean re-deriving
this formula to add it back.

WHAT ORDERING DOES AND DOES NOT DECIDE. The active profile is always tried
first, whatever it scores. The user picked it; quietly demoting the model
someone chose because it was slow once is not failover, it is the app
overruling them. Scoring orders the FALLBACKS — which is exactly where nobody
has expressed a preference and the app should use what it knows.

Every decision is logged with its factors at DEBUG, and the chosen chain at
INFO. When a turn goes somewhere surprising, `primnox2.routing` is the log that
says why, in one line per candidate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import health

log = logging.getLogger("primnox2.routing")

ALLOW, WARN, DENY = "allow", "warn", "deny"

# OmniRoute's ProviderQuotaStatus. Primnox reports "unknown" for everything
# until something tracks free-tier balances; the factors are kept so that when
# it does, this table is the only thing that changes.
QUOTA_FACTOR = {
    "exhausted": 0.0,
    "approaching_limit": 0.65,
    "unavailable": 0.9,
    "unknown": 1.0,
    "healthy": 1.0,
}


def _clamp(value: float | None, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return fallback


def _latency_factor(latency_ms: float | None) -> float:
    """OmniRoute's latencyFactor, rescaled for a desktop.

    Theirs floors at 0.4 over a 50-second horizon, which is right for a gateway
    fronting batch traffic. Here, 3 seconds to first token is already the point
    where a user assumes it is broken, so the curve has to be steeper or it
    never actually influences an ordering.
    """
    if latency_ms is None:
        return 1.0
    return max(0.4, 1.0 - min(latency_ms, 10_000.0) / 12_000.0)


@dataclass
class Candidate:
    """One provider the gate is allowed to call for a turn."""
    label: str                 # profile name, or "active" for the live one
    provider: object
    model: str
    origin: str = "profile"    # "active" | "profile"
    capability: float = 1.0
    preference: float = 0.5
    cost: float = 1.0
    quota: str = "unknown"
    allocation: str = ALLOW

    @property
    def key(self) -> str:
        """What health is recorded against: endpoint plus model, not the
        profile name. Renaming a profile must not wipe its history, and two
        profiles pointing at one endpoint share that endpoint's fate."""
        return f"{getattr(self.provider, 'base_url', 'local')}|{self.model}"

    @property
    def is_local(self) -> bool:
        return bool(getattr(self.provider, "is_local", False))

    @property
    def api_key(self) -> str:
        return getattr(self.provider, "api_key", "")

    @property
    def requires_key(self) -> bool:
        """Not the same question as `is_local`. A gateway is off-device and
        still needs no credential — see gateway.requires_key_for()."""
        return bool(getattr(self.provider, "requires_key", not self.is_local))


@dataclass
class Explanation:
    """OmniRoute's RoutingExplanation. The `factors` dict is the debugging
    surface: when a provider was skipped, exactly one number in it is zero."""
    label: str
    model: str
    key: str
    score: float
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    factors: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"provider": self.label, "model": self.model, "key": self.key,
                "score": self.score, "eligible": self.eligible,
                "reasons": self.reasons, "factors": self.factors}


def score(candidate: Candidate) -> Explanation:
    """Port of `scoreCandidate`. Multiplicative, deliberately — see the module
    docstring."""
    rec = health.circuit(candidate.key)

    capability = _clamp(candidate.capability)
    allocation = 0.0 if candidate.allocation == DENY else 0.85 if candidate.allocation == WARN else 1.0
    health_factor = _clamp(rec.health_score, 0.5)
    reliability = 1.0 - _clamp(rec.error_rate)
    latency = _latency_factor(rec.latency_ms)
    preference = _clamp(candidate.preference, 0.5)
    cost = _clamp(candidate.cost, 1.0)
    quota = QUOTA_FACTOR.get(candidate.quota, 1.0)
    circuit = 0.0 if rec.state == health.OPEN and rec.open else 0.5 if rec.state == health.HALF_OPEN else 1.0

    total = round(capability * allocation * health_factor * reliability * latency
                  * preference * cost * quota * circuit, 6)

    reasons = [
        "capability match" if capability >= 0.8 else "partial capability match",
        {"allow": "allocation permitted", "warn": "allocation permitted with warning"}
        .get(candidate.allocation, "allocation denied"),
        "provider healthy" if health_factor >= 0.8 else "provider health degraded",
        f"circuit {rec.state}",
        f"quota {candidate.quota}",
    ]
    if rec.latency_ms is not None:
        reasons.append(f"latency {round(rec.latency_ms)}ms")
    if rec.calls:
        reasons.append(f"{round(rec.error_rate * 100)}% recent errors over {rec.calls} calls")

    explanation = Explanation(
        label=candidate.label, model=candidate.model, key=candidate.key,
        score=total,
        eligible=(total > 0 and candidate.allocation != DENY
                  and not (rec.state == health.OPEN and rec.open)
                  and candidate.quota != "exhausted"),
        reasons=reasons,
        factors={"capability": capability, "allocation": allocation, "health": health_factor,
                 "reliability": round(reliability, 4), "latency": round(latency, 4),
                 "preference": preference, "cost": cost, "quota": quota, "circuit": circuit},
    )
    log.debug("scored %s (%s) = %.6f eligible=%s factors=%s",
              candidate.label, candidate.model, total, explanation.eligible,
              explanation.factors)
    return explanation


def rank(candidates: list[Candidate]) -> list[tuple[Candidate, Explanation]]:
    """Port of `rankCandidates`: score everything, best first.

    Ineligible candidates are kept in the list rather than filtered out. The
    gate skips them anyway, and a caller asking "why did nothing answer" needs
    to see the zero and the factor that caused it — a filtered list can only
    say "no candidates", which is the least useful sentence in an outage.
    """
    scored = [(c, score(c)) for c in candidates]
    scored.sort(key=lambda pair: pair[1].score, reverse=True)
    return scored


# ── Building the chain ───────────────────────────────────────────────────────
def _capability_score(base_url: str, model: str) -> float:
    """How well this model matches what a turn generally needs.

    Reuses the capability registry the gateway already keeps, rather than a
    second table: tool calling and context window are what actually differ
    between the models a user has configured, and a model that can only emulate
    tool calls really is a worse pick when a better one is available.
    """
    from .gateway import capabilities_for
    caps = capabilities_for(base_url, model)
    tools = {"native": 1.0, "emulated": 0.7, "none": 0.4}.get(caps.tool_calling, 0.7)
    window = min(caps.context_window, 200_000) / 200_000
    return round(tools * 0.75 + window * 0.25, 4)


def _provider_for(base_url: str, api_type: str, api_key: str, model: str, kind: str = ""):
    from .gateway import (AnthropicProvider, OpenAICompatProvider,
                          on_device_for, requires_key_for)
    cls = AnthropicProvider if api_type == "anthropic" else OpenAICompatProvider
    return cls(base_url, api_key, model, on_device_for(kind, base_url),
               requires_key_for(kind, base_url))


def head_candidate() -> Candidate:
    """The active provider — always first, always tried, never re-ordered."""
    from .gateway import active_provider
    provider, model = active_provider()
    return Candidate(
        label="active", provider=provider, model=model, origin="active",
        capability=_capability_score(getattr(provider, "base_url", "local"), model),
        preference=1.0,
    )


def fallback_candidates(allow_cloud: bool) -> list[Candidate]:
    """Saved profiles other than the active one, best-first.

    THE TRUST BOUNDARY LIVES HERE. A local provider never falls back to a cloud
    one. Someone running Ollama chose that, and answering an outage by shipping
    their conversation to a hosted API would be the worst thing this chain
    could do — silently, mid-turn. Cloud → local is allowed, because that
    direction only ever reduces what leaves the device.
    """
    try:
        from ..settings import models as profile_store
        rows = profile_store.chain()
    except Exception as exc:                                  # noqa: BLE001
        log.debug("no profile store (%s); the chain is the active provider alone", exc)
        return []

    from .gateway import on_device_for
    out: list[Candidate] = []
    for row in rows:
        base = str(row.get("base_url") or "").strip()
        model = str(row.get("model") or "").strip()
        name = str(row.get("name") or "").strip()
        if not base or not model:
            log.debug("profile %r is not a usable candidate (base_url=%r model=%r)",
                      name, base, model)
            continue

        # `kind`, not the URL — a gateway listening on 127.0.0.1 is a cloud
        # destination wearing a local address, and treating it as on-device
        # here would let a local session fall back to it and skip scrubbing.
        kind = str(row.get("kind") or "")
        local = on_device_for(kind, base)
        if not local and not allow_cloud:
            log.info("excluding cloud profile %r: the active provider is local, "
                     "and a local session never falls back off-device", name)
            continue

        from .gateway import requires_key_for
        needs_key = requires_key_for(kind, base)
        key = profile_store.get_key(name) if needs_key else ""
        if needs_key and not key:
            # No credential, so this would be a 401 with extra steps. Silent
            # here and loud for the ACTIVE profile, where a missing key is the
            # answer the user actually needs to hear.
            log.debug("skipping profile %r: no key in the keyring", name)
            continue

        out.append(Candidate(
            label=name,
            provider=_provider_for(base, str(row.get("api_type") or "openai"), key, model, kind),
            # OmniRoute answers on its free tier with nothing configured, so a
            # keyless gateway belongs in the chain; a keyless cloud endpoint
            # does not, and was filtered out above.
            model=model, origin="profile",
            capability=_capability_score(base, model),
            # Local costs nothing to run, so it wins a tie against a paid
            # endpoint of equal health. It is a tiebreak, not a thumb on the
            # scale: 1.0 vs 0.9 cannot outrank a real health difference.
            cost=1.0 if local else 0.9,
            preference=0.5,
        ))

    ranked = rank(out)
    if ranked:
        log.info("fallback order: %s", ", ".join(
            f"{c.label}({e.score:.3f}{'' if e.eligible else ', ineligible'})"
            for c, e in ranked))
    return [c for c, _ in ranked]


def chain(limit: int | None = None):
    """The active provider, then the ranked fallbacks. Lazily.

    Laziness is load-bearing: `fallback_candidates()` reads the OS credential
    store, and a turn that succeeds on the first provider — nearly all of them
    — must not pay a keyring round-trip per saved profile to build a list it
    never looks at.
    """
    head = head_candidate()
    log.debug("head candidate: %s (%s) local=%s", head.label, head.model, head.is_local)
    yield head

    if limit is not None and limit <= 1:
        log.debug("failover disabled (models.failover_attempts=%s)", limit)
        return
    yield from fallback_candidates(allow_cloud=not head.is_local)
