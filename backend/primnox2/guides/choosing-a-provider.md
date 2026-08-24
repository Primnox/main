---
title: Gateway or local — which do I want?
summary: Primnox reaches hosted models through OmniRoute and local ones directly. That is the whole decision.
order: 1
---

# Gateway or local

Primnox does not host a model. Every reply comes from somewhere you chose, and
there are only two shapes that choice can take.

## Through the gateway

**OmniRoute** is a local program that fronts around 290 hosted providers behind
one endpoint. Primnox talks to it on `127.0.0.1:20128` and it forwards to
whichever provider it picks.

This is the default, and it is why Primnox carries no provider catalogue of its
own. It briefly did — 346 entries copied out of OmniRoute's source — and that
was a mistake worth describing, because it explains the current design: only
103 of those entries carried an endpoint Primnox could actually call, and
keeping the rest current would have meant hand-tracking someone else's release
cycle forever to remain a worse copy of it.

So the provider list lives in OmniRoute, where it is maintained, and **your API
keys live there too** rather than in Primnox's keyring.

If it is not installed, Settings → Provider shows the one command.

## On this machine

**Ollama**, LM Studio, or llama.cpp. No key, no account, and no network — this
is the only configuration where nothing you type leaves the machine at all.

Bounded by your hardware: a 7B model runs comfortably on most laptops, a 70B
one does not run on any of them. Primnox reads what you already have installed
rather than suggesting something that will not load.

## Both

The usual setup. OmniRoute active with Ollama behind it, so a rate limit or an
outage degrades to a local answer instead of a failed conversation.

It does not work in the other direction. A local session never falls back to
the gateway — see [How routing and failover work](routing-and-failover).

## Choosing a channel, not a model

On the OmniRoute profile, pick one of the `auto/*` channels rather than a named
model:

| Channel | Optimises for |
|---|---|
| `auto` | Balanced. Sticks to the last provider that worked. |
| `auto/coding` | Quality for code. |
| `auto/fast` | Lowest latency. |
| `auto/cheap` | Cost per token. |
| `auto/offline` | Most quota headroom. |
| `auto/smart` | Quality, with some exploration. |

A named model pins the turn to one provider and gives up the fallback that is
the entire reason to run a gateway. Pick the named model in OmniRoute's own
dashboard if you need one for a specific job.

## Running but empty

Worth knowing because it looks like success: OmniRoute can be reachable with no
providers connected to it. Nothing distinguishes that from healthy by status
code, and a message sent in that state fails *inside the gateway* — which reads
as a Primnox error and is not one.

Settings → Provider says so explicitly when it happens, and links to the
dashboard where you connect one.

## A direct endpoint

Any OpenAI-compatible URL, called without OmniRoute in between — a private
deployment, a company proxy, or a provider you would rather reach directly. Add
it under **Advanced** on the same tab: base URL, model, API type, key. That key
does live in Primnox's keyring, because there is no gateway holding it.
