# Primnox Web

A browser build of the Primnox V2 conversation runtime. Zero-knowledge
storage, static host, feature parity with desktop V2 minus the on-device
privacy scrubber.

**Canonical design:** [`../docs/ARCHITECTURE_WEB.md`](../docs/ARCHITECTURE_WEB.md)
(CRS/1.0-W). Read it before touching anything here.

```
web/
├── client/     the SPA — content plane (crypto, context, model calls, sandbox)
├── server/     Render service — coordination plane (event log, fan-out, sync)
└── supabase/   Postgres migrations — the single runtime database
```

## Status — Phase 1 (Foundation), in progress

| Piece | State |
|---|---|
| `client/src/crypto` | **done** — Argon2id → KEK → DEK, AES-256-GCM AEAD w/ AAD, BIP-39 recovery, passphrase change. 11 tests + verified in a real browser. |
| `client/src/runtime` (reducer, store) | **done** — CRS/1.0-W envelope + kinds, pure-fold reducer with dedupe + gap buffering, observable store for React. 7 tests. |
| `client/src/model` | **done** — Model Router + Capability Layer; SSE parser; adapters for OpenRouter/Groq (OpenAI-compatible), Anthropic (direct-browser header), Gemini (`?alt=sse`); normalized `StreamEvent`; `model.egress` audit hook. 16 tests. |
| `client/src/context` | **done** — Context Bundle builder: system block + memory/asset/workspace folding, oldest-first history trim to a token budget. 3 tests. |
| `client/src/runtime` (transport, turn) | **done** — `HttpTransport` + `MockTransport` (real in-memory event log + replay); `runTurn` generates all ids, drives start → stream → encrypt-then-POST each token → complete, abort → `turn.cancelled` + partial text. 5 tests, incl. a full seal → log → decrypt → reduce round-trip. |
| `client/src/runtime/eventcodec` | **done** — `sealEventPayload` / `decryptEvent`; AAD binds each payload to its event id + kind; enforces the §4.2 carve-out (only `turn.failed` / `turn.status` / `sync.complete` may be unsealed, `token` / `message` / `tool.*` / `memory.*` rejected if unsealed). 7 tests. |
| `client/src/runtime/realtime` (`EventFeed`) | **done** — subscribe → replay the gap → drain; decrypt each row and `store.ingest`, `store.skip` on failure so the cursor never stalls. `MockRealtimeSource`. 3 tests. |
| `client/src/runtime/reducer` | **done** — added `skip()` (acknowledge a sequence without applying) sharing the ordering machinery with `ingest()`. |
| `client/src/vault/keys` | **done** — `ProviderKeyStore`: BYO model keys sealed under the DEK, one active entry per provider, `profile()` for the turn driver. 3 tests. |
| `client/src/auth` | **done** — `SessionStore` state machine (`loading`/`authenticated`/`unauthenticated`/`expired`) + `accessToken()` for `HttpTransport`; `AuthClient` interface with `SupabaseAuthClient` (the only file importing supabase-js) and `MockAuthClient`. 6 tests. |
| `client/src/ids` | **done** — client-generated `<prefix>_<uuidv7>` ids (CRS §1.1) so AAD binding is exact. |
| `supabase/migrations/0001_init.sql` | **done** — full schema + RLS + Realtime on `events`. Not yet applied to a project. |
| `server/` | **done for Phase 1** — JWKS JWT verify, client-supplied ids validated, `appendEvent` folded into the caller's transaction (CRS §4.2 atomic), turn/token/complete/cancel/replay routes, origin-disconnect watchdog. Typechecks; not yet deployed. |
| GitHub App connect + sync job, real chat UI (reuse `frontend/`), Supabase project | not started. |

**61 client tests pass. Both packages typecheck clean. SPA builds.**

## Operator setup (account actions — not code)

See [`../docs/ARCHITECTURE_WEB.md#18`](../docs/ARCHITECTURE_WEB.md). In short:

1. **GitHub** — create `cyanexani/primnox-chat`, enable Pages. Register the
   *Primnox Data* GitHub App (Contents RW, Metadata R, single-repo). Store its
   private key + client secret as Render secrets.
2. **Supabase** — new project. Enable Auth (email + GitHub OAuth). Apply
   `supabase/migrations/0001_init.sql`. Note the project URL, anon key, JWKS URL.
3. **Render** — new web service from `web/server`. Env per `server/.env.example`.
   Add a 10-minute cron pinger to `/health` (resolves Q5).

## Local dev

```bash
cd web/client && npm install && npm test        # crypto + reducer unit tests
cd web/client && npm run dev                     # vault panel at :5273/primnox-chat/
cd web/server && npm install && npm run dev      # needs a Supabase project + DATABASE_URL
```

## Phase 1 decisions locked (2026-08-30)

- Providers: OpenRouter, Anthropic (direct-browser header), Gemini, Groq.
  OpenAI models routed via OpenRouter. The §W4 tunnel ships disabled.
- Fan-out: Supabase Realtime on the `events` table, RLS-filtered.
- Recovery: BIP-39 mnemonic capture forced at setup, with an explicit
  "no recovery, I accept" escape hatch.
- Render: free tier + cron pinger until there are real users.
