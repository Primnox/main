# Capability catalog — all 300

Numbered as in the master spec, so a capability can be named by number ("run 148")
and mean the same thing every time.

The **How** column names the actual tool. Tags used throughout:

- `browser` — Browser pane tools (`read_page`, `computer`, `read_console_messages`, …)
- `pytest` — the backend suite at `v2/backend/tests`
- `shell` — a command
- `read` — static reading of source; no runtime needed
- `⚠ no harness` — nothing automated exists; needs manual work or new tooling. Say so rather than faking a pass.

Contents: [1 UI](#1-ui--interaction-125) · [2 Visual](#2-visual-validation-2645) · [3 Frontend Logic](#3-frontend-logic-4665) · [4 Backend & API](#4-backend--api-6690) · [5 Performance](#5-performance-91115) · [6 Reliability](#6-reliability--chaos-116140) · [7 Security](#7-security-141165) · [8 AI Systems](#8-ai-systems-166195) · [9 Hardware](#9-hardware-diagnostics-196215) · [10 File System](#10-file-system-216230) · [11 Accessibility](#11-accessibility-231245) · [12 Installer](#12-installer--updates-246255) · [13 Observability](#13-observability-256265) · [14 CI/CD](#14-cicd--release-266275) · [15 Data Integrity](#15-data-integrity-276285) · [16 Privacy](#16-privacy--compliance-286290) · [17 Advanced](#17-advanced-intelligence-291300)

---

## 1. UI & Interaction (1–25)

| # | Capability | How |
|---|---|---|
| 1 | Button validation | `browser` click each control, assert the state change in `read_page` |
| 2 | Form validation | `browser` `form_input` valid + invalid + empty + boundary values |
| 3 | Navigation flow | `browser` walk every route; assert arrival and back-navigation |
| 4 | Modal behavior | `browser` open, Esc, backdrop click, focus trap, scroll lock |
| 5 | Dropdown behavior | `browser` open/close, keyboard select, outside click, selection persists |
| 6 | Context menus | `browser` `right_click`; assert items and dismissal |
| 7 | Drag and drop | `browser` `left_click_drag`; assert reorder committed to state |
| 8 | Window resize | `browser` `resize_window` across breakpoints; check reflow |
| 9 | Fullscreen | `browser` toggle; assert layout holds and exit restores |
| 10 | Multi-monitor | ⚠ no harness — manual, note DPI change on move |
| 11 | Scroll behavior | `browser` scroll containers; check sticky headers, no body h-scroll |
| 12 | Keyboard shortcuts | `browser` `key` each binding; assert action and no conflicts |
| 13 | Focus order | `browser` repeated Tab; assert order matches visual order |
| 14 | Hover states | `browser` `hover` then screenshot; desktop viewport only |
| 15 | Loading states | Run against real backend; assert spinner/skeleton appears and clears |
| 16 | Empty states | Fresh `PRIMNOX2_HOME`; assert empty copy, not a blank panel |
| 17 | Error screens | Stop the backend, act, assert a real message not a stack trace |
| 18 | Theme consistency | `resize_window` `colorScheme` light+dark; screenshot both |
| 19 | Toast notifications | Trigger, assert text, auto-dismiss, and stacking |
| 20 | Search behavior | Query with hits, no hits, special chars; assert result and empty state |
| 21 | Settings persistence | Change, reload page, assert value survived (`settings/service.py`) |
| 22 | Clipboard actions | `browser` copy control, then read clipboard via `javascript_tool` |
| 23 | File picker | ⚠ no harness — native dialog; test the handler directly instead |
| 24 | Right-click actions | `browser` `right_click` on each target surface |
| 25 | Gesture support | `resize_window` mobile preset to enable touch; then drive |

## 2. Visual Validation (26–45)

No visual-regression tooling exists. Everything here is screenshot + inspection, or
computed-style assertions via `javascript_tool`, which are far more reliable than
eyeballing pixels.

| # | Capability | How |
|---|---|---|
| 26 | Screenshot comparison | `browser` screenshot before/after; compare by eye ⚠ no baseline store |
| 27 | Pixel difference | ⚠ no harness — needs a baseline system; propose before claiming |
| 28 | Color consistency | `javascript_tool` read `getComputedStyle` vs design tokens |
| 29 | Font consistency | `javascript_tool` collect `font-family`/`size` across nodes; look for strays |
| 30 | Icon validation | `read_page` assert every icon has an accessible name |
| 31 | Alignment | Screenshot; check shared edges and grid adherence |
| 32 | Spacing | `javascript_tool` read margins/padding against the spacing scale |
| 33 | Border radius | `javascript_tool` compare `border-radius` against tokens |
| 34 | Shadows | Computed `box-shadow` matches the elevation scale |
| 35 | Transparency | Check alpha layers stay legible in both themes |
| 36 | Overflow detection | `javascript_tool`: `scrollWidth > clientWidth` on every container |
| 37 | Z-index conflicts | Open modal + toast + dropdown together; assert stacking |
| 38 | Blur detection | Check transforms on non-integer pixels causing text blur |
| 39 | Animation smoothness | `browser` observe; check for layout-triggering properties |
| 40 | Responsive layout | `resize_window` mobile/tablet/desktop; no horizontal body scroll |
| 41 | Image rendering | `read_network_requests` for 404s; assert intrinsic sizing |
| 42 | SVG rendering | Assert viewBox scaling and `currentColor` inheritance |
| 43 | High-DPI rendering | `resize_window` + DPR change; check raster asset crispness |
| 44 | Dark mode visuals | `colorScheme: dark`, screenshot every surface |
| 45 | Light mode visuals | `colorScheme: light`, same |

## 3. Frontend Logic (46–65)

| # | Capability | How |
|---|---|---|
| 46 | React state | Drive the UI and assert rendered output ⚠ no unit runner |
| 47 | Hook dependencies | `read` deps arrays for missing/extra entries causing stale closures |
| 48 | Component re-renders | `javascript_tool` instrument render counts; watch for loops |
| 49 | Event listeners | `read` that every `addEventListener` has a matching removal |
| 50 | DOM mutations | `javascript_tool` MutationObserver during interaction |
| 51 | Local storage | `javascript_tool` inspect keys before/after; assert reload restores |
| 52 | Session storage | Same, and assert it clears with the session |
| 53 | Cookies | Inspect `document.cookie`; check flags on anything auth-related |
| 54 | Route transitions | Navigate; assert unmount cleanup and no state bleed |
| 55 | Lazy loading | `read_network_requests`; assert chunks load on demand not upfront |
| 56 | Suspense boundaries | Throttle/kill backend; assert fallback renders, not a blank screen |
| 57 | Client cache | Repeat a fetch; assert cache hit and correct invalidation |
| 58 | Memory cleanup | Mount/unmount repeatedly; watch heap via `javascript_tool` |
| 59 | Hydration | `read_console_messages` for hydration mismatch warnings |
| 60 | Async race conditions | Fire overlapping requests; assert last-write-wins is correct |
| 61 | Debounce logic | Rapid input; count requests in `read_network_requests` |
| 62 | Throttle logic | Rapid scroll/resize; assert handler rate is capped |
| 63 | State persistence | Reload; assert intended state survives and the rest resets |
| 64 | Undo/redo | Apply a sequence, undo to start, redo to end; assert equality |
| 65 | Offline state | Kill the backend; assert offline messaging and recovery on return |

## 4. Backend & API (66–90)

Primary harness: `pytest` at L0–L3. See `references/backend.md`.

| # | Capability | How |
|---|---|---|
| 66 | REST APIs | `pytest` L2 http — status, shape, error bodies |
| 67 | GraphQL | Not used in this stack — skip unless one appears |
| 68 | WebSockets | `pytest` — see `test_ws_origin.py`; connect, stream, disconnect |
| 69 | gRPC | Not used — skip |
| 70 | Authentication | `pytest` — unauthenticated request must be rejected |
| 71 | Authorization | `pytest` — each role against each endpoint |
| 72 | Refresh tokens | Expire then refresh; assert rotation and old token rejection |
| 73 | Session expiry | Advance clock/TTL; assert clean expiry not a 500 |
| 74 | Permission matrix | Table-driven test over (role × endpoint × verb) |
| 75 | Database reads | `pytest` L1/L2 against the `fresh_db` fixture |
| 76 | Database writes | Assert persisted state, not just the response |
| 77 | Transactions | `pytest` L4 — interrupt mid-transaction, assert atomicity |
| 78 | Migrations | `test_schema_migrations.py` — forward, and re-run idempotency |
| 79 | Cache invalidation | Mutate the source, assert the cached read updates |
| 80 | File uploads | Size limits, wrong MIME, malformed payload |
| 81 | File downloads | Content-type, filename, and path-traversal resistance |
| 82 | Streaming responses | Assert first token arrives before completion (core V2 promise) |
| 83 | API contracts | `pytest` L0 `test_l0_contracts.py` — the schema gate |
| 84 | Rate limits | Burst past the limit; assert 429 and recovery |
| 85 | Retry logic | Force a transient failure; assert bounded retries with backoff |
| 86 | Timeouts | Stall a dependency; assert the timeout fires and is surfaced |
| 87 | Queue processing | `kernel/scheduler.py` — enqueue, assert ordering and drain |
| 88 | Cron jobs | Assert scheduled work fires once, and is idempotent |
| 89 | Pagination | Boundaries: page 0, last page, past the end, changed page size |
| 90 | Webhooks | Assert delivery, signature verification, and retry on failure |

## 5. Performance (91–115)

Budgets live in `test_perf_budgets.py`. `turn_accepted` (50ms) is the load-bearing one.

| # | Capability | How |
|---|---|---|
| 91 | Cold startup | Time first launch with empty caches |
| 92 | Warm startup | Time relaunch; compare against cold |
| 93 | CPU usage | Sample during a turn; look for busy-wait |
| 94 | RAM usage | Sample at idle and under load |
| 95 | Memory leaks | Repeat the same operation 100× and watch RSS trend |
| 96 | VRAM usage | ⚠ no harness — only if GPU inference is in play |
| 97 | GPU utilization | ⚠ no harness — same |
| 98 | FPS | `browser` observe animation; check for dropped frames |
| 99 | Frame timing | `javascript_tool` `requestAnimationFrame` deltas |
| 100 | Input latency | Time from `computer` input to DOM change |
| 101 | Disk read speed | Time bulk reads against the local store |
| 102 | Disk write speed | Time bulk writes; watch for fsync-per-row |
| 103 | Random I/O | Time scattered reads on a large DB |
| 104 | Network latency | `read_network_requests` timings |
| 105 | DNS timing | Only relevant for cloud providers; check first-call penalty |
| 106 | Bundle size | `npm --prefix v2/frontend run build`; inspect `dist` sizes |
| 107 | Asset loading | `read_network_requests` — waterfall, blocking resources |
| 108 | Garbage collection | Watch for GC pauses during streaming |
| 109 | Thread utilization | Assert worker threads aren't starving the event loop |
| 110 | Idle resource usage | Sample with the app open and untouched — should be ~0 |
| 111 | Battery usage | ⚠ no harness — infer from idle CPU |
| 112 | Thermal behavior | ⚠ no harness — sustained-load observation |
| 113 | Background processes | Assert no orphans after quit (see 122) |
| 114 | Render bottlenecks | Profile long tasks in the browser |
| 115 | Performance regression | `pytest v2/backend/tests/test_perf_budgets.py` — the gate |

## 6. Reliability & Chaos (116–140)

`test_l4_chaos.py` already does several of these. Extend it rather than starting over.

| # | Capability | How |
|---|---|---|
| 116 | Forced crashes | Kill the process mid-operation; assert recoverable state |
| 117 | Power loss simulation | `SIGKILL` (no cleanup) then restart; assert no torn state |
| 118 | Network disconnect | Drop the backend mid-stream; assert the turn terminates |
| 119 | Low RAM simulation | Constrain memory; assert graceful degradation |
| 120 | Disk full simulation | L4 already covers this — assert the error is surfaced |
| 121 | Slow storage simulation | Inject latency; assert timeouts fire rather than hang |
| 122 | Process termination | Kill sandbox child mid-execution; assert parent recovers |
| 123 | Auto-save recovery | Kill before save; assert no partial write on restart |
| 124 | Session recovery | Restart; assert the conversation reloads intact |
| 125 | Sleep/wake | Suspend the host; assert reconnect on wake |
| 126 | Hibernation | Same, across a full hibernate cycle |
| 127 | Update interruption | Kill mid-update; assert rollback or clean resume |
| 128 | File locking | Concurrent writers to the DB; assert no corruption |
| 129 | Permission denial | Make the data dir read-only; assert a real error |
| 130 | Corrupted config | Write malformed settings; assert fallback to defaults |
| 131 | Corrupted database | Truncate the DB file; assert detection not a crash loop |
| 132 | Infinite clicking | `browser` `repeat` clicks; assert no duplicate side effects |
| 133 | Rapid shortcuts | Fire shortcuts faster than handlers settle |
| 134 | Window flooding | Open many windows/modals; assert no leak |
| 135 | Multi-instance | Launch twice; assert DB locking is handled |
| 136 | Recovery verification | After every chaos case, assert the invariant below |
| 137 | Retry exhaustion | Fail past max retries; assert a terminal, readable error |
| 138 | Timeout recovery | After a timeout, assert the next request succeeds |
| 139 | Unexpected shutdown | Kill at each lifecycle stage |
| 140 | Rollback verification | Assert a failed transaction leaves zero trace |

**The invariant every chaos case asserts** (from `test_l4_chaos.py`): never a completed
turn with no event, never an event with no turn, never a turn left non-terminal.

## 7. Security (141–165)

See `references/security.md`. Existing coverage: `test_csrf_origin.py`, `test_ws_origin.py`,
`test_tool_escapes.py`, `test_vault.py`.

| # | Capability | How |
|---|---|---|
| 141 | API key detection | `grep` the diff for key-shaped strings before commit |
| 142 | Secret scanning | Scan tracked files and history for credentials |
| 143 | Environment variables | Assert secrets come from env, never literals |
| 144 | Dependency vulnerabilities | `npm audit`; check Python deps against advisories |
| 145 | Permission auditing | Review what the app can reach on disk and network |
| 146 | Open ports | Assert only 4109 listens, and only on loopback |
| 147 | Localhost exposure | Assert bind is `127.0.0.1`, never `0.0.0.0` |
| 148 | SQL injection | Assert parameterized queries; fuzz string inputs |
| 149 | Command injection | `test_tool_escapes.py` — shell metacharacters in tool args |
| 150 | XSS | Inject `<script>` via chat/markdown; assert escaped |
| 151 | CSRF | `test_csrf_origin.py` — cross-origin request rejected |
| 152 | CSP validation | Assert the header exists and blocks inline script |
| 153 | HTTPS enforcement | For any external call, assert TLS |
| 154 | Certificate validation | Assert verification is never disabled |
| 155 | OAuth flow | State parameter, redirect allow-list, code exchange |
| 156 | Token validation | Expired, malformed, wrong-signature all rejected |
| 157 | Session hijacking | Assert tokens aren't logged or placed in URLs |
| 158 | Directory traversal | `../` in any path-bearing parameter |
| 159 | File permission leaks | Assert restrictive modes on the data dir |
| 160 | Clipboard leaks | Assert secrets never auto-copied |
| 161 | Temp file exposure | Assert temp files are scoped and removed |
| 162 | Unsafe configs | Assert debug/verbose off in release builds |
| 163 | Encryption validation | `test_vault.py` — at-rest encryption of sensitive fields |
| 164 | Secure storage | Assert `storage/vault.py` is used, not plain rows |
| 165 | Security regression | Re-run the security tests as a gate on every change |

## 8. AI Systems (166–195)

The domain most specific to Primnox. See `references/ai-systems.md`. Use the
**echo backend** for anything where the model shouldn't be the variable.

| # | Capability | How |
|---|---|---|
| 166 | Prompt consistency | Assert assembled prompt is stable for stable inputs |
| 167 | Memory recall | Store a fact, ask later, assert retrieval |
| 168 | Memory persistence | Restart; assert memory survives (`test_memory.py`) |
| 169 | Memory conflicts | Store contradicting facts; assert a defined resolution |
| 170 | Context overflow | Exceed the window; assert truncation not a crash |
| 171 | Context compression | Assert compaction preserves the load-bearing content |
| 172 | Tool invocation | Assert the right tool fires with the right args |
| 173 | Tool routing | `test_tool_routing.py` |
| 174 | Model routing | `test_model_profiles.py` — right model per task |
| 175 | Hallucination detection | Ask about absent data; assert refusal over invention |
| 176 | Citation validation | Assert cited sources exist and support the claim |
| 177 | Response consistency | Same input × N; measure variance |
| 178 | Reasoning stability | Assert conclusions hold across paraphrases |
| 179 | Decision consistency | Same decision point × N; assert stability |
| 180 | Conversation continuity | Multi-turn; assert earlier turns stay in scope |
| 181 | Personality consistency | Assert tone holds across a long session |
| 182 | STT accuracy | ⚠ no harness — fixture audio needed |
| 183 | TTS quality | ⚠ no harness — manual listen |
| 184 | Voice interruption | Assert barge-in stops playback and captures input |
| 185 | Wake word | ⚠ no harness — false-positive rate needs a corpus |
| 186 | Multi-agent coordination | Assert handoffs preserve context |
| 187 | Agent retry logic | Force a tool failure; assert bounded retry |
| 188 | RAG accuracy | Assert retrieved chunks are relevant to the query |
| 189 | Embedding quality | Assert near-duplicates rank adjacent |
| 190 | Token efficiency | Track tokens per turn; watch for prompt bloat |
| 191 | Response latency | `first_token` budget (400ms) in perf budgets |
| 192 | Prompt injection resistance | `test_sdl_inject.py` — instructions in tool output must not execute |
| 193 | Memory indexing | `test_knowledge_graph.py`, `test_facts_graph.py` |
| 194 | Skill conflict detection | Assert overlapping skills resolve deterministically |
| 195 | AI regression | Golden outputs — `test_golden.py`, `tests/golden/` |

## 9. Hardware Diagnostics (196–215)

Mostly `⚠ no harness` — these need real devices. Report them as manual, and don't
claim a pass on a device you never touched.

| # | Capability | How |
|---|---|---|
| 196 | Microphone | `browser` getUserMedia permission + level check |
| 197 | Speakers | Manual playback |
| 198 | Webcam | `browser` getUserMedia video track |
| 199 | Autofocus | Manual |
| 200 | CPU temperature | OS sensor query |
| 201 | GPU temperature | OS sensor query |
| 202 | SSD health | SMART query |
| 203 | HDD SMART | SMART query |
| 204 | Battery health | `powercfg /batteryreport` |
| 205 | Charger detection | OS power state |
| 206 | USB devices | Enumerate via OS |
| 207 | Bluetooth | Enumerate adapters/pairing |
| 208 | Wi-Fi | Adapter state and throughput |
| 209 | Ethernet | Link state |
| 210 | Keyboard ghosting | Manual N-key rollover |
| 211 | Touchpad | Manual gestures |
| 212 | Display refresh | Report mode from OS |
| 213 | Dead pixels | Manual full-screen colors |
| 214 | Color accuracy | Manual/colorimeter |
| 215 | Fan behavior | Sustained load observation |

## 10. File System (216–230)

| # | Capability | How |
|---|---|---|
| 216 | Duplicate files | Hash and group |
| 217 | Corruption detection | Checksum against a known-good manifest |
| 218 | Permissions | Assert the data dir isn't world-readable |
| 219 | Symbolic links | Assert links can't escape the data root |
| 220 | Temp files | Assert cleanup on exit |
| 221 | Backup integrity | Assert the backup restores to an identical DB |
| 222 | Restore validation | Restore into a clean home; assert full function |
| 223 | File watchers | Assert watchers detach and don't leak handles |
| 224 | Large files | Assert streaming, not full read into memory |
| 225 | Encoding | Non-UTF8 and BOM inputs |
| 226 | Path length | Windows >260-char paths |
| 227 | Hidden files | Assert correct handling, not crashes |
| 228 | Archive extraction | Zip-slip resistance |
| 229 | Cloud sync | Data dir under OneDrive — assert DB locking survives |
| 230 | Disk space prediction | Assert growth is bounded and estimable |

## 11. Accessibility (231–245)

`read_page` returns the accessibility tree — it is the primary tool here and is more
reliable than a screenshot for everything except contrast.

| # | Capability | How |
|---|---|---|
| 231 | Screen readers | `read_page` — assert every control has a name and role |
| 232 | Keyboard navigation | `browser` Tab/Enter/Esc through every flow, no mouse |
| 233 | Contrast | `javascript_tool` compute ratios; 4.5:1 text, 3:1 UI |
| 234 | Focus visibility | Tab and screenshot; assert a visible ring |
| 235 | Font scaling | Set root font to 200%; assert no clipping |
| 236 | Reduced motion | `prefers-reduced-motion`; assert animation suppressed |
| 237 | Captions | Assert media has caption tracks |
| 238 | Voice navigation | Assert controls are addressable by visible name |
| 239 | Color blindness | Assert state is never signalled by hue alone |
| 240 | Zoom compatibility | 200% browser zoom; no loss of function |
| 241 | Touch targets | Assert ≥44×44px in mobile viewport |
| 242 | Reading order | `read_page` order matches visual order |
| 243 | Accessible names | Every icon-only control named (a known past defect here) |
| 244 | ARIA validation | Assert roles are valid and not redundant |
| 245 | Landmark validation | Assert main/nav/banner exist and are unique |

## 12. Installer & Updates (246–255)

Tauri build — `v2/frontend/src-tauri`, `.github/workflows/build-windows.yml`.

| # | Capability | How |
|---|---|---|
| 246 | Fresh install | Clean VM; assert first launch works |
| 247 | Upgrade | Install old → new; assert data migrates |
| 248 | Downgrade | Assert refusal or safe handling, never data loss |
| 249 | Uninstall | Assert files removed and user data handled per policy |
| 250 | Registry cleanup | Assert no orphan registry keys |
| 251 | Shortcut validation | Assert shortcuts resolve post-install |
| 252 | Startup entries | Assert no unrequested autostart |
| 253 | Dependency installation | Assert bundled runtime deps are present |
| 254 | Update integrity | Assert signature/hash verified before applying |
| 255 | Rollback install | Assert a failed update reverts cleanly |

## 13. Observability (256–265)

| # | Capability | How |
|---|---|---|
| 256 | Log analysis | Assert errors are logged with context and no secrets |
| 257 | Trace validation | Assert a turn is traceable end to end |
| 258 | Metrics validation | Assert counters move as expected |
| 259 | Error fingerprinting | Assert like errors group under one signature |
| 260 | Crash symbolication | Assert stack traces resolve to source |
| 261 | Session replay | `test_replay_recorder.py` — replay reproduces state |
| 262 | Event sequencing | Assert event order is deterministic and total |
| 263 | Performance traces | Assert timings are captured per stage |
| 264 | Alert simulation | Force the condition; assert the alert fires |
| 265 | Dashboard validation | Assert displayed values match the source |

## 14. CI/CD & Release (266–275)

| # | Capability | How |
|---|---|---|
| 266 | Build reproducibility | Build twice; compare artifacts |
| 267 | Artifact verification | Assert the artifact contains what it should |
| 268 | Signature verification | Assert the binary is signed |
| 269 | Canary validation | Assert a staged rollout can be halted |
| 270 | Environment parity | Assert dev and CI resolve the same deps |
| 271 | Version consistency | Assert version matches across manifests and tags |
| 272 | Release notes validation | Assert notes cover the actual diff |
| 273 | Pipeline stability | Assert no flaky steps across recent runs |
| 274 | Build timeout prediction | Track build duration trend |
| 275 | Release readiness | The full gate: L0–L4 + perf + security all green |

## 15. Data Integrity (276–285)

| # | Capability | How |
|---|---|---|
| 276 | Schema drift | Assert the live schema matches migrations |
| 277 | Referential integrity | Assert FK relationships hold |
| 278 | Duplicate records | Assert uniqueness constraints are enforced |
| 279 | Orphan records | Assert children are cleaned with parents |
| 280 | Timestamp consistency | Assert monotonic ordering on events |
| 281 | Timezone validation | Assert UTC storage and correct local display |
| 282 | Backup verification | See 221 |
| 283 | Restore verification | See 222 |
| 284 | Checksum validation | Assert stored hashes match content |
| 285 | Sync validation | Assert convergence after concurrent writes |

## 16. Privacy & Compliance (286–290)

Existing coverage: `test_privacy_mirror.py`, `primnox2/privacy/`.

| # | Capability | How |
|---|---|---|
| 286 | PII detection | Assert the PII model flags names/emails/IDs before egress |
| 287 | Consent validation | Assert no data leaves without recorded consent |
| 288 | Data retention | Assert old data ages out per policy |
| 289 | Secure deletion | Assert delete removes rows and derived artifacts |
| 290 | Audit logs | Assert privacy-relevant actions are logged |

## 17. Advanced Intelligence (291–300)

These are meta-capabilities: modes of investigation rather than single checks. Reach
for them when a defect resists the direct approach.

| # | Capability | How |
|---|---|---|
| 291 | Autonomous bug hunting | Explore unprompted; drive the app looking for breakage |
| 292 | Root cause synthesis | Correlate logs, traces, and diff into one causal story |
| 293 | Risk prediction | Rank changed areas by blast radius before testing |
| 294 | Test generation | Write the missing test for the uncovered path |
| 295 | Coverage gap detection | Compare the 300 against what the suite actually asserts |
| 296 | Failure clustering | Group failures by shared cause, not by test name |
| 297 | Behavior fingerprinting | Capture a behavioral baseline to diff against later |
| 298 | Time-travel comparison | `git stash` / checkout the parent commit; compare behavior |
| 299 | Human behavior simulation | Drive the app as an impatient user: double-click, spam Esc |
| 300 | Self-evolving edge case discovery | Feed each finding back as a new permanent test |
