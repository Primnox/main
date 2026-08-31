# Primnox Strategic Roadmap

## The Vision

Primnox is building a **privacy-first personal OS**—a unified platform that combines calendar, tasks, notes, and an autonomous AI agent into one trustworthy system. The differentiator is threefold:

1. **Verifiable privacy:** Local scrubbing of PII before cloud send (auditable code, not promises)
2. **Autonomous missions:** AI plans and executes work, not just reads and responds
3. **Cross-platform continuity:** One runtime, every device—start on desktop, finish on phone

This roadmap explains why we ship V2 first, then V3, then V4—and why each step is necessary.

---

## The Progression: V2 → V3 → V4 → V5

### Why This Order?

**Naive approach:** "Ship everything at once. Be an Uber of personal AI."

**Reality check:**
- Notion took 6 years to get workspace + AI integration right
- Apple took 15 years to integrate five native apps
- Primnox has three hard problems: sandbox (V2), always-on experience (V3), sync (V4)
- Each hard problem needs to ship, prove itself, then feed the next

**The order is locked:**
- **V2 builds the engine** — sandbox, scrubber, verification, Graphify. Nothing in V3 works without it.
- **V3 makes Primnox feel like JARVIS** — missions, voice, desktop awareness. Proves the engine can sustain an always-on experience.
- **V4 scales to every device** — PrimSync, cross-device missions, mobile. Locks in the ecosystem.
- **V5 predicts the future** — digital twin, ambient intelligence. Only possible if V4's foundation is solid.

If V2 is shaky, V3 dies. If V3 doesn't feel alive, V4 has no moat. This is sequential by necessity, not roadmap planning.

---

## V2 — The Engine (Now Shipping)

**Release theme:** "Privacy you can verify. Not a promise—code."

**What it is:**
- Conversation runtime with tool execution (sandbox + local)
- PII scrubber that runs before cloud send
- Graphify: knowledge graph with verification layer
- Baseline memory and decision history

**What it's NOT:**
- A full personal OS (calendar, tasks, notes are separate)
- Multi-agent (one model at a time)
- Cross-device (single machine)
- Voice (text only)

### V2 Goals

**Shipping confidence:**
- Sandbox execution is bulletproof (no escapes, no exploits)
- Scrubber catches realistic PII (names, emails, phone, SSN, credit cards)
- Graphify builds accurate knowledge graphs (not hallucinated)
- Privacy audit passes (verifiable > promissory)

**Market positioning:**
- Early adopters: developers, privacy-conscious professionals, makers
- Entry point: chat interface (familiar) with visible execution timeline (novel)
- Message: "Your AI runs code safely. Your data never leaves your machine (unless you approve)."

### V2 Verification (535 tests)

| Category | Tests | Focus |
|----------|-------|-------|
| Sandbox | 145 | Escape attempts, resource limits, file access |
| Scrubber | 120 | False negatives (missed PII), false positives (over-scrubbing) |
| Graphify | 95 | Accuracy, cycles, provenance tracking |
| Conversation | 85 | Tool chaining, error recovery, state persistence |
| Privacy | 55 | Data flow auditing, cloud payloads, encryption |
| Performance | 35 | Latency, throughput, memory use |

### V2 Timeline

- **2025–2026:** Sandbox, scrubber, Graphify (shipped)
- **2026–2027:** Verification, edge cases, hardening
- **Milestone:** Public beta (trusted users, regulated professionals)

---

## V3 — AEGIS: Always-On JARVIS (Next)

**Release theme:** "Stop opening Primnox to ask. Start assigning missions."

**What it is:**
- Mission runtime: multiline executions that survive crashes, sleep, cancellation
- Multi-agent orchestra: Architect, Builder, Designer, Researcher, Tester (visible to user)
- Desktop awareness: Context from active window, terminal, clipboard
- Voice interaction: Wake word, STT, natural conversation, TTS
- Adaptive personality: Behavioral adaptation based on context (not fake emotions)
- Memory Palace: Visual knowledge graph with provenance
- Unified workspace: Calendar, tasks, notes, all in one (single-user, local)

**Why it matters:**
- V2 proved the sandbox works. V3 proves it can sustain a *living* experience.
- Users stop perceiving Primnox as a tool (chat window) and start seeing it as an agent.
- Daily-use stickiness depends on personality + perceived autonomy + visible progress.

### V3 Goals

**Feature completeness:**
- Mission runtime handles >80% of real user workflows
- Voice feels natural (interruptions work, context carries)
- Desktop awareness reduces copy-paste friction to near-zero
- Personality engine learns preferences without announcements
- Calendar + tasks + notes unified feel solid, not bolted-on

**Market positioning:**
- Target: Developers, makers, product managers, knowledge workers
- Entry motion: "Assign a mission, watch it happen" demo
- Stickiness: Personality makes users come back daily

