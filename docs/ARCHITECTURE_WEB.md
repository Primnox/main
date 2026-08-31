# Primnox Web — Architecture

**CRS/1.0-W** · Status: Draft · 2026-08-30

This document defines the architecture of **Primnox Web**: a browser build of
the Primnox V2 conversation runtime that runs on a static host, keeps
zero-knowledge storage, and reaches feature parity with desktop V2 minus the
Privacy Mirror.

It is a *profile* of [CONVERSATION_RUNTIME_SPEC.md](CONVERSATION_RUNTIME_SPEC.md)
(CRS/1.0), not a replacement. §4 below is the normative part — it enumerates
every CRS clause that is amended, added, or removed for the web substrate.
Everywhere §4 is silent, CRS/1.0 applies unchanged.

**Companion documents**

| Document | Role |
|---|---|
| [CONVERSATION_RUNTIME_SPEC.md](CONVERSATION_RUNTIME_SPEC.md) | **Normative base.** Objects, event log, transactions, lifecycles, reconnect, cancellation. |
| [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md) | Desktop rationale. The design this profile diverges from. |
| [../PRODUCT.md](../PRODUCT.md) | Product constraints. §15 records which of its claims the web build cannot hold. |

---

## 0. The one-sentence change

**Desktop's runtime produces content and stores it locally. Web's client
produces content and stores it as ciphertext; the server orders and fans out
events it cannot read.**

Desktop Primnox is one process on `127.0.0.1` with one SQLite file. Every
guarantee in CRS/1.0 — atomic `state + event`, a gapless global sequence,
replay from the log, no fake streaming — is cheap because one process owns
everything.

Web Primnox splits that process across a browser it trusts and a server it
does not. The browser holds the keys, assembles context, calls the model, and
runs the sandbox. The server (Render) holds none of the plaintext and does the
one job the browser cannot do alone: assign a global order to events from
multiple devices and fan them out. Supabase Postgres is the single runtime
database. GitHub is the user's encrypted archive. Everything sensitive that
leaves the browser is ciphertext.

---

## 1. Locked decisions

Settled in the design dialogue of 2026-08-30. Changing any of these is a
major revision of this document.

| # | Decision | Consequence |
|---|---|---|
| D1 | **Web upholds the desktop privacy posture**, not a weaker one. | No server-readable user content anywhere. Rules out server-side orchestration, memory ranking, and context assembly. |
| D2 | **Client-side zero-knowledge E2E.** Passphrase → Argon2id → KEK → DEK, all in the browser. | Render and Supabase see ciphertext + envelope metadata only. Lost passphrase + lost recovery mnemonic = lost data, by design. |
| D3 | **BYO model key, stored encrypted in the user's GitHub repo.** | The key is vault data like any other. It is decrypted in the browser per session and sent directly to the provider. |
| D4 | **Keep a real backend: Render + Supabase Postgres.** | Under D1/D2 it is a coordination plane, not an orchestrator. §3.2 lists exactly what it does. |
| D5 | **Two independent auth relationships.** Supabase Auth = identity. GitHub App = repo authorization. | A user can disconnect GitHub without deleting their account, and vice versa. |
| D6 | **Two desktop guarantees are given up on web and documented as such:** fully-local/offline inference, and OS-level sandbox isolation. | See §13, §15. The web sandbox is WASM; inference is always a network call. |
| D7 | **The Privacy Mirror / PII scrubber is removed.** | Plaintext context reaches the chosen provider, as with any BYO-key web client. The honest security statement is §2.2. |
| D8 | **Host:** static SPA at `cyanexani.github.io/primnox-chat`, reusing the `frontend/` Tactical Telemetry UI. | Vite `base: '/primnox-chat/'`. No SSR. Deployed from a personal repo, not the org. |
| D9 | **Build order:** Foundation → Memory → Assets/Canvas → Knowledge Graph → Tools/WASM → Ambient. | §16. Each phase ships independently and leaves a working app. |

---

## 2. Trust model

### 2.1 Parties and what each can see

