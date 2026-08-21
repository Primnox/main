# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

General desktop users who want an AI assistant on their own machine. Not
assumed to be developers: the technical capabilities (sandboxed execution,
knowledge graph, local model routing) must stay usable without the user
understanding how any of them work. A privacy-conscious or technical user is
a subset to serve, never the floor to design for.

Single-user, single-machine. There are no accounts, no multi-tenancy, and no
server-side state — the whole product is one desktop app talking to a
loopback backend.

## Product Purpose

A personal AI environment that runs on the user's own machine: conversations,
persistent memory, document ingestion, a knowledge graph over what it has
read, and the ability to actually run code rather than only describe it.

Success is a user trusting it with real work — real documents, real context,
real credentials — because the boundaries are demonstrable rather than
promised.

## Positioning

Four claims, all confirmed as load-bearing. Each is a mechanism a competitor
would have to build, not a phrase they could copy:

1. **Nothing leaves unscrubbed.** On-device PII scrubbing before any outbound
   model call, and a BIP-39 mnemonic-encrypted database at rest (AES-256-GCM,
   PBKDF2-SHA512). The user holds a key the app cannot recover for them.
2. **Verified runtime, not vibes.** A normative written spec (CRS/1.0) with a
   layered verification suite proving the runtime behaves — including failure
   states, cancellation, crash recovery, and reconnect replay.
3. **Real OS-level sandboxed execution.** Model-generated code runs inside a
   genuine Windows AppContainer with filesystem, network, process, memory,
   CPU, and cross-execution isolation enforced by the OS.
4. **Runs fully local, any provider.** Works against a local model (Ollama,
   LlamaCpp) with no cloud account and no network at all. Cloud providers are
   optional and swappable, never required.

These are testable claims and are expected to stay tested. A change that
weakens one without measurement is a regression regardless of what it adds.

## Operating Context

Desktop app on Windows (current beta). A Tauri shell hosts the UI and
supervises a bundled backend on `127.0.0.1:4109`; all state lives in a single
SQLite database (`primnox.db`) under the user's profile.

The user works in long-running conversations, attaches their own documents,
and lets work accumulate: memory persists across chats, and ingested material
joins a knowledge graph the runtime consults on its own rather than waiting
to be asked.

Distribution is GitHub releases (NSIS installer). V2 is the product going
forward; V1's source is retained in-repo but no longer built or shipped.

## Capabilities and Constraints

Confirmed capabilities: folder-organised conversations with streaming replies
and visible model reasoning where the provider supports it; persistent
searchable memory with soft forgetting; document/asset ingestion with
extraction and preview; a knowledge graph with scoped queries; persistent and
ephemeral workspaces; sandboxed Python/Node/shell execution; incognito
conversations that write nothing to disk; per-provider model profiles.

Constraints that future work must respect:

- **Windows-only isolation.** The sandbox boundary is AppContainer. On any
  platform without it, execution is refused rather than silently downgraded.
- **Loopback only.** The backend binds localhost and verifies Origin on every
  state-changing request. It is not, and must not become, a network service.
- **One database.** Conversations, memory, and the graph share `primnox.db`,
  so there is exactly one file to encrypt, back up, or lose.
- **Honest failure over silent fallback.** A turn that produced nothing fails
  with a reason; isolation that cannot be established refuses to run.
- **Known gaps, stated rather than hidden:** registry reads inside the sandbox
  cannot be blocked by AppContainer alone; the sandbox disk limit is
  best-effort for sub-poll bursts; a locked vault cannot currently be recovered
  from the UI if the OS keychain entry is lost.

## Brand Commitments

Name: Primnox. Existing icon set and installer identity ship with the Tauri
bundle.

Voice, as established by the product's own copy: plain, specific, and
non-euphemistic — failure states say what happened and what was lost, and
permission prompts say what will actually run. Marketing register is avoided
inside the product.

## Evidence on Hand

- Normative specs: `docs/CONVERSATION_RUNTIME_SPEC.md`, `docs/ARCHITECTURE_V2.md`.
- Verification suite: `v2/backend/tests/` (611 passing at time of writing),
  layered L0 contracts through L4 chaos, plus perf budgets.
- Measured sandbox boundary results (filesystem, network, credentials,
  clipboard, process handles, named pipes, resource limits, cross-execution
  isolation) recorded in `v2/backend/tests/test_sandbox_isolation.py`.
- Real shipping installer pipeline: `.github/workflows/build-windows.yml`.

No customer testimonials, usage numbers, benchmarks, press, or pricing exist.
Future work must not fabricate any of these.

## Product Principles

1. **A boundary that isn't measured isn't a boundary.** Every privacy or
   isolation claim is backed by a test that would fail if it stopped being
   true.
2. **Local is the default, not the fallback.** The product must remain fully
   usable with no cloud account and no network.
3. **Say what actually happened.** Errors, permissions, and limits are
   reported specifically, including when the answer is unflattering.
4. **Technical depth, non-technical surface.** Power features must not require
   understanding their implementation to use safely.
5. **The user's data outlives the session.** Memory, documents, and the graph
   accumulate and remain the user's to inspect, export, or delete.

## Accessibility & Inclusion

**WCAG 2.1 AA** is the target standard. Contrast ratios, keyboard reachability
for every interactive control, visible focus, and accessible names are held to
AA, and a regression against it is treated as a defect rather than a polish
item.
