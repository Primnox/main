"""Provider health, the circuit breaker, and per-model lockout.

Ported and merged from OmniRoute (MIT):

  `src/lib/resilience/adaptiveCircuit.ts`      → `Circuit` / `observe()`
  `src/lib/resilience/modelLockoutSettings.ts` → `Lockout` / `cooldown_ms()`
  `src/lib/db/providers/rateLimit.ts`          → the "until" timestamp idea

OmniRoute keeps these apart because three different subsystems own them there
(a preview route, a settings resolver, a SQLite table). In Primnox they are one
question — *what do we currently know about this endpoint, and should we call
it?* — so they are one module with one lock and one record per candidate.

THE THREE STATES ARE THE POINT. A two-state breaker (open/closed) has no way to
test recovery except by reopening the floodgates, so it either stays open too
long or slams a recovering provider with a full turn's traffic. `half_open`
lets exactly one request through as a probe: if it works the breaker closes, if
it fails it reopens immediately with a longer cooldown — that is the whole of
`observe()`'s failure branch checking `state == "half_open"` before it even
looks at the threshold.

WHAT THIS DELIBERATELY DOES NOT DO. No jitter on the backoff: anti-thundering
-herd matters when a thousand clients retry a shared upstream in lockstep, and
this is one desktop process talking to a provider on its owner's behalf. Adding
randomness would only make the cooldown untestable.

STATE IS PROCESS-LOCAL and resets on restart, unlike OmniRoute's, which
persists cooldowns in SQLite so they survive a token refresh. That is the right
call for a multi-tenant gateway and the wrong one here: a breaker is a claim
about right now, and the usual fix for "my provider is broken" — start Ollama,
paste a new key, reconnect the VPN — happens outside this process, where a
persisted verdict would just be wrong on the next launch.

Everything here logs. `primnox2.routing.health` at DEBUG gives a running
account of every observation; INFO carries the state changes, which are the
lines you actually want when a turn went somewhere surprising.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from . import failures

log = logging.getLogger("primnox2.routing.health")

now_ms = lambda: int(time.time() * 1000)

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

# OmniRoute's DEFAULT_MODEL_LOCKOUT_SETTINGS.errorCodes. A 404 is in the list
# because a model that has been retired answers 404 forever, and hammering it
# once per turn is exactly what the lockout exists to stop.
LOCKOUT_CODES = (403, 404, 429, 502, 503, 504)

# Floors per failure type, seconds. An auth failure gets a long one because
# retrying a rejected credential every thirty seconds is how an account gets
# rate-limited for a problem it does not have.
_FLOOR_S = {
    failures.AUTHENTICATION_ERROR: 300.0,
    failures.PERMISSION_ERROR: 300.0,
    failures.QUOTA_EXHAUSTED: 600.0,
    failures.RATE_LIMIT: 20.0,
    failures.MODEL_UNAVAILABLE: 300.0,
    failures.INVALID_REQUEST: 60.0,
}

# Providers have been seen returning hours in Retry-After. Honouring it beats
# any curve we would invent, but not without a ceiling, or one bad header takes
# a candidate out of the chain for the rest of the session.
RETRY_AFTER_CAP_S = 900.0


@dataclass
class Lockout:
    """OmniRoute's ModelLockoutSettings, resolved from Primnox's tunables."""
    enabled: bool = True
    error_codes: tuple[int, ...] = LOCKOUT_CODES
    base_cooldown_s: float = 30.0
    max_cooldown_s: float = 900.0
    max_backoff_steps: int = 10
    exponential: bool = True
    threshold: int = 2

    @classmethod
    def resolve(cls) -> "Lockout":
        """Read the live tunables, falling back to the defaults above.

        The fallback is not decoration: `health` is imported by the gateway,
        which runs in tests and at boot before `storage.configure()`, and a
        breaker that cannot read its threshold must still work.
        """
        try:
            from ..settings import tunables
            base = float(tunables.get("models.breaker_cooldown_s"))
            settings = cls(
                base_cooldown_s=base,
                # OmniRoute clamps max up to base for the same reason: a cap
                # below the base makes exponential backoff meaningless.
                max_cooldown_s=max(float(tunables.get("models.breaker_cooldown_max_s")), base),
                threshold=int(tunables.get("models.breaker_threshold")),
            )
        except Exception as exc:                              # noqa: BLE001
            log.debug("tunables unavailable (%s); using built-in lockout defaults", exc)
            return cls()
        return settings

    def cooldown_s(self, trips: int, failure_type: str = "",
                   retry_after_s: float | None = None) -> float:
        """How long this candidate sits out, after `trips` consecutive opens."""
        if self.exponential:
            steps = min(max(trips - 1, 0), self.max_backoff_steps)
            cooldown = min(self.base_cooldown_s * (2 ** steps), self.max_cooldown_s)
        else:
            cooldown = self.base_cooldown_s
        cooldown = max(cooldown, _FLOOR_S.get(failure_type, 0.0))
        if retry_after_s is not None:
            # The provider's own number wins when it is longer than ours — it
            # is the only party that actually knows.
            cooldown = max(cooldown, min(retry_after_s, RETRY_AFTER_CAP_S))
        return cooldown


@dataclass
class Circuit:
    """Port of OmniRoute's AdaptiveCircuit, with Primnox's health counters
    folded in — the same record answers "is it open" and "how good is it",
    and splitting them meant two things that could disagree."""
    key: str
    state: str = CLOSED
    failure_count: int = 0
    success_count: int = 0
    trips: int = 0                    # times it has opened; drives the backoff
    opened_at: int = 0
    half_open_at: int = 0
    next_probe_at: int = 0
    reason: str = ""
    last_error: str = ""
    last_failure_at: int = 0
    last_success_at: int = 0

    # Lifetime counters, for the score. Separate from failure_count, which is
    # consecutive and resets — a provider that fails every other call must not
    # look healthy just because the last one worked.
    calls: int = 0
    failures: int = 0
    # EWMA of time to FIRST token, not of the whole reply: a long answer is
    # not a slow provider. OmniRoute averages over a stats window instead;
    # this process is long-lived with no window to average over, so recency is
    # bought with the decay factor rather than by forgetting old rows.
    latency_ms: float | None = None
    error_rate: float = 0.0           # EWMA, 0.0-1.0

    @property
    def open(self) -> bool:
        return self.state == OPEN and now_ms() < self.next_probe_at

    @property
    def opens_in_s(self) -> float:
        return max(0.0, (self.next_probe_at - now_ms()) / 1000.0) if self.next_probe_at else 0.0

    @property
    def terminal(self) -> bool:
        """The last failure was one that time does not fix — a rejected
        credential or an empty balance. OmniRoute calls such a connection
        "terminal" and penalises it harder than a flaky one, because a
        provider that is merely down will come back and this one will not,
        not without someone doing something."""
        return self.reason in (failures.AUTHENTICATION_ERROR,
                               failures.PERMISSION_ERROR,
                               failures.QUOTA_EXHAUSTED)

    @property
    def success_rate(self) -> float | None:
        """Reported alongside the score, never folded into it — see below."""
        if not self.calls:
            return None
        return round((self.calls - self.failures) / self.calls, 4)

    @property
    def health_score(self) -> float:
        """0.0-1.0. Port of OmniRoute's provider score in
        `src/lib/monitoring/providerHealthMatrix.ts`.

        THIS IS A PENALTY MODEL, and that is the part worth not "improving".
        The obvious implementation — score = success rate — is wrong in a way
        that only shows up in combination with `routing.score()`, which already
        multiplies by `reliability` (1 - error rate) and by a latency factor as
        SEPARATE terms. Folding those into the health score too counts each of
        them twice, so a provider with one bad patch gets squared out of the
        chain. OmniRoute keeps them apart deliberately: this number is about
        STATE — is the circuit open, is the credential dead, how many times has
        this thing tripped — and rate/latency ride alongside it as their own
        factors.

        Their penalties, mapped onto one-connection-per-profile:

          circuit open           0.4     (half open: 0.2)
          in cooldown            0.2     their cooldown/total connection share
          terminal credential    0.25    their terminal connection share
          repeat trips           0.05 each, capped at 0.2
        """
        penalty = 0.0
        if self.state == OPEN and self.open:
            penalty += 0.4
        elif self.state == HALF_OPEN:
            penalty += 0.2
        if self.opens_in_s > 0:
            penalty += 0.2
        if self.terminal:
            penalty += 0.25
        penalty += min(0.2, self.trips * 0.05)
        return round(max(0.0, min(1.0, 1.0 - penalty)), 4)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "state": self.state,
            "open": self.open,
            "opens_in_s": round(self.opens_in_s, 1),
            "trips": self.trips,
            "calls": self.calls,
            "failures": self.failures,
            "consecutive_failures": self.failure_count,
            "error_rate": round(self.error_rate, 4),
            "success_rate": self.success_rate,
            "latency_ms": self.latency_ms,
            "health_score": self.health_score,
            "terminal": self.terminal,
            "reason": self.reason,
            "last_error": self.last_error,
            "last_failure_at": self.last_failure_at,
            "last_success_at": self.last_success_at,
        }


_lock = threading.RLock()
_circuits: dict[str, Circuit] = {}


def circuit(key: str) -> Circuit:
    with _lock:
        rec = _circuits.get(key)
        if rec is None:
            rec = _circuits[key] = Circuit(key=key)
            log.debug("new circuit %s", key)
        return rec


def is_open(key: str) -> bool:
    """True when this candidate must be skipped without being called.

    Also performs OmniRoute's `probe` transition: once the cooldown has passed
    the circuit moves to half_open and this returns False, so the next caller
    becomes the probe. Cleared here rather than on success so two threads
    cannot both take the probe slot.
    """
    with _lock:
        rec = _circuits.get(key)
        if rec is None or rec.state != OPEN:
            return False
        if now_ms() >= rec.next_probe_at:
            rec.state = HALF_OPEN
            rec.half_open_at = now_ms()
            log.info("circuit %s -> half_open, sending one probe (was open %.1fs, trips=%d)",
                     key, (rec.half_open_at - rec.opened_at) / 1000.0, rec.trips)
            return False
        log.info("circuit %s open, skipping (%.1fs left, last: %s)",
                 key, rec.opens_in_s, rec.reason or "unknown")
        return True


def opens_in_s(key: str) -> float:
    with _lock:
        rec = _circuits.get(key)
        return rec.opens_in_s if rec else 0.0


def record_success(key: str, latency_ms: float | None = None) -> Circuit:
    """OmniRoute's `observeCircuit(current, "success")`, plus the counters."""
    with _lock:
        rec = circuit(key)
        was = rec.state
        rec.calls += 1
        rec.success_count += 1
        rec.last_success_at = now_ms()
        rec.error_rate = round(rec.error_rate * 0.7, 4)

        if latency_ms is not None:
            rec.latency_ms = (round(latency_ms, 1) if rec.latency_ms is None
                              else round(rec.latency_ms * 0.7 + latency_ms * 0.3, 1))

        rec.state = CLOSED
        rec.failure_count = 0
        rec.opened_at = rec.half_open_at = rec.next_probe_at = 0
        rec.reason = rec.last_error = ""
        # Decayed, not reset. A provider that fails, recovers for one call and
        # fails again is flapping, and a reset would hand it the same short
        # cooldown forever instead of backing off the way the curve intends.
        if rec.trips:
            rec.trips -= 1

        if was != CLOSED:
            log.info("circuit %s -> closed after %s probe succeeded in %sms",
                     key, was, round(latency_ms) if latency_ms else "?")
        else:
            log.debug("%s ok in %sms (score=%.3f, calls=%d)",
                      key, round(latency_ms) if latency_ms else "?",
                      rec.health_score, rec.calls)
        return rec