**Differentiation:**
- Notion has more features. Primnox has *feel*.
- TickTick has better list UX. Primnox has *autonomy*.
- Google is everywhere. Primnox is *trustworthy*.

### V3 Verification (850+ additional tests)

| Feature | Tests | Focus |
|---------|-------|-------|
| Voice | 120 | STT accuracy, TTS quality, interruption handling, wake word reliability |
| Desktop | 180 | Window detection, text parsing, context switching, privacy boundaries |
| Missions | 250 | Planning, execution, crash recovery, rollback, history |
| Agents | 160 | Agent routing, collaboration, visible state, handoff |
| Screen | 140 | Screenshot parsing, button detection, error understanding, workflow inference |
| Workspace | 120 | Calendar sync, task state, note persistence, unified search |
| Personality | 80 | Tone consistency, preference learning, ethical boundaries |

**Total V3 test suite:** 535 + 850 = 1,385 tests

### V3 Timeline

- **2026–2027:** Mission runtime, multi-agent
- **2027:** Desktop awareness, voice
- **2027–2028:** Adaptive personality, unified workspace
- **Milestone:** Launch to beta (invite-only, high-engagement users)

---

## V4 — NEXUS: Cross-Platform Ecosystem (Planning)

**Release theme:** "One brain. Every device."

**What it is:**
- PrimSync: Dedicated sync engine (LAN, Cloud encrypted, Self-hosted, Offline)
- PrimMesh: Device discovery and peer-to-peer streaming
- Cross-device missions: Start on desktop, resume on phone, finish on laptop (state carries)
- Universal workspace: Same calendar, tasks, notes on Windows, macOS, Linux, Android, Web
- Companion phone: Control centre for permissions, mission monitoring, voice control
- Shared knowledge graph: Graph updates everywhere
- Offline-first everywhere: Every platform works without internet
- Cross-platform UI system: One design language, multiple platforms

**Why it matters:**
- V3 proved Primnox can be a daily-use agent on one machine.
- V4 makes it *indispensable* by following the user everywhere.
- The runtime doesn't change (V2's architecture scales). The shells do.
- Users with multiple devices become locked into the ecosystem (switching costs high).

### V4 Goals

**Platform parity:**
- Windows, macOS, Linux, Web, Android all feel identical
- Sync is reliable (no data loss, conflict resolution is transparent)
- Offline works seamlessly (no "sync failed" errors)

**Market expansion:**
- Early adopters (V3) → mainstream professionals (V4)
- Regulatory compliance: HIPAA, GDPR, SOC 2 possible with V4 infrastructure
- Geographic expansion: Self-hosted sync option for regulated markets

**Lock-in:**
- Switching from Primnox means losing cross-device continuity
- User data in Primnox (missions, graph, preferences) is valuable and portable, but *using it elsewhere* is hard

### V4 Verification (1,090+ additional tests)

| Feature | Tests | Focus |
|---------|-------|-------|
| Sync | 300 | Real-time updates, offline handling, conflict resolution, encryption |
| Conflict Resolution | 180 | Merge strategies, user control, data integrity, crash recovery |
| LAN Mesh | 140 | Device discovery, local streaming, handoff performance |
| Offline | 160 | Queuing, retry logic, eventual consistency, data integrity |
| Cross-platform UI | 220 | Platform-specific needs (Android back button, iOS swipe-back), consistency |
| Migration | 90 | V3 → V4 data migration, rollback, user experience |

**Total V4 test suite:** 1,385 + 1,090 = 2,475 tests

### V4 Timeline

- **2027–2028:** PrimSync, PrimMesh (infrastructure)
- **2028:** Cross-device missions, universal workspace
- **2028–2029:** Mobile clients (Android first, iOS later)
- **Milestone:** General availability (open beta, paid plans)

---

## V5 — Digital Twin: Predictive Intelligence (Visionary)

**Release theme:** "Primnox knows what you're about to do."

**What it is:**
- Predictive workflows: "You usually meet with X on Thursdays at 2pm. I've blocked time and drafted the agenda."
- Ambient intelligence: Background agents work without user prompting
- Churn prediction: Notices when you're overloaded and offers help
- Decision history analysis: Learns your decision-making patterns
- Proactive alerts: Flags decisions that conflict with stated values

