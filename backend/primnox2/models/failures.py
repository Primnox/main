"""What kind of failure was that, and should another provider try?

Ported from OmniRoute (MIT) — `src/lib/resilience/failureClassification.ts`
and the failover policy from `src/lib/routing/adaptiveRouting.ts`. The taxonomy
is theirs, deliberately: ten named failure types, matched on HTTP status first
and on the error text second, because providers are wildly inconsistent about
which status they attach to a given complaint and the message is often the only
thing that distinguishes "your key is wrong" from "you are out of credit".

WHY A CLASSIFIER AT ALL. Without one there are two possible behaviours and both
are wrong: retry everything, and a rejected API key becomes a retry storm across
every provider you own; retry nothing, and a single 503 fails a turn that the
next provider would have answered in a second. The whole value of a fallback
chain is in the distinctions this module draws.

WHAT PRIMNOX CHANGED. One thing, and it is a deliberate divergence from the
port: `should_failover()` here allows a chain to advance past an authentication
or quota failure, where OmniRoute stops. OmniRoute is a shared gateway whose
operator must be told their credential is broken rather than have the cost
quietly moved to a different account; Primnox is one person's desktop, all the
accounts are theirs, and "Anthropic rejected your key so I used Ollama instead,
and here is the banner saying so" is the behaviour that keeps them working. The
failure is still recorded, still logged, and still surfaced in `route`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger("primnox2.routing.failures")

# The ten types, exactly as OmniRoute names them. Keeping their spelling means
# their dashboards, their docs and any future port of their analytics all still
# describe the same thing this module produces.
AUTHENTICATION_ERROR = "authentication_error"
RATE_LIMIT = "rate_limit"
QUOTA_EXHAUSTED = "quota_exhausted"
TIMEOUT = "timeout"
NETWORK_ERROR = "network_error"
PROVIDER_5XX = "provider_5xx"
INVALID_REQUEST = "invalid_request"
MODEL_UNAVAILABLE = "model_unavailable"
PERMISSION_ERROR = "permission_error"
UNKNOWN = "unknown"

_AUTH_RE = re.compile(r"invalid.*(key|token)|unauthori[sz]ed|forbidden")
_TIMEOUT_RE = re.compile(r"timeout|timed out|etimedout")
_RATE_RE = re.compile(r"rate.?limit|too many requests|retry.?after")
_QUOTA_RE = re.compile(r"quota|insufficient balance|credits exhausted|balance is \$0")
_INVALID_RE = re.compile(r"invalid request|malformed|unsupported parameter")
_MODEL_RE = re.compile(r"model unavailable|model not found|unknown model")
_NETWORK_RE = re.compile(r"network|econnreset|econnrefused|enotfound|fetch failed|socket")


@dataclass
class Failure:
    """One provider's refusal, named."""
    type: str
    retryable: bool
    provider: str
    model: str = ""
    status: int | None = None
    retry_after_s: float | None = None
    message: str = ""

    @property
    def summary(self) -> str:
        bits = [self.type]
        if self.status is not None:
            bits.append(f"HTTP {self.status}")
        if self.retry_after_s is not None:
            bits.append(f"retry-after {self.retry_after_s}s")
        return " | ".join(bits)


def classify(provider: str, model: str = "", status: int | None = None,
             code: str = "", message: str = "",
             retry_after_s: float | None = None) -> Failure:
    """Name a failure. Status first, then the message text.

    The order matters and is OmniRoute's: a 401 is authentication even if its
    body happens to mention the word "timeout", because the status is the
    provider's own structured answer and the prose is marketing.
    """
    text = (message or "").strip() or "Provider request failed"
    normalized = f"{code or ''} {text}".lower()
    kind, retryable = UNKNOWN, False

    if status in (401, 403) or _AUTH_RE.search(normalized):
        kind = (PERMISSION_ERROR if status == 403 or "permission" in normalized
                else AUTHENTICATION_ERROR)
    elif status in (408, 504) or _TIMEOUT_RE.search(normalized):
        kind, retryable = TIMEOUT, True
    elif status == 429 or _RATE_RE.search(normalized):
        # A 429 that mentions credit is not a rate limit — waiting will not fix
        # an empty balance, and retrying it is how a chain wastes its budget on
        # the one provider that definitely cannot answer.
        kind = QUOTA_EXHAUSTED if _QUOTA_RE.search(normalized) else RATE_LIMIT
        retryable = kind == RATE_LIMIT
    elif status is not None and status >= 500:
        kind, retryable = PROVIDER_5XX, True
    elif status == 400 or _INVALID_RE.search(normalized):
        kind = INVALID_REQUEST
    elif status == 404 or _MODEL_RE.search(normalized):
        kind = MODEL_UNAVAILABLE
    elif _NETWORK_RE.search(normalized):
        kind, retryable = NETWORK_ERROR, True

    failure = Failure(type=kind, retryable=retryable, provider=provider, model=model,
                      status=status, retry_after_s=retry_after_s, message=text[:500])
    log.debug("classified %s/%s as %s (retryable=%s): %s",
              provider, model or "?", kind, retryable, text[:200])
    return failure