| Party | Sees | Cannot see |
|---|---|---|
| **Browser (this user's tab)** | Everything. Holds the KEK and DEK in memory for the session. | — |
| **Render** | Event envelopes (`sequence`, `turn_id`, `kind`, `ts`, `scope`, ids). Ciphertext payloads. Job/turn status. Device + session rows. Usage counters. The GitHub App token. | Message text, token text, tool arguments/results, memory text, canvas contents, titles, provider keys, the KEK, the DEK. |
| **Supabase Postgres** | Same as Render — it is Render's database. | Same as Render. |
| **Supabase Auth** | Email / OAuth identity, session records. | All Primnox content. It is not on the data path. |
| **GitHub** | Encrypted blobs in one repo. Commit timestamps and blob sizes. | Plaintext of anything. |
| **The chosen model provider** | The plaintext Context Bundle for each turn: system prompt, recent messages, retrieved memory, attached asset text, tool schemas. The user's API key. | Anything not put in that turn's bundle. Stored history. Other conversations. |

### 2.2 The honest security statement

> Primnox, Render, Supabase, and GitHub cannot read your stored data. Your
> chosen inference provider receives the plaintext context required to answer
> each message. Nothing is scrubbed before it is sent.

This is the claim the product may make. It must not be shortened to "nothing
leaves your device" (D7) — that is false on web and true only on desktop with
a local model.

### 2.3 Threats

**In scope.** A compromised Render or Supabase. A compromised GitHub account or
a leaked repo. A network attacker. A malicious or subpoenaed infrastructure
operator. Memory-poisoning content in a conversation (§11.4). All of these
reach ciphertext or envelope metadata only.

**Out of scope.** A compromised browser or device. A key-logger capturing the
passphrase. The model provider logging or training on submitted prompts — the
user chooses the provider and accepts its terms. A malicious browser
extension with page access.

**Metadata leakage, acknowledged.** Render and GitHub learn *when* the user is
active, *how many* turns and messages exist, rough *sizes*, and the *shape* of
the conversation graph. Envelope `kind` reveals that (e.g.) a tool ran, not
which tool. This profile does not pad or mix to hide it.

---

## 3. Components

```
                              USER
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PRIMNOX WEB CLIENT — static SPA, GitHub Pages                    │
│  the runtime's CONTENT plane                                      │
│                                                                  │
│  UI (Tactical Telemetry)   Local Application Core                 │
│      Chat · Canvas · Memory / Workspace / Context                 │
│                                                                  │
│  Reducer (pure fold, CRS §8.4)   IndexedDB (cache/drafts/queue)   │
│  Crypto core (Argon2id → KEK → DEK)                               │
│  Context Bundle builder      Memory engine (embeddings, ranking)  │
│  Model Router (direct-to-provider)   Model Capability Layer       │
│  Canvas engine (CRDT)        WASM sandbox (Pyodide / QuickJS)     │
└───────────────┬─────────────────────────────────┬────────────────┘
                │ Supabase JWT                    │ encrypted events
                ▼                                 ▼
        ┌───────────────┐        ┌──────────────────────────────────┐
        │ SUPABASE AUTH │        │  RENDER — the COORDINATION plane │
        │ identity      │        │  JWT verify · event log          │
        │ sessions      │        │  sequence assignment · fan-out   │
        │ JWT           │        │  turn/job lifecycle bookkeeping  │
        └───────────────┘        │  GitHub App token custody + sync │
                                 │  rate limit · usage metering     │
                                 │  ambient triggers                │
                                 │  (optional) non-CORS model tunnel│
                                 └──────────┬───────────┬───────────┘
                                            ▼           ▼
                                  ┌──────────────┐ ┌──────────────┐
                                  │  SUPABASE    │ │   GITHUB     │
                                  │  POSTGRES    │ │  one repo    │
                                  │  the single  │ │  encrypted   │
                                  │  runtime DB  │ │  user data   │
                                  └──────────────┘ └──────────────┘
```

### 3.1 Browser client — the content plane

Owns everything CRS/1.0 assigns to "the Runtime" that touches plaintext:

- **Context Bundle builder** (CRS/ARCH §4.1). Decrypts history, retrieved
  memory, and asset text locally; assembles the prompt.
- **Model Router + Model Capability Layer** (CRS/ARCH §5). Chooses provider
  and model, adapts the universal tool protocol, runs emulation grammar for
  weak models. Calls the provider directly.
- **Memory engine** (§11). Embeddings, retrieval, ranking, the poisoning
  classifier.
- **Canvas engine** (§12). Local operations, CRDT merge.
- **WASM sandbox** (§13). Pyodide / QuickJS, capability-gated.
- **Crypto core** (§5). Passphrase KDF, key unwrap, all encrypt/decrypt.
- **The reducer.** A pure `reduce(state, event) → state` fold (CRS §8.4.3).
  It decrypts payloads as events arrive and never infers state the log did
  not carry.

It also runs a **local application core** — UI state, streaming assembly,
IndexedDB, the sync client — and is offline-capable for everything except a
model call.

### 3.2 Render — the coordination plane

The only server. It **does**:

| Job | Detail |
|---|---|
| Auth verification | Validate the Supabase JWT on every request. Derive `user_id` from it, never from the body (CRS-equivalent of ARCH §13). |
| Event log | Assign the gapless global `sequence` (§4.1), append `{envelope, ciphertext_payload}` atomically, persist to Supabase. |
| Multi-device fan-out | Push new events to every other connected device for that user, filtered per CRS §8.2. |
| Turn / job lifecycle bookkeeping | Own the `status` columns, the visible queue, `cancel_requested` flags, the boot sweep (CRS §10.3), and the origin-disconnect watchdog (§4.4). |
| GitHub App token custody | Hold the installation token. Run the `sync` job: write client-supplied ciphertext blobs to the user's repo, commit, push. |
| Rate limiting · usage metering | Per-user request limits. Aggregate the token counts the client reports. Content-blind. |
| Ambient triggers | Fire reminders and scheduled jobs on time. The *content* of what fires is assembled by the client on wake (§4.9). |
| Non-CORS model tunnel *(optional, off by default)* | A plain server-side proxy for providers with no browser CORS (§10.3). Render can read these prompts and keys. Loudly gated. |

It **does not**: read conversations, retrieve or rank memory, build prompts,
call the model with plaintext, perform crypto, or inspect canvas contents.

**Cold start.** Render's free tier spins down after ~15 min idle and takes
~50 s to wake. Mitigation is an operator decision (§18): paid Starter
instance, or a cron pinger, or accept the first-request delay.

### 3.3 Supabase Postgres — the single runtime database

Resolves CRS §4.1 ("all state tables and the event log MUST live in one
database") by **being** that one database. It replaces `primnox.db`.

- Atomic `state + event` transactions: `BEGIN; … INSERT INTO events …; COMMIT;`
  Postgres gives this directly.
- Gapless sequence: a single `event_seq` counter row, `SELECT … FOR UPDATE`
  inside the event-insert transaction. `SERIAL`/`IDENTITY` is **prohibited**
  for `sequence` for the same reason `AUTOINCREMENT` is in CRS §3.1.3 — a
  rolled-back allocation burns a value and creates a permanent gap.
- Row-Level Security: every table keyed by `user_id`; RLS restricts each row
  to its owner. Render connects with a role that RLS still constrains, so a
  Render bug cannot cross users.
- Payload columns are `bytea` ciphertext. The database has no function that
  can read them.

### 3.4 Supabase Auth

Identity only (D5). Email/password plus OAuth providers (GitHub OAuth is
offered here as a *login*, distinct from the GitHub *App* authorization in
§3.5). Issues the JWT that Render verifies. Not on the data path — a Supabase
Auth compromise yields sessions, not content.

Client auth states, unchanged from desktop intent:
`AUTH_LOADING · AUTHENTICATED · UNAUTHENTICATED · SESSION_EXPIRED`.

### 3.5 GitHub — encrypted durable datastore

The user-owned archive and disaster-recovery copy. One repo, created and
authorized via a **GitHub App** with least privilege:

- Permissions: **Contents: read/write**, **Metadata: read**. Nothing else.
- Scope: a single repository the user picks or lets Primnox create
  (default `primnox-data`, private).
- The installation token lives on Render (§3.2). Render uses it only to run
  the `sync` job with ciphertext the client produced.

GitHub is **not** in the hot transaction path. A turn completes against
Supabase; the `sync` job mirrors to GitHub afterward (§4.11 §W2). This keeps
CRS §4.1 intact — the runtime has one database, and GitHub is a downstream
encrypted export.

Repo layout: §9.2.

### 3.6 IndexedDB — device working copy

Per CRS it is never a source of truth. Holds: decrypted recent conversations
and messages for instant load, draft composer text, canvas working state, the
offline write queue, sync checkpoints, and the downloaded embedding model.
Cleared or lost, it re-hydrates from Supabase + GitHub on next unlock.

Wrapped key material and salt **may** be cached here for faster unlock; the
plaintext KEK/DEK **must not** be persisted — session memory only.

---

## 4. CRS/1.0-W — normative deltas

RFC 2119 keywords. Each entry cites the CRS/1.0 clause it changes. Unlisted
clauses apply as written.

### 4.1 §4.1 — one database → Supabase Postgres

The single database **MUST** be one Supabase Postgres instance. All CRS state
tables and the `events` table live there. Splitting across databases remains
**PROHIBITED**. GitHub is an encrypted export, not a state store, and **MUST
NOT** be read to reconstruct history (§4.5).

`sequence` **MUST** be assigned from an `event_seq` counter row updated inside
the event-insert transaction. `SERIAL`, `IDENTITY`, and sequences that
survive rollback **MUST NOT** be used (CRS §3.1.3 rationale).

### 4.2 §3.2 — envelope plaintext, payload ciphertext

Every event **MUST** keep this envelope in cleartext, exactly as CRS §3.2:
`event_id`, `sequence`, `ts`, `scope`, `conversation_id`, `turn_id`, `kind`.
Ordering, filtering (CRS §8.2), and replay depend on it.

The `payload` object **MUST** be encrypted client-side with the DEK before it
leaves the browser and stored as an opaque blob:

```json
{ "…envelope…": "…",
  "payload": { "v": 1, "alg": "A256GCM", "iv": "…", "ct": "…", "tag": "…" } }
```

Message rows (`messages.body`), workspace file contents, asset `extracted_text`,
memory `text` and `embedding`, canvas document state, conversation `title`, and
provider keys **MUST** be stored the same way. Ids, statuses, timestamps,
counts, and foreign keys stay cleartext.

A client receiving a payload it cannot decrypt (wrong DEK, corrupt blob)
**MUST** surface a decryption error for that item and **MUST** still advance
its cursor (CRS §3.2 unknown-kind rule, extended).

**Carve-out — server-originated lifecycle events.** A `turn.failed` written by
the origin-disconnect watchdog (§4.4), and any future server-emitted
`turn.status` or `sync.complete`, carry a **cleartext** payload restricted to
control metadata: `{ code, message, retryable }` for `turn.failed`,
`{ status }` for `turn.status`, `{ head }` for `sync.complete`. The `message`
**MUST** be a fixed, non-sensitive string. The server holds no key and so
cannot seal; these fields are envelope-class metadata, never user content, and
this is the only path by which an unsealed payload enters the log. A client
**MUST** accept an unsealed payload **only** for these kinds when
`scope = "conversation"` and the event has no client origin, and **MUST**
reject an unsealed payload for `token`, `message`, `tool.*`, `memory.*`, or
`workspace.*`.

### 4.3 §3.4 — durability before delivery, with a client token source

Tokens originate in the browser (§4.4), so CRS §3.4 is satisfied thus:

1. The origin client receives a token from the provider.
2. It encrypts the token and **MUST** `POST` it to Render before rendering it
   as committed (it **MAY** render optimistically in parallel).
3. Render **MUST** append the `token` event (sequence assigned, committed to
   Supabase) **before** fan-out to other devices.
4. A token that reached the provider→client but not Render's log is treated
   as not delivered; on reload the client replays from the log and re-issues
   from the last logged token if the turn is still non-terminal (§4.4).

`token` payloads remain append-only (CRS §3.6.1). Optimistic client text that
Render never confirmed **MUST** be reconciled to the logged sequence on
`sync.complete`.

### 4.4 §7.1 — delivery is origin-client-driven

The runtime **MUST NOT** simulate streaming from stored text (CRS §7.1.2,
unchanged). But the token *source* is the origin client, and:

- A turn in `streaming` or `thinking` **MUST** record its `origin_device_id`.
- Render **MUST** run a watchdog: if the origin device's session drops and no
  `token` / `turn.status` event arrives for that turn within
  `origin_grace_seconds`, Render **MUST** move the turn to `failed` with code
  `origin_disconnected`, `retryable: true`, preserving the partial assistant
  text from the last logged `token` (CRS §9.3, §10.3.2).
- Any device **MAY** then Retry, which creates a new turn referencing the
  failed one (CRS §5.2.3). Automatic resume is **NOT REQUIRED** and **SHOULD
  NOT** be attempted unless the provider supports deterministic continuation.

This is a real reduction from desktop, where the runtime keeps streaming
through a client drop. It is accepted (D1/D2 make a server-side token source
impossible) and **MUST** be shown in the UI, not hidden.

### 4.5 §8 — reconnect, with decrypt-on-replay

The handshake, filtering, `sync.complete`, and full-resync directive are
unchanged (CRS §8.1–§8.3). Additionally:

- On replay the client **MUST** decrypt each payload with the DEK before
  reducing it.
- History load (CRS §3.3.3, §7.1.3) reads state rows from Supabase and
  decrypts them. It **MUST NOT** read GitHub. GitHub is only consulted for
  explicit restore (§4.11 §W2) or when Supabase has lost a row.
- `min_retained_seq` and the `sync.required` path (CRS §8.3) apply to the
  Supabase `events` table's retention.

### 4.6 §13.2 — the privacy boundary is removed

CRS §13.2 (all outbound model traffic passes the Model Gateway; the Gateway is
the only PII-scrubbing point) **does not apply** to this profile. There is no
scrubber (D7). The client-side Model Router is the single egress point and
**MUST**:

- record a `model.egress` event (`{provider, model, input_tokens}` — counts,
  no content) so the user has an audit trail of what was sent where;
- refuse to send if no provider key is unlocked;
- never route through Render except via the explicit non-CORS tunnel (§10.3),
  which **MUST** require per-provider opt-in and display that Render can read
  those requests.

`privacy.scrub` (CRS §3.6) is retired from the registered event kinds for
web.

### 4.7 §5 — the Model Capability Layer runs client-side

Unchanged in contract. It executes in the browser. The capability registry
ships with the SPA; runtime probes and their per-`(base_url, model)` cache
live in IndexedDB (cleartext — not sensitive). No code outside the router
module branches on provider name (CRS §13.1.1).

### 4.8 Context assembly runs client-side

The Context Bundle builder (CRS/ARCH §4.1, §8) executes in the browser. It
decrypts conversation history, retrieved memory, asset text, and workspace
contents locally and produces the plaintext bundle sent to the provider.
Render is not in this path.

### 4.9 §11 — ambient: split trigger and content

Ambient producers (CRS §11.1) split:

- **Trigger** (a reminder's time arriving, a schedule firing) runs on Render.
  Render emits a `system`-scope wake event.
- **Content** (what the reminder says, any retrieval it needs) is assembled by
  the client on wake, encrypted, and promoted per CRS §11.1.3 (promotion
  creates a Turn / Asset / system Turn). Render never composes ambient
  content.

Incognito (CRS §11.2) is unchanged: no rows in `conversations`, `turns`,
`messages`, `events`; in-memory only; history lost on reload and the UI says
so.

### 4.10 §2.5, §2.6 — workspaces and assets

Versioning, immutability, and content-addressing are unchanged. File contents
and `extracted_text` are ciphertext (§4.2). Asset ingestion (hash → extract →
chunk → embed → index) runs entirely in the browser; the sandbox and WASM
extractors do the work. Canvas (§12) layers a CRDT on top of the workspace
version model.

### 4.11 New web-only clauses

**§W1 — Key management.** The client **MUST** implement §5. A server **MUST
NOT** ever hold the KEK, the DEK, or the passphrase in any form from which
plaintext is derivable. Wrapped DEK blobs and the KDF salt **MAY** be stored
server-side and in GitHub (they are useless without the passphrase or the
recovery mnemonic).

**§W2 — GitHub sync.** After a turn reaches a terminal state, Render **SHOULD**
enqueue a `sync` job that writes the affected conversation, turns, messages,
memory, and workspace blobs (all ciphertext, produced by the client and
uploaded with the turn) to the user's repo and commits. The job **MUST** be
idempotent (CRS §6.2.3) and **MUST NOT** fail the turn on GitHub error — it
retries with backoff (CRS §6). A `sync.complete` system event carries the new
repo `head`.

**§W3 — Device registration.** Each browser profile **MUST** register a
`device` row (opaque id, label, created-at, last-seen). Fan-out (§3.2) and the
origin-disconnect watchdog (§4.4) key off it. Revoking a device invalidates
its sessions; it does not touch data.

**§W4 — Non-CORS tunnel.** If Render proxies a model call (§10.3) it **MUST**
be per-provider opt-in, **MUST** show the user that Render can read those
requests and keys, and **MUST** default off. It **MUST NOT** log request or
response bodies.

---

## 5. Encryption & key management

```
              USER PASSPHRASE          (optional) BIP-39 MNEMONIC
                     │                            │
                 Argon2id  ── salt ──┐        HKDF-SHA256
                     │               │            │
                     ▼               │            ▼
                    KEK              │        recovery-KEK
              (never leaves          │            │
               the browser)          │            │
                     │               │            │
          AES-256-GCM unwrap ◄───────┴────────────┤
                     │        wrapped-DEK blobs   │
                     ▼        (repo + Supabase)   │
                    DEK  ─────────────────────────┘
                     │
        ┌────────────┼────────────┬───────────┬───────────┐
        ▼            ▼            ▼           ▼           ▼
     Messages     Memory       Canvas     Workspaces   Provider
     & events     + vectors    (CRDT)     files        keys
        │            │            │           │           │
        └────────────┴──── AES-256-GCM ───────┴───────────┘
                          ciphertext → Supabase + GitHub
```

**KDF.** Argon2id, `m ≥ 19 MiB`, `t ≥ 2`, `p = 1`, 128-bit random salt,
256-bit output. Tuned so a derive costs ~250–500 ms on target hardware
(exact params: §17). Salt is stored cleartext (Supabase `vault.kdf_salt`,
mirrored to repo). Salt is not a secret; the passphrase is.

**Keys.**
- **KEK** — Argon2id(passphrase, salt). 256-bit. Session memory only. Never
  serialized, never sent.
- **DEK** — random 256-bit, generated once at vault creation. Encrypts all
  content. Also session memory only after unwrap.
- **wrapped-DEK** — `AES-256-GCM(KEK, DEK)` → `{iv, ct, tag}`. Stored in the
  repo (`vault/dek.wrap`) and mirrored to Supabase (`vault.wrapped_dek`) so a
  new device can unlock before GitHub is reachable. Both copies are inert
  without the passphrase.

**Recovery (optional but offered at setup).** Generate a 256-bit recovery
secret → render as a BIP-39 mnemonic, shown once. `recovery-KEK =
HKDF-SHA256(recovery secret)`. Store a second wrap `AES-256-GCM(recovery-KEK,
DEK)` at `vault/dek.recovery.wrap`. Lost passphrase → enter mnemonic → unwrap
DEK → set a new passphrase → re-wrap. No mnemonic and no passphrase = data is
unrecoverable, and the setup flow states this in plain words.

**Passphrase change.** Derive old KEK, unwrap DEK, derive new KEK from the new
passphrase, re-wrap. Content is untouched — no re-encryption.

**Multi-device.** New device: fetch salt (public) → prompt passphrase →
Argon2id → KEK → fetch wrapped-DEK → unwrap. No key material transits a server
in usable form. The wrapped-DEK is the only thing shared, and it is
ciphertext.

**Per-item encryption.** Each blob gets a fresh 96-bit random IV. AAD binds
the ciphertext to its envelope where one exists (`event_id` for events,
`msg_id` for messages) so a blob cannot be silently relocated. Format is
versioned (`"v": 1`) for future rotation.

**What is encrypted:** message bodies; event payloads (`token`, `tool.call`,
`tool.result`, `permission.request`, `memory.written`, `workspace.updated`
changed contents); memory text and embeddings; canvas document state;
workspace file contents; asset extracted text; conversation and workspace
titles; provider API keys.

**What is not:** ids, `sequence`, `ts`, `scope`, `kind`, `conversation_id`,
`turn_id`, turn/job status, timestamps, token counts, sizes, foreign keys,
device rows, sync pointers, the KDF salt, wrapped-DEK blobs.

---

## 6. Data ownership matrix

| Data | Supabase Postgres | GitHub repo | IndexedDB |
|---|---|---|---|
| Event log (`events`) | **authoritative**, envelope + ciphertext payload | encrypted mirror (via `sync`) | recent window, decrypted cache |
| Turns / messages | **authoritative**, ciphertext bodies | encrypted mirror | decrypted cache |
| Conversations / folders | **authoritative**, ciphertext titles | encrypted mirror | decrypted cache |
| Jobs, queue, `cancel_requested` | **authoritative** | — | mirror of visible queue |
| `sequence` counter | **authoritative** | — | — |
| Devices / sessions | **authoritative** | — | this device's id |
| Usage counters | **authoritative** | periodic encrypted snapshot | — |
| Memory (text + vectors) | encrypted rows for fast sync | **authoritative** encrypted store | decrypted working index |
| Canvas (CRDT updates) | encrypted update blobs, ordered | **authoritative** encrypted store | live CRDT doc |
| Workspaces / versions | encrypted rows | **authoritative** encrypted store | open workspace only |
| Assets (blobs + extracted text) | metadata + encrypted text | **authoritative** encrypted blobs | opened assets |
| Provider keys | encrypted mirror | **authoritative** (`vault/keys.enc`) | decrypted in session memory |
| Wrapped-DEK, KDF salt | mirror | **authoritative** (`vault/`) | may cache |
| Drafts, offline queue | — | — | **authoritative** |

Rule of thumb: **Supabase is operational truth (fast, ordered, ephemeral-ish);
GitHub is durable user-owned truth; IndexedDB is this device's working copy.**
On conflict for durable data, GitHub wins; for live runtime state, Supabase
wins.

---

## 7. The request lifecycle

A user sends a message. `▸` = browser, `▹` = Render.

```
▸  compose → optimistic user bubble, write draft to IndexedDB
▸  ensure KEK/DEK unlocked (prompt for passphrase if the session is cold)
▸  POST /conversations/{id}/turns   { ciphertext(user_message), asset_ids[] }
▹      verify JWT → user_id
▹      BEGIN
▹        event_seq += 1
▹        INSERT turn (QUEUED), INSERT message(user, ciphertext)
▹        INSERT event turn.created
▹      COMMIT
▹      fan-out turn.created to other devices
▹      return { turn_id, sequence }                         (~tens of ms)
▹      enqueue chat job; mark origin_device_id
▸  status → building_context
▸  Context Bundle builder:
▸    decrypt recent turns, retrieve memory (§11), decrypt asset text,
▸    decrypt open workspace files → assemble plaintext bundle
▸  Model Router (§10): pick provider+model, apply Capability Layer
▸  emit model.egress event (counts only), status → thinking
▸  fetch(provider, bundle, stream=true)          ── plaintext leaves here ──
▸  on first token: status → streaming
▸  for each token:  encrypt → POST /turns/{id}/events  { token }
▹      append token event (committed) → fan-out to other devices
▸  tool proposal:
▸    status → tool_running; run in WASM sandbox (§13);
▸    encrypt tool.call / tool.result events → POST
▸  permission needed:
▸    status → awaiting_input; emit permission.request; park until user answers
▸  provider stream ends:
▸    encrypt assistant message + turn.completed{usage} → POST
▹      BEGIN … turn → COMPLETED, INSERT message(assistant, ciphertext),
▹              INSERT event turn.completed … COMMIT → fan-out
▹      enqueue memory job, enqueue sync job (§W2)
▸  memory job (browser): extract candidates → classify (§11.4) →
▸    embed → encrypt → POST memory.written events
▹  sync job (Render): write ciphertext blobs to the repo, commit, push →
▹    emit sync.complete { head }
▸  reconcile optimistic text to logged sequence; clear draft
```

Failure branches follow CRS §10 with codes extended by §4.4
(`origin_disconnected`) and §10.3 (`provider_*` unchanged). GitHub failure in
the sync job never fails the turn (§W2).

---

## 8. Auth & GitHub authorization

Two relationships, deliberately separate (D5).

```
        SUPABASE AUTH                        GITHUB APP
        "who is this user?"                  "which repo may Primnox use?"
              │                                    │
        email / OAuth login                  install on one repo
              │                              (Contents RW, Metadata R)
              ▼                                    │
          JWT (short-lived)                   installation token
              │                                    │
              ▼                                    ▼
        Render verifies on every request     Render holds it, runs sync only
```

- **Login** is Supabase Auth. GitHub *OAuth* may be one login option; that is
  identity, not repo access.
- **Repo access** is a GitHub *App* install, done once, revocable from GitHub
  settings or an in-app "Disconnect GitHub" that deletes the stored
  installation token and stops sync. Data already in the repo stays the
  user's.
- **"Delete my Primnox data"** is two flows: purge Supabase rows for the
  user; and (separately, user-initiated) delete or keep the GitHub repo.
- Least privilege is enforced by the App manifest — Primnox cannot see other
  repos, cannot read account data beyond metadata, cannot act outside the one
  installation.

---

## 9. Storage schemas (sketch)

Indicative, not final DDL. `ct` columns are `bytea` ciphertext per §4.2.

### 9.1 Supabase Postgres

```
event_seq            (id=1, value bigint)                    -- the one counter
schema_migrations    (version, applied_at)

users                (id, supabase_uid, created_at)
devices              (id, user_id, label, created_at, last_seen_at, revoked_at)
sessions             (id, user_id, device_id, issued_at, expires_at, revoked_at)

vault                (user_id, kdf_salt, kdf_params, wrapped_dek,
                      wrapped_dek_recovery, key_version, updated_at)

folders              (id, user_id, parent_id, title_ct, created_at, updated_at)
conversations        (id, user_id, folder_id, title_ct, incognito,
                      created_at, updated_at, archived_at, deleted_at)
turns                (id, conversation_id, user_id, seq_in_conversation,
                      status, error_code, error_ct, origin_device_id,
                      created_at, completed_at)
messages             (id, turn_id, role, body_ct, created_at)

jobs                 (id, turn_id, user_id, kind, status, cancel_requested,
                      attempts, payload_ct, result_ct, error, created_at,
                      started_at, finished_at)

events               (event_id, sequence bigint UNIQUE, ts, scope,
                      conversation_id, turn_id, kind, payload_ct)
                      -- INSERT always inside the event_seq bump txn
min_retained_seq     (value bigint)

assets               (id, user_id, kind, source, sha256, bytes, status,
                      extracted_text_ct, page_count, metadata_ct, created_at)
turn_assets          (turn_id, asset_id)

workspaces           (id, user_id, kind, title_ct, origin_turn_id,
                      current_version, created_at, updated_at)
workspace_versions   (workspace_id, version, files_ct, created_by_turn_id,
                      created_at)

canvas_updates       (id, workspace_id, user_id, seq, update_ct, created_at)
                      -- ordered encrypted CRDT deltas

memories             (id, user_id, kind, text_ct, embedding_ct, salience,
                      created_at, last_used_at, expires_at, source_turn_id)

usage                (id, user_id, turn_id, provider, model, input_tokens,
                      output_tokens, latency_ms, created_at)

github_connection    (user_id, installation_id, repo_id, repo_full_name,
                      status, connected_at)
sync_state           (user_id, repo_head, last_synced_seq, updated_at)
```

RLS: every table with `user_id` restricts `USING (user_id = auth_uid())`.
Child tables join to parent for the check.

### 9.2 GitHub repo (`primnox-data`, private)

```
primnox-data/
├── vault/
│   ├── kdf.json                 kdf params + salt (cleartext, not secret)
│   ├── dek.wrap                 AES-GCM(KEK, DEK)
│   ├── dek.recovery.wrap        AES-GCM(recovery-KEK, DEK)   (if enabled)
│   └── keys.enc                 provider API keys (AES-GCM, DEK)
├── conversations/
│   └── {conv_id}/
│       ├── meta.enc             title, folder, timestamps
│       ├── turns.enc            turn rows
│       └── messages.enc         message bodies
├── memory/
│   ├── facts.enc  preferences.enc  projects.enc  relationships.enc
│   └── vectors.enc              embeddings
├── canvas/
│   └── {ws_id}/updates.enc      CRDT update log
├── workspaces/
│   └── {ws_id}/v{n}.enc
├── artifacts/
│   └── {asset_id}.enc
├── manifest.enc                 index: ids, versions, blob → head map
└── README.md                    cleartext: "encrypted Primnox data; see …"
```

Writes are batched by the `sync` job into one commit per sync cycle.

### 9.3 IndexedDB stores

`conversations`, `messages`, `events` (recent, decrypted) · `drafts` ·
`outbox` (queued encrypted writes) · `canvas` (live docs) · `sync` (cursors,
`repo_head`) · `models` (capability probe cache, cleartext) · `embedder`
(downloaded model files). No plaintext keys.

---

## 10. Model path

### 10.1 Direct to provider

The Model Router calls the provider from the browser with the user's key.
Streaming over `fetch` (SSE or chunked). Per-token: encrypt → POST to Render
(§4.3).

### 10.2 CORS-capable providers (the v1 set)

| Provider | Browser-callable | Note |
|---|---|---|
| OpenRouter | yes | built for browser use |
| Anthropic | yes | requires `anthropic-dangerous-direct-browser-access: true` |
| Google Gemini | yes | API-key calls send CORS |
| Groq | yes | |
| Mistral | yes | verify at integration |
| Cerebras / Together | yes | verify at integration |

### 10.3 Non-CORS providers

OpenAI's main API does not support browser calls. Options, in order of
preference:

1. **Route the user to OpenRouter** for OpenAI models (still their key/billing,
   OpenRouter is browser-safe).
2. **The Render tunnel (§W4)** — off by default, per-provider opt-in, with a
   clear notice that Render can read those prompts and keys. No body logging.
3. **Leave OpenAI-direct out of v1.**

The router picks 1 automatically where possible and only offers 2 on explicit
user action.

### 10.4 Token accounting

The client reports `{input_tokens, output_tokens, latency_ms}` per call in a
`usage` row and a `model.egress` event. Counts only — Render meters and
rate-limits on these without seeing content.

---

## 11. Memory engine (client-side)

### 11.1 Embeddings

`transformers.js` with a small sentence encoder — candidate
`Xenova/bge-small-en-v1.5` (~33 MB, 384-dim) or `Xenova/all-MiniLM-L6-v2`
(~23 MB). WebGPU when available, WASM fallback. Model cached in IndexedDB.
Final choice: §17.

### 11.2 Retrieval & ranking

Vectors are decrypted into an in-memory index on unlock. Brute-force cosine is
adequate to ~10 k memories; above that, an in-JS HNSW (§17). Ranking blends
similarity, recency, salience, and explicit pins — same intent as desktop.

### 11.3 Memory types & lifetime

| Type | Lifetime |
|---|---|
| User preferences ("use dark mode") | durable |
| Stable facts | durable |
| Project context ("working on X this week") | medium-term, decays |
| Relationships, decisions, goals | durable, revisable |
| Working context ("we're discussing function Y") | turn / session |
| Historical context | archived, low salience |

### 11.4 Poisoning defense

Conversation text **MUST NOT** become a trusted instruction automatically.
Every candidate passes: is it a fact/preference/decision (vs a command)? is it
plausibly from the user (vs quoted/pasted/tool output)? is it instruction-like
or jailbreak-shaped? confidence score → persist / hold-for-confirm / drop.
This runs in the browser as part of the memory job.

---

## 12. Canvas

Workspace version model (CRS §2.6) plus a CRDT for live editing.

- **Library:** Yjs (leading candidate) or Automerge — §17.
- **Local first:** an edit updates the in-memory doc and the UI immediately;
  the CRDT update is queued.
- **Sync:** each update is encrypted with the DEK and POSTed to Render, which
  stores it as an ordered opaque blob (`canvas_updates`) and fans out. Render
  merges nothing — clients apply updates in order and the CRDT resolves.
- **Conflict:** CRDT convergence for document content. Last-write-wins is
  acceptable only for non-content metadata (title, position of a detached
  panel).
- **Snapshot:** periodically the client writes a compacted encrypted state to
  `workspace_versions` and truncates the update log.

---

## 13. Sandbox

Browser, so **not** the desktop AppContainer.

| | Desktop | Web |
|---|---|---|
| Mechanism | Windows AppContainer | WASM: Pyodide (Python), QuickJS (JS) |
| Memory isolation | OS-enforced | yes (WASM linear memory) |
| Filesystem isolation | OS-enforced | virtual FS only; no host FS |
| Network isolation | OS-enforced | host-controlled; no network unless the host grants a fetch shim |
| Process isolation | OS-enforced | n/a — no processes |
| CPU / wall limits | job object | cooperative + worker termination |

Capabilities are explicit and per-tool: `READ_VFS`, `WRITE_VFS`,
`NET_FETCH(allowlist)`, `CLOCK`. Default deny. The host mediates every
capability call; the guest cannot escalate.

**This must not be marketed as equivalent to the desktop sandbox** (D6, §15).
It is memory-safe code execution, not OS-level isolation.

Reference: [sandbox-runtime-limitations.md](sandbox-runtime-limitations.md).

---

## 14. Failure handling

| Failure | Behaviour |
|---|---|
| Origin tab closes mid-stream | Watchdog → `turn.failed{origin_disconnected}`, partial text kept; any device can Retry (§4.4). |
| Render unreachable | Client keeps working offline; writes queue in IndexedDB `outbox`; turns cannot start (no sequence, no fan-out) — UI says "offline". Drains on reconnect. |
| Supabase unreachable | Same as Render down — Render depends on it. |
| GitHub unreachable | `sync` job retries with backoff. No user impact; a "last synced" indicator goes stale. |
| Provider error | CRS §10.2 codes unchanged. `provider_auth` / `provider_quota` → not retryable, prompt for key. Router may fall back to the next configured provider. |
| Decryption failure on an item | That item shows a decrypt-error placeholder; cursor still advances (§4.2); rest of the conversation renders. |
| Passphrase lost | Recovery mnemonic flow (§5). No mnemonic → data is gone, and the UI always said so. |
| Retention gap on reconnect | `sync.required` → client discards local conversation state, reloads from Supabase (CRS §8.3). |

---

## 15. What Web does not have (vs desktop V2)

| Desktop capability | Web | Why |
|---|---|---|
| On-device PII scrubbing before model calls (Privacy Mirror) | **removed** | D7. Plaintext context is inherent to BYO cloud inference; a JS scrubber would be security theatre. |
| Fully-local inference, no cloud account, no network | **not available** | A tab cannot host a real local model. WebGPU/WebLLM is a possible later add (§17), not a substitute. |
| OS-level AppContainer sandbox isolation | **downgraded to WASM** | No browser equivalent for FS/network/process isolation (§13). |
| Runtime keeps streaming through a client drop | **downgraded** | Zero-knowledge forbids a server-side token source (§4.4). |
| Single-file local vault the user physically holds | **replaced** | Vault is the wrapped-DEK + ciphertext in Supabase and the user's repo (§5). Equivalent control, different medium. |

`PRODUCT.md` positioning claims 1 (nothing leaves unscrubbed) and 4 (runs
fully local) do not hold for web and must be qualified wherever the web build
is described. Claims 2 (verified runtime) and 3 → (WASM, not OS) need the
asterisk in §13.

---

## 16. Build sequence

Each phase ships and leaves a working app. CRS migration-stage parallels in
brackets.

**Phase 1 — Foundation** *(CRS stages 0–3)*
Repo + Pages deploy (`base: /primnox-chat/`). Supabase project, Auth, RLS
schema. Render service: JWT verify, `event_seq`, atomic event append,
WebSocket fan-out, turn/job lifecycle, origin watchdog. Crypto core (Argon2id,
KEK/DEK, wrap/unwrap, BIP-39 recovery, passphrase change). GitHub App
registration + connect flow + `sync` job. Client: reducer, Context Bundle
builder, Model Router (OpenRouter + Anthropic + Gemini), direct streaming with
encrypt-then-POST, conversations/folders/turns, IndexedDB cache + offline
outbox. **Deliverable:** encrypted, multi-device, streaming chat with
BYO key; conversations mirrored to the user's repo.

**Phase 2 — Memory** *(desktop `memory/`)*
transformers.js embedder, encrypted `memories`, client retrieval/ranking,
poisoning classifier, `MemoryPanel`, memory promotion from turns.

**Phase 3 — Assets & Canvas** *(CRS stages 4–5)*
Asset ingest/extract in-browser, encrypted `extracted_text`, versioned
workspaces, CRDT Canvas (`canvas_updates`, snapshotting), `Canvas` /
`AssetPreview` / `AssetVersions` components.

**Phase 4 — Knowledge graph** *(desktop `knowledge/`)*
Client-side graph build over ingested assets and memory, scoped queries,
`GraphPanel`, `FlowchartBlock`.

**Phase 5 — Tools & WASM sandbox** *(CRS stage 6)*
Universal tool protocol, Model Capability Layer emulation grammar, Pyodide /
QuickJS host, capability gating, `PermissionBlock` / `ExecutionBlock` /
`permission.request` flow.

**Phase 6 — Ambient** *(CRS stage 7)*
Render triggers + client-composed content, reminders, proactive suggestions,
promotion-only bridge, incognito polish.

Cross-cutting throughout: CRS/1.0-W conformance checks, a layered test suite
(L0 contracts → L4 chaos) adapted from `backend/tests/`, WCAG 2.1 AA held as a
defect line.

---

## 17. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | Argon2id exact params vs. target-hardware unlock time. | Phase 1 crypto core. |
| Q2 | Embedding model: `bge-small-en-v1.5` vs `all-MiniLM-L6-v2` vs a newer small model. | Phase 2. |
| Q3 | Vector search at scale: brute force vs in-JS HNSW, and the crossover point. | Phase 2. |
| Q4 | CRDT library: Yjs vs Automerge. | Phase 3. |
| Q5 | Render tier: free + cron pinger vs paid Starter — accept ~50 s cold start or not. | Phase 1 deploy. Operator (§18). |
| Q6 | Non-CORS providers: ship the tunnel (§W4) in v1, or OpenRouter-only for OpenAI models. | Phase 1 Model Router. |
| Q7 | Provider list beyond OpenRouter/Anthropic/Gemini for Phase 1. | Phase 1. |
| Q8 | Fan-out transport: Supabase Realtime vs a Render-owned WebSocket. | Phase 1. |
| Q9 | Recovery UX: force mnemonic capture at setup, or allow "no recovery, I accept". | Phase 1. |
| Q10 | Envelope metadata minimisation — is `kind` granularity a leak worth reducing. | design review. |
| Q11 | WebGPU/WebLLM local-inference option as a later phase — in or out of roadmap. | roadmap. |

### 17.1 Resolved for Phase 1 (2026-08-30)

| # | Resolution | Rationale |
|---|---|---|
| Q5 | **Render free tier + a 10-minute cron pinger** (GitHub Actions hitting `/health`). Upgrade to paid Starter when there are real users. | No cost during build-out; the pinger keeps the service warm through any active session, so the ~50 s cold start only bites a truly idle account. |
| Q6 | **OpenRouter-only for OpenAI models in v1.** The §W4 tunnel ships disabled and is wired in Phase 5 with the tools work. | OpenRouter gives OpenAI-model access on the user's own billing and is browser-safe. The tunnel is the one zero-knowledge hole and must not be rushed. v1 providers: OpenRouter, Anthropic (with header), Gemini, Groq. |
| Q8 | **Supabase Realtime for fan-out.** Render still owns sequence assignment and the atomic append (writes go client → Render → Postgres); clients *subscribe* to `events` inserts via Realtime, RLS-filtered to their own rows. | Render's free tier sleeps and drops WebSocket connections; Realtime is always-on, reconnects itself, and the client already holds a Supabase connection for Auth. Receiving fan-out no longer needs Render up. |
| Q9 | **Force recovery-mnemonic capture at setup**, with a typed word-count confirmation. An explicit "I don't want recovery" path exists behind a second confirm that states the data is permanently unreadable without the passphrase. | Matches the desktop BIP-39 vault. The escape hatch respects autonomy while making the consequence unmissable. |

Q1–Q4, Q7, Q10, Q11 remain open and are settled inside their phase.

---

## 18. Operator setup (human, not code)

1. **GitHub** — create the personal repo `cyanexani/primnox-chat`; enable
   Pages (Actions or branch). Register the **Primnox Data** GitHub App
   (Contents RW, Metadata R; single-repo install); store its private key +
   client secret as Render secrets.
2. **Supabase** — new project; enable Auth (email + GitHub OAuth); apply the
   §9.1 schema + RLS; note the project URL, anon key, JWT secret / JWKS URL.
3. **Render** — new web service from the backend repo; env: Supabase JWKS,
   service DB URL, GitHub App creds, `origin_grace_seconds`, rate limits.
   Decide Q5 (paid vs pinger).
4. **SPA config** — Vite `base: '/primnox-chat/'`; env: Supabase URL + anon
   key, Render API base, GitHub App slug.
5. **First run** — sign in → connect GitHub → set passphrase → capture the
   recovery mnemonic → add a provider key. The key and vault land in the repo,
   encrypted.

Claude can do 3–5 and scaffold everything in Phase 1; steps 1–2 and the
secret material are account actions for the operator.

---

## Appendix A — rule index (web)

Rules that, if violated, break the web privacy posture or reintroduce a CRS/1.0
defect.

| Rule | What it prevents |
|---|---|
| §4.2 payload ciphertext, envelope clear | server-readable content; also a broken cursor if a blob won't decrypt |
| §4.1 Supabase is the one runtime DB | replayed stream disagreeing with stored state (CRS §4.1) |
| §4.3 encrypt-then-POST before render-as-committed | a token shown to the user but unrecoverable on reload |
| §4.4 origin watchdog + partial-text preserve | a dead tab leaving a turn wedged forever; a stop/crash destroying the half-written answer |
| §4.6 no scrubber, but `model.egress` audit | a silent claim that content was protected when it was not |
| §W1 no server-held key material | "passphrase → plaintext DB key on the server", the thing zero-knowledge exists to forbid |
| §W2 sync never fails the turn | a GitHub outage taking down the chat |
| §W4 tunnel off by default, loud when on | plaintext routed through Render without the user knowing |
| §5 AAD binds blob to envelope | a ciphertext blob silently relocated to another message/event |
| §13 "not equivalent to AppContainer" | marketing a WASM sandbox as OS isolation |