**Why it matters:**
- V4's infrastructure (universal workspace, real-time sync, cross-device state) makes this possible
- This is the "digital twin" promised in the original vision
- No competitor has this (because no competitor has V4's foundation)

**Target timeline:** 2029+

---

## Why Not Ship V3 + V4 Features Together?

**The trap:** "We need voice to launch" / "Users want mobile from day one"

**Reality:**
- If sandbox is broken, voice is useless
- If missions don't work reliably, cross-device is a nightmare
- If personality feels fake, daily-use stickiness is zero

**Examples of products that shipped too-early-too-many-features:**
- Google+: Social network, photos, video, games, products. Fractured and failed.
- Microsoft Zune: Cloud, streaming, device, marketplace. Each part competed with others.

**Why sequential shipping works:**
1. **V2:** Prove the engine works (early adopters see it working)
2. **V3:** Prove the experience is alive (beta users feel it's different)
3. **V4:** Prove it scales (mainstream adoption, regulatory sales)
4. **V5:** Prove it predicts (magic moment, they can't imagine leaving)

Each version gives us a **moat** before the next:
- V2 moat: Verifiable privacy (hard to copy)
- V3 moat: Personality and autonomous missions (hard to copy)
- V4 moat: Cross-device continuity (hard to leave)
- V5 moat: Predictive intelligence (they don't know what they need)

---

## Feature Ownership by Version

### V2 Features (Shipped)

- [x] Sandbox execution (Python, local tools)
- [x] PII scrubbing (local, before cloud)
- [x] Graphify (knowledge graph, communities, verification)
- [x] Conversation memory (thread history)
- [x] Multiple AI models (via OmniRoute)
- [x] Tool capability boundaries
- [x] User preferences persistence
- [x] Data flow audit trail
- [x] Portable conversation export

### V3 Features (In Development)

- [ ] Mission runtime (live execution timeline)
- [ ] Multi-agent orchestra (visible agents)
- [ ] Desktop awareness (window, terminal, clipboard)
- [ ] Voice interaction (STT, TTS, wake word)
- [ ] Adaptive personality (context-aware responses)
- [ ] Memory Palace (visual knowledge graph)
- [ ] Unified calendar (calendar view, sync)
- [ ] Unified tasks (task list, recurring)
- [ ] Unified notes (note editor, linking)
- [ ] Screen intelligence (button detection, error parsing)

### V4 Features (Planned)

- [ ] PrimSync (LAN, Cloud, Self-hosted, Offline)
- [ ] PrimMesh (device discovery, streaming)
- [ ] Cross-device missions (state carries)
- [ ] Universal workspace (every device)
- [ ] Companion phone (V3 companion mode improved)
- [ ] Full mobile client (Android, iOS)
- [ ] Web PWA client
- [ ] Shared knowledge graph (synced graph)
- [ ] Seamless handoff (exact state resume)
- [ ] Offline-first everywhere

### V5 Features (Visionary)

- [ ] Predictive workflows (anticipatory actions)
- [ ] Ambient intelligence (background agents)
- [ ] Churn prediction (user wellbeing detection)
- [ ] Decision pattern learning
- [ ] Proactive alerts (value conflicts)
- [ ] Time series forecasting (workload trends)
- [ ] Recommendation engine (next best action)

---

## Market Timeline

### 2026 (V2 Beta)

- **Q3:** Public beta (limited, trusted users)
- **Q4:** Privacy audit complete, early enterprise trials

**Target users:** Privacy-conscious developers, regulated professionals, makers

### 2027 (V3 Alpha → Beta)

- **Q1–Q2:** Mission runtime, voice (alpha)
- **Q3:** Desktop awareness, personality (beta)
- **Q4:** General availability (V3.0)

**Target users:** Indie developers, product managers, knowledge workers

### 2028 (V4 Alpha)

- **Q1–Q2:** PrimSync, PrimMesh (alpha)
- **Q3:** Cross-device missions (beta)
- **Q4:** Mobile clients (limited, Android first)

**Target users:** Cross-platform professionals, ecosystem enthusiasts

### 2029 (V4 GA → V5 Visionary)

- **Q1–Q2:** General availability (V4.0), full mobile support
- **Q3+:** V5 visionary work (predictive, ambient)

**Target users:** Mainstream professionals, regulated enterprises

---

## Success Metrics by Version

### V2 Success
- [ ] Zero sandbox escapes (verified by third-party audit)
- [ ] Scrubber <1% false negative rate (missed PII)
- [ ] Graphify accuracy >95% (correct relations, low hallucination)
- [ ] 1,000+ beta users retained after 30 days
- [ ] Privacy audit passes (GDPR, no breach)

### V3 Success
- [ ] Missions save users >2 hours/week on average
- [ ] >60% of user sessions include voice interaction
- [ ] Personality rated "trustworthy" by 75%+ of users
- [ ] 10,000+ beta users, 50% 30-day retention
- [ ] Desktop awareness used in >40% of sessions

### V4 Success
- [ ] Sync latency <2 seconds (cross-device)
- [ ] Zero data loss in production
- [ ] Cross-device handoff used in 80%+ of multi-device users
- [ ] 100,000+ paying users
- [ ] Regulated enterprises (HIPAA, GDPR) see Primnox as compliant

### V5 Success
- [ ] Predictive workflows save >4 hours/week
- [ ] Ambient agents reduce user keystrokes by 50%
- [ ] Churn prediction prevents 30%+ of at-risk users from leaving
- [ ] Market cap demonstrates category creation ($1B+)

---

## Competitive Dynamics by Version

### V2 Era (2026–2027)
- **Competition:** Notion (bolted-on AI), Obsidian (local but no AI)
- **Primnox advantage:** Verifiable privacy + sandbox execution
- **Risk:** Notion adds better AI (they will), Obsidian adds LLM (they will)

### V3 Era (2027–2028)
- **Competition:** Google Assistant, Siri (voice), Amie (autonomy)
- **Primnox advantage:** Unified workspace + missions + personality
- **Risk:** Apple adds mission-like features to Reminders + Calendar, Google unifies Workspace + Duet

### V4 Era (2028–2029)
- **Competition:** Apple ecosystem (lock-in), Google ecosystem (ubiquity)
- **Primnox advantage:** Cross-platform (they're locked to their OS), verifiable privacy
- **Risk:** Apple launches cross-device missions, Google finally unifies their apps

### V5 Era (2029+)
- **Competition:** Everyone scrambles to add predictive features
- **Primnox advantage:** V4's foundation (data quality, cross-device consistency) makes predictions accurate
- **Risk:** Whoever ships first owns the space (even with 80% accuracy)

---

## Critical Dependencies

### V2 Dependencies
- Sandbox research (exploit surface area)
- Scrubber accuracy (PII taxonomy)
- Graphify algorithm (community detection, verification)

### V3 Dependencies
- V2 must be stable (foundation)
- Voice quality (Whisper, Kokoro licensing)
- Desktop access APIs (Windows, macOS, Linux)

### V4 Dependencies
- V3 must feel alive (users need to be loyal)
- Sync infrastructure (conflict resolution is hard)
- Mobile OS support (Android first, iOS later)

### V5 Dependencies
- V4 must have 1M+ users (data for prediction)
- User data quality (GIGO: garbage in, garbage out)
- Regulatory compliance (personal data usage for ML is fraught)

---

## Platform Roadmap

### Desktop (Windows, macOS, Linux)
- V2: Windows (beta), macOS/Linux (planned)
- V3: Full desktop support (all three platforms)
- V4: Native clients with platform-specific features

### Web
- V2: None planned (data security concerns)
- V3: Limited PWA (view-only, no execution)
- V4: Full PWA + progressive enhancement

### Mobile
- V2: None
- V3: Companion mode (approval, monitoring)
- V4: Full client (Android), Later (iOS)

### Ecosystem
- V2: Single-user, local-only
- V3: Single-user, unified workspace
- V4: Multi-device, shared workspace (multi-user later)

---

## Risk & Mitigation

### Execution Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Sandbox escape found in production | Critical | Third-party audit, responsible disclosure, rapid patch |
| Scrubber false negatives (privacy breach) | Critical | Continuous learning on breach data, automated testing, audit trail |
| Personality feels fake or preachy | High | Extensive user testing, comedian + ethicist input, iteration |
| Voice quality poor on launch | Medium | Fallback to text, partnerships for TTS/STT quality |
| Sync data loss on V4 launch | Critical | Extensive conflict resolution testing, offline-first gradual rollout |

### Market Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Google launches unified "Workspace AI" | High | Ship V4 faster, emphasize privacy + personality |
| Apple launches cross-device missions | High | Emphasize non-Apple support, emphasize privacy |
| Notion buys a bot company | Medium | Ship V3 personality first, own autonomous missions |
| Market doesn't care about privacy verification | High | Pivot to regulated professionals, prove ROI via missions |

### Operational Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Talent churn (too ambitious roadmap) | Medium | Ship versioned roadmap, celebrate milestones, revenue-share |
| Funding pressure to compress timeline | High | Raise enough for sequential shipping, resist pressure to merge V3+V4 |
| Open-source competitor forks Primnox | Low | Open-source core (sandbox, scrubber), closed-source moat (personality, sync) |

---

## Conclusion

Primnox's roadmap is **locked by architecture, not arbitrary**.

V2 ships the engine that makes V3 possible. V3 proves it works at scale. V4 scales it to every device. V5 makes it predictive.

Each step takes **2 years** because:
1. The features are genuinely hard (sandbox, voice, sync)
2. Verification is extensive (535 → 850+ → 1,090+ tests)
3. User trust must compound (V2 → V3 → V4)

**The wedge:** Start with early adopters (developers, privacy-conscious professionals) in V2–V3. Use their feedback and data to expand to mainstream (V4). Lock in via ecosystem (V4) and predictive magic (V5).

**The moat:** No competitor can ship all five versions in sequence without running out of money or focus. V5 won't be invented for 3–5 years. By then, Primnox users won't be able to imagine leaving.