def from_exception(exc: BaseException, provider: str, model: str = "") -> Failure:
    """Classify a Python exception the way the TS port classifies a fetch error.

    urllib raises three different shapes for what a browser would report as one
    thing, so the status, the code and the message are pulled out here and the
    actual decision is left to `classify()` — one place, one table.
    """
    import urllib.error

    status: int | None = None
    retry_after: float | None = None
    code = type(exc).__name__

    if isinstance(exc, urllib.error.HTTPError):
        status = exc.code
        raw_header = None
        try:
            raw_header = exc.headers.get("Retry-After") if exc.headers else None
        except AttributeError:
            raw_header = None
        if raw_header:
            try:
                retry_after = float(str(raw_header).strip())
            except (TypeError, ValueError):
                # The HTTP-date form. Not worth a date parser: the backoff
                # curve already covers it, and guessing wrong here would pin a
                # provider out for however long we mis-parsed.
                log.debug("unparsed Retry-After %r from %s", raw_header, provider)
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")[:1000]
        except Exception:                                     # noqa: BLE001
            body = ""
        message = f"{exc.reason or ''} {body}".strip() or str(exc)
    elif isinstance(exc, urllib.error.URLError):
        # The interesting part is the wrapped OSError; str(URLError) buries it.
        message = f"{exc.reason}"
        code = f"{code} {type(exc.reason).__name__}"
    else:
        message = str(exc)

    return classify(provider, model, status=status, code=code, message=message,
                    retry_after_s=retry_after)


@dataclass(frozen=True)
class FailoverPolicy:
    """OmniRoute's `FailoverPolicy`, with Primnox's defaults.

    `max_attempts` is a latency budget, not a reliability dial: every attempt
    can cost a full connect timeout before the user sees a token.
    """
    max_attempts: int = 3
    allow_cross_provider: bool = True
    retry_rate_limited: bool = True
    retry_timeouts: bool = True
    # OmniRoute stops the chain on these; Primnox continues. See the module
    # docstring for why, and flip either one to get OmniRoute's behaviour back.
    retry_auth_failures: bool = True
    retry_quota_exhausted: bool = True

    # Types no chain should advance past. A malformed request is Primnox's own
    # bug — every provider will reject it identically, so trying five of them
    # turns one clear error into five confusing ones.
    hard_stop: frozenset = field(default=frozenset({INVALID_REQUEST}))


DEFAULT_POLICY = FailoverPolicy()


def should_failover(failure: Failure, policy: FailoverPolicy = DEFAULT_POLICY) -> bool:
    """May the chain try the next provider after this failure?"""
    verdict, why = _decide(failure, policy)
    log.debug("failover after %s from %s: %s (%s)",
              failure.type, failure.provider, verdict, why)
    return verdict


def _decide(failure: Failure, policy: FailoverPolicy) -> tuple[bool, str]:
    if not policy.allow_cross_provider:
        return False, "cross-provider failover disabled"
    if failure.type in policy.hard_stop:
        return False, "every provider would reject this identically"
    if failure.type == RATE_LIMIT:
        return policy.retry_rate_limited, "rate limited"
    if failure.type == TIMEOUT:
        return policy.retry_timeouts, "timed out"
    if failure.type in (AUTHENTICATION_ERROR, PERMISSION_ERROR):
        return policy.retry_auth_failures, "credential rejected"
    if failure.type == QUOTA_EXHAUSTED:
        return policy.retry_quota_exhausted, "out of quota"
    if failure.type in (NETWORK_ERROR, PROVIDER_5XX, MODEL_UNAVAILABLE):
        return True, "provider-side, another may answer"
    # UNKNOWN. Trying one more provider is the cheaper mistake: the alternative
    # is failing a turn that would have worked, on a classification we already
    # admitted we could not make.
    return True, "unclassified"
