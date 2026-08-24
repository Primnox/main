---
title: What leaves your device
summary: Exactly which text goes to a provider, what is replaced before it does, and where the line is drawn.
order: 3
---

# What leaves your device

Primnox runs on your machine and talks to whichever provider you configured.
Whether anything leaves at all depends on which one that is, and the distinction
is enforced in code rather than promised in a settings screen.

## On-device providers

Ollama, LM Studio, llama.cpp, and anything else running on this computer.

Nothing leaves. The conversation, your documents, the knowledge graph, memory —
all of it stays in `primnox.db` on your disk and the model reads it over
loopback. There is no network request to scrub, so nothing is scrubbed: applying
pseudonymization to a request that never leaves would cost accuracy and buy
nothing.

## Cloud providers

Anthropic, OpenAI, and the other 300-odd hosted entries.

The prompt goes to their servers. That is what calling an API means, and no
amount of local processing changes it. What Primnox controls is *what the prompt
contains*.

Before any outbound call, the **Privacy Mirror** replaces personal data with
consistent placeholders: names, email addresses, phone numbers, and similar
identifiers become stable stand-ins. The model sees the structure of what you
asked without the identifying detail. When the reply streams back, the
placeholders are swapped for the real values before a single token reaches your
screen — so you never see the substitution and the model never sees the original.

Both directions happen at one place in the code, deliberately. A caller that
scrubbed the request and rehydrated the reply itself would be a second
implementation that could drift out of sync with the first.

You can see exactly what was substituted for any turn: the reveal appears in the
conversation itself, on the machine, and is sent nowhere.

## The gateway on localhost is not local

This is now the main path, not an aside, and the address lies about it.

OmniRoute runs on `127.0.0.1:20128` and forwards your request to a hosted
provider a millisecond later. The URL says loopback. The destination is
somebody else's server — and since Primnox reaches every hosted model this way,
one wrong classification would switch scrubbing off for all of it at once.

Primnox classifies a provider by what it *is*, not where it listens. An entry
marked as a gateway is treated exactly like a cloud provider: the Privacy Mirror
applies, and a local session will not fall back to it. Getting this wrong would
have meant scrubbing was silently skipped for prompts that left the machine
immediately afterward, which is why there is a test that fails if it regresses.

## What is never sent

- **Your API keys**, to anywhere other than the provider they belong to. They
  live in the Windows Credential Manager, one entry per profile, and are never
  written to the database and never returned to the interface — not even masked.
- **Telemetry.** There is none. No usage reporting, no crash uploads, no
  analytics endpoint.
- **Your database.** `primnox.db` is never uploaded anywhere by Primnox.
- **Provider exports.** The export in Settings deliberately contains no keys, so
  the file is safe to mail to yourself or attach to a bug report.

## What routing sends

Failover means a turn can reach a provider other than the one you picked. Two
rules bound that:

A local session never falls back to a cloud provider, however badly the local
one is failing. Cloud → local is allowed, because it only reduces what leaves.

And a cloud fallback receives the *same scrubbed payload* as the first attempt —
scrubbed once for the whole chain, not re-derived per provider, so two providers
can never see two different versions of your prompt.

## Turning scrubbing off

Settings → Privacy. It is on by default, and an absent setting is read as on:
this is one of the few places in Primnox where the default fails toward privacy
rather than toward whatever the user last did.

Turning it off sends your text verbatim. There are legitimate reasons — the
substitution can confuse a model on tasks that are genuinely about names — but
it is a decision, and it is worth making deliberately rather than by accident.
