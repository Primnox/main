# Platform: hardware, filesystem, installer, observability, CI/CD

Covers domains 9 (196–215), 10 (216–230), 12 (246–255), 13 (256–265), and
14 (266–275). These share a property: most of them can't be verified from a normal
dev session, and pretending otherwise is the main risk in this group.

## Hardware (196–215)

Almost entirely without a harness. These need real devices, real sensors, and in
several cases a human looking at a screen.

What's genuinely automatable from here:

- **Microphone (196) / webcam (198)** — `browser` `getUserMedia`; assert the
  permission flow works and a track is produced. That tests *your integration*, which
  is usually the actual question.
- **Battery (204)** — `powercfg /batteryreport` on Windows.
- **Network adapters (208, 209)** — OS query for link state.

Everything else — temperatures, SMART health, dead pixels, ghosting, fan behaviour,
color accuracy — is manual. Report them as **not checked, needs hardware**. A
hardware capability marked green by an agent that never touched hardware is worse
than an obvious gap, because it stops anyone else from looking.

## Filesystem (216–230)

More testable, and several of these are real Windows-specific risks for this app:

- **Path length (226)** — Windows paths over 260 characters. Primnox stores under
  `PRIMNOX2_HOME`, and a deep user path plus generated filenames gets there faster
  than you'd expect. Test with a genuinely long home path.
- **Cloud sync (229)** — if the data directory lands under OneDrive (common on
  Windows, and the default Documents folder is frequently synced), SQLite file
  locking meets a sync client that wants to hold the file. This is a real corruption
  vector, not a theoretical one.
- **Symlinks (219)** and **archive extraction (228)** — both are containment
  questions: can anything escape the data root? See `references/security.md`.
- **Large files (224)** — assert streaming rather than a full read into memory. The
  failure only appears at a size no one tests with by accident.
- **Encoding (225)** — non-UTF8 input, BOMs, and CRLF. This repo has a `.gitattributes`
  for a reason; line-ending surprises are a recurring Windows tax.
- **Temp file cleanup (220)** — assert temp files are scoped and removed on exit.
  Also a security concern (161) when they hold user content.
- **Backup/restore (221, 222)** — the only honest test is a round trip: back up,
  restore into a clean `PRIMNOX2_HOME`, and assert the app is fully functional. A
  backup that's never been restored is not a verified backup.

## Installer and updates (246–255)

The Tauri build lives at `v2/frontend/src-tauri`, built by
`.github/workflows/build-windows.yml`.

These need a clean machine or VM to test properly. From a dev box you can verify the
*artifact* but not the *installation*:

- **Fresh install (246)** — needs a clean VM. On a dev machine, dependencies are
  already present and you'll get a false pass. This is the single most common
  installer testing mistake.
- **Upgrade (247)** — the one that risks user data. Install the previous version,
  create real data, upgrade, assert the data migrated. Ties to schema migrations
  (78) — an upgrade path that drops the database is the worst-case bug in the whole
  catalog.
- **Update integrity (254)** and **signature verification (268)** — assert the
  signature is checked *before* the update is applied. Verify-after-apply is not
  verification.
- **Rollback (255)** and **update interruption (127)** — kill the updater mid-write
  and assert the app still launches. Users close laptops mid-update.
- **Startup entries (252)** — assert nothing adds itself to autostart without being
  asked.

## Observability (256–265)

The test is not "do we log" but "could someone diagnose a failure from what we
logged". Practical checks:

- **Log analysis (256)** — errors carry enough context to locate them, and carry no
  secrets or PII. Both halves matter and they pull against each other.
- **Trace validation (257)** and **event sequencing (262)** — a turn should be
  followable end to end, with a deterministic total order on events. This underpins
  replay; if ordering is ambiguous, replay becomes nondeterministic and every test
  built on it goes flaky in a way that's very hard to attribute.
- **Session replay (261)** — `test_replay_recorder.py`. The assertion is that replaying
  recorded events reproduces the same state.
- **Error fingerprinting (259)** — the same underlying error groups under one
  signature. Without it, one bug looks like a hundred and triage stalls.

A good way to test observability: pick a bug you already fixed, and ask whether the
logs alone would have led you to it. If not, that's the finding.

## CI/CD and release (266–275)

- **Environment parity (270)** — dev and CI resolving different dependency versions
  produces "works on my machine" failures that cost hours. Compare lockfile
  resolution, not just declared ranges.
- **Version consistency (271)** — one version, agreeing across `package.json`, the
  Tauri config, and the git tag. Drift here ships a build that lies about what it is.
- **Reproducibility (266)** — build twice, compare artifacts. Differences that aren't
  timestamps are worth understanding.
- **Pipeline stability (273)** — look across recent runs for steps that fail
  intermittently. A flaky pipeline trains everyone to re-run without reading, which
  is how a real failure ships.
- **Release readiness (275)** — the composite gate: L0–L4 green, perf budgets inside
  limits, security tests passing, typecheck clean, version consistent. This is the
  one to run when the question is "can we ship".

For CI investigation, `gh run list` and `gh run view --log-failed` beat opening the
web UI — the failed-log view goes straight to the failing step.
