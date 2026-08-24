---
title: How routing and failover work
summary: Why a reply sometimes comes from a provider you did not pick, and how to see the reasoning.
order: 2
---

# How routing and failover work

When you send a message, Primnox does not simply call the provider you
activated. It walks a chain: the provider you chose first, then the others you
have configured, stopping at the first one that answers.

Most of the time the chain stops at step one and none of this is visible. It
becomes visible when something is wrong — and then the question is always the
same: *why did my reply come from Ollama when I picked Anthropic?*

Settings → Provider → **Routing** answers that. This explains what it is showing.

## The chain

The order is not arbitrary.

**Your active provider is always first.** Whatever its health, whatever its
score. You picked it; an app that quietly demotes your choice because it was
slow once is not doing failover, it is overruling you.

**Everything after it is ranked** by what Primnox has actually observed:
success rate, time to first token, whether the circuit is open, whether the
credential was rejected last time. That is exactly where you have not expressed
a preference, so the app uses what it knows.

## When a failover happens

Only before the first token arrives.

A provider that dies before producing anything can be replaced silently —
nothing has reached your screen, so nothing has to be taken back. A provider
that dies *after* producing something cannot: restarting on another model would
splice two half-answers into one reply with no visible seam. So the first token
is the point of no return, and a failure after it is reported as an error rather
than routed around.

Not every failure earns a retry either:

| What happened | What the chain does |
|---|---|
| Rate limited (429) | Try the next provider |
| Server error (5xx) | Try the next provider |
| Timeout, connection refused | Try the next provider |
| Key rejected (401/403) | Try the next provider, and bench this one for 5 minutes |
| Out of credit | Try the next provider, and bench this one for 10 minutes |
| Malformed request (400) | **Stop.** Every provider will reject it identically |

That last row is the one worth knowing. A 400 is usually Primnox's own bug, and
trying five providers turns one clear error into five confusing ones.

## The circuit breaker

A provider that fails twice in a row is *benched*: skipped without being called
at all, until a cooldown expires. This is not punishment, it is arithmetic — an
endpoint that is down costs a full connection timeout every time you ask, and
you would pay that on every message for as long as it stayed down.

The cooldown starts at 30 seconds and doubles each time the provider trips
again, up to 15 minutes. A rejected key skips the two-strike rule and benches
immediately, because the same credential will be rejected on the next call too.

When the cooldown expires the provider is not simply restored — the next message
is sent as a single **probe**. If it works, the breaker closes. If it fails, it
reopens with a longer cooldown. That way recovery is tested with one request
rather than by resuming full traffic against something still broken.

**Restarting Primnox clears every breaker.** A breaker is a claim about what is
happening right now, and the usual fix — start Ollama, paste a new key,
reconnect the VPN — happens outside the app.

You can also clear one immediately with **Reset** on the Routing panel, which is
what "I already fixed it, stop waiting" means. Testing a provider successfully
does the same thing.

## Reading the score

Each fallback shows a score between 0 and 1. It is the product of nine factors,
not their average, which has one useful consequence: **any factor at zero takes
the whole score to zero.** A provider with an open circuit scores 0 no matter how
good it is at everything else, and cannot be carried into the chain by its other
numbers.

Expand a row to see all nine. When a candidate is ineligible, exactly one of
them is zero, and that one is the reason.

## The local boundary

**A local provider never falls back to a cloud one.** If you are running Ollama
and it stops, the turn fails.

That is deliberate. Answering a local outage by sending the same conversation to
a hosted API would be the single worst thing this chain could do, and it would
do it silently, in the middle of a reply. Cloud → local is allowed, because that
direction only ever reduces what leaves the device.

## Turning it off

Settings → Tuning → **Providers** → `models.failover_attempts`. Set it to 1 and
Primnox calls the active provider and nothing else.

The other three knobs there control the breaker: how many consecutive failures
bench a provider, the first cooldown, and the ceiling on the doubling. Each says
what moving it costs.