def record_failure(key: str, failure: failures.Failure,
                   lockout: Lockout | None = None) -> Circuit:
    """OmniRoute's `observeCircuit(current, "failure")`, plus the lockout curve.

    A failure while half_open reopens immediately whatever the threshold says —
    the probe was the test and it failed.
    """
    settings = lockout or Lockout.resolve()
    with _lock:
        rec = circuit(key)
        was = rec.state
        rec.calls += 1
        rec.failures += 1
        rec.failure_count += 1
        rec.success_count = 0
        rec.last_failure_at = now_ms()
        rec.reason = failure.type
        rec.last_error = failure.message[:400]
        rec.error_rate = round(min(1.0, rec.error_rate * 0.7 + 0.3), 4)

        threshold = settings.threshold
        # A rejected credential is not a flake: the same key will be rejected
        # on the next call, so one is enough to stop calling.
        if failure.type in (failures.AUTHENTICATION_ERROR, failures.PERMISSION_ERROR,
                            failures.QUOTA_EXHAUSTED):
            threshold = 1

        should_open = was == HALF_OPEN or rec.failure_count >= threshold
        if not (settings.enabled and should_open):
            log.warning("%s failed (%s) — %d/%d before the breaker opens: %s",
                        key, failure.summary, rec.failure_count, threshold,
                        failure.message[:200])
            return rec

        rec.trips += 1
        cooldown = settings.cooldown_s(rec.trips, failure.type, failure.retry_after_s)
        rec.state = OPEN
        rec.opened_at = now_ms()
        rec.half_open_at = 0
        rec.next_probe_at = rec.opened_at + int(cooldown * 1000)
        log.warning("circuit %s -> OPEN for %.0fs after %s (trip #%d%s): %s",
                    key, cooldown, failure.summary, rec.trips,
                    ", probe failed" if was == HALF_OPEN else "",
                    failure.message[:200])
        return rec


def snapshot() -> list[dict]:
    """Every circuit, worst first — the reason anyone opens this is to find out
    what is broken, so what is broken goes at the top."""
    with _lock:
        rows = [rec.as_dict() for rec in _circuits.values()]
    return sorted(rows, key=lambda r: (not r["open"], r["health_score"]))


def reset(key: str | None = None) -> int:
    """Forget history. What "try it again now" means for someone who has just
    fixed the thing the breaker is waiting out."""
    with _lock:
        if key is None:
            count = len(_circuits)
            _circuits.clear()
        else:
            count = 1 if _circuits.pop(key, None) is not None else 0
    log.info("reset %d circuit(s)%s", count, "" if key is None else f" for {key}")
    return count
