---
title: When a provider stops working
summary: Reading the error, finding out whether it is the key, the endpoint, the model, or them.
order: 4
---

# When a provider stops working

Five things can be wrong and they look almost identical from the outside: the
gateway, the key, the endpoint, the model name, or the provider itself. This is
how to tell them apart without guessing.

## Is OmniRoute running?

Ask this first, because it is upstream of everything hosted. Settings →
Provider says **Not installed**, **Running**, or — the one worth reading twice
— **Running, but no providers connected**. That last state answers requests and
has nothing to route them to, so a turn fails inside the gateway and reads as a
Primnox error.

If it is down, local models still work. Nothing else does.

## Start with Test

Settings → Provider → the **⚡** button on the profile's row. It probes the
endpoint with the stored key and reports what came back.

A pass means reachable and authenticated. It does **not** mean chat works — some
endpoints serve a model list to anyone and reject completions without a paid
plan. The wording says "reachable" for exactly that reason.

A failure names itself, and the name tells you where to look.

| What it says | What is actually wrong |
|---|---|
| `authentication error` | The key. Revoked, mistyped, or from a different account. |
| `permission error` | The key is valid but not entitled to this model. |
| `quota exhausted` | The account is out of credit. Waiting will not fix it. |
| `rate limit` | Too many requests. Waiting *will* fix it. |
| `model unavailable` | The endpoint is fine; the model id is retired or wrong. |
| `provider 5xx` | Their problem. Nothing to fix on this side. |
| `timeout` / `network error` | Nothing answered. Endpoint, DNS, VPN, or firewall. |
| `not JSON` | The URL is not an API. Usually a sign-in or bot-check page. |

## The model id is the most common one

Model names go stale faster than anything else. Providers retire ids without
warning and the failure arrives as a 404 that reads like the endpoint is wrong.

Press **↻** on the profile row. It asks the provider what it currently offers
and replaces the list. If the model you were using has disappeared from it, that
was the problem.

## "It says benched"

The circuit breaker has skipped this provider because it failed twice in a row.
Nothing is being sent to it, which is why it is not producing new errors.

If you have already fixed the cause, you do not have to wait out the cooldown:

- **Test** it — a successful probe closes the breaker immediately.
- Or **Reset** on the Routing panel, which forgets everything known about it.
- Or restart Primnox. Breakers do not survive a restart by design.

If you have not fixed anything, the countdown is showing you when it will next
be probed automatically. It doubles each time, up to 15 minutes.

## "My reply came from the wrong provider"

That is failover, and the Routing panel shows the order it will try. A provider
that is benched, out of credit, or missing a key is skipped, and the next one
answers.

If you want that to stop, set `models.failover_attempts` to 1 in Settings →
Tuning. The turn will then fail instead of falling back — which is the right
setting if a wrong-but-cheap answer is worse for you than no answer.

## "It worked yesterday"

In rough order of likelihood:

1. **A free tier reset or ended.** Free quotas move, and providers end them.
2. **The key expired.** Several providers rotate keys on a schedule.
3. **The model was retired.** Press ↻.
4. **You are behind a different network.** A VPN or a corporate proxy can block
   an endpoint that worked at home. `timeout` rather than `authentication error`
   points this way.

## Nothing works at all

Check whether the failure is Primnox rather than any provider:

Settings → Diagnostics → **Force the echo provider**. Echo needs no network and
no key and answers immediately. If echo replies normally, the runtime is fine
and the problem is a provider or the network. If echo also fails, the problem is
Primnox and the logs are the next stop.

## Reading the logs

Every routing decision is logged under `primnox2.routing`. Turn on
Settings → Diagnostics → **Record a trace per turn** and a failing conversation
records which provider was tried, in what order, what each returned, and how
long it took before giving up.

That trace is written to your machine and sent nowhere.
