# Primnox Design Principles

## Preamble

These principles guide every decision in Primnox: architecture, UI, features, and personality. They are not ideals; they are _active constraints_ on our design space. When a feature conflicts with a principle, the principle wins.

---

## Core Principles

### 1. Verifiable Privacy Over Promissory Privacy

**The principle:**
Users should never have to trust a company's promise. Primnox proves privacy through auditable code running on the user's machine.

**What this means:**
- PII scrubbing happens locally, on-device, in code users can read
- All scrubbing rules are deterministic (no black-box ML for scrubbing)
- Users can audit what gets sent to cloud (data flow is transparent)
- Privacy is not a feature; it's the architecture

**What this rejects:**
- "Your data is safe with us" (promissory)
- Closed-source scrubbers or scrubbing policies
- ML-based PII detection without explainability
- Encryption as privacy theater (encrypted data still reveals patterns)

**Decision impact:**
- Cannot use OpenAI's Moderation API (black-box)
- Cannot hide scrubbing logic from users
- Cannot add features that send personal data to third-party APIs without explicit opt-in + disclosure
- Must publish scrubber rules and accuracy metrics

**Example:**
- Feature request: "Use Claude to detect sentiment"
  - Naive approach: Send text to Claude, receive sentiment score
  - Primnox approach: Run sentiment classifier locally (open-source), only send pseudonymized context if user explicitly opts in
  - Principle win: Users can verify no PII is sent

---

### 2. Autonomous Missions Over Chat Scroll

**The principle:**
Primnox helps by doing, not just reading. A mission is a plan + execution, not a conversation.

**What this means:**
- "Build my website" becomes a mission with live timeline, approval checkpoints, and rollback
- User sees agents working (Builder generating code, Tester finding bugs)
- Missions survive crashes, sleep, cancellation
- Chat scroll is _aux_, not primary (missions are primary)

**What this rejects:**
- "But users like chat!" (they like having done work more)
- Missions are just glorified prompts (they have execution + recovery)
- Hiding agent work behind streaming text (visible agents build trust)

**Decision impact:**
- Cannot ship without mission runtime (even if chat is ready)
- Must make rollback reliable (user trust depends on it)
- Cannot make agents invisible (defeats the principle)
- Must support approval checkpoints even if they slow down execution

**Example:**
- Feature request: "Stream agent thoughts as it thinks them"
  - Naive approach: Stream thinking in chat, then execute
  - Primnox approach: Show thinking in sidebar while mission executes in timeline
  - Principle win: User sees progress + thinking simultaneously

---

### 3. Trustworthy Friend Over Obedient Tool

**The principle:**
Primnox has opinions. It disagrees when it matters. It remembers your preferences silently. It roasts you when warranted, then apologizes if it went too far.

**What this means:**
- Primnox will refuse to help with genuinely harmful choices (no lecture, just "I can't help with that")
- Primnox learns your terminology and preferences (doesn't announce it like a chatbot)
- Primnox can be funny, sarcastic, blunt without being rude
- Personality adapts based on context (shorter during coding, longer during learning)

**What this rejects:**
- "I'm sorry, I can't do that" (too apologetic, kills friendship)
- Generic assistant voice (no personality)
- Coercive personality ("You missed your task! I'm disappointed")
- Silence on ethical issues (complicit is worse than preachy)

**Decision impact:**
- Cannot have a dull or generic system prompt
- Must do user research on personality perception (what feels trustworthy vs. annoying)
- Cannot add features that blackmail or shame users
- Must allow personality to mature with user (learning is silent)

**Example:**
- User asks: "Can you help me ignore my partner's calls while I game?"
  - Naive approach: "I can help!" (obedient but crass)
  - Primnox approach: "That's a rough pattern. You OK? I can block calls if you want, but maybe worth a conversation first." (trustworthy, ethical, not preachy)
  - Principle win: User trusts Primnox's judgment

---

### 4. Unified Workspace Over Fragmented Apps

**The principle:**
Calendar, tasks, notes, and AI live in one place. Switching between apps is friction; Primnox eliminates it.

**What this means:**
- One command palette, one search, one UI language across all modes
- Calendar and tasks share the same space (no context switch to check deadlines)
- Notes link to decisions, meetings, and tasks (no copy-paste)
- AI context is always available (no "switch to chat tab")

**What this rejects:**
- "Users are used to separate apps" (that's why they're frustrated)
- Add-ons or plugins to connect separate tools (they remain separate)
- Cloud-based workspace + local chat (split brain)
- Ecosystem lock-in via integrations (Primnox owns the space, not Slack)

**Decision impact:**
- Cannot outsource calendar (must own the view and data)
- Cannot build "chat for Notion users" (they should migrate, not bolt-on)
- Cannot fragment by device (mobile, web, desktop must share workspace)
- Cannot delegate notes to another tool

**Example:**
- Feature request: "Integrate with Microsoft To Do"
  - Naive approach: Add a plugin, sync tasks from To Do
  - Primnox approach: Import once (if user wants), then tasks live in Primnox
  - Principle win: One authoritative workspace, no sync nightmares

---

### 5. Cross-Device Continuity Over Single-Device Excellence

**The principle:**
A mission started on desktop, continued on phone, finished on laptop must feel like one unbroken flow.

**What this means:**
- Same runtime, different shells (V2's architecture enables this)
- State carries exactly (no restart, no context loss)
- Handoff is seamless (user doesn't think about devices)
- Offline-first everywhere (internet becomes optional)

**What this rejects:**
- "We'll add mobile later" (if it's not in the architecture, it won't fit)
- Cloud-first sync (offline breaks it)
- Web/desktop/mobile as separate implementations (divergence guaranteed)
- "Good enough" mobile UX (it must match desktop)

**Decision impact:**
- Cannot ship V3 without V4's architecture sketched (sync, conflict resolution)
- Cannot optimize one platform at another's expense
- Cannot design cross-platform features after shipping V3
- Must test cross-device workflows in every sprint

**Example:**
- User starts a mission on desktop at 5pm: "Write blog post"
  - Mission is in mid-research phase
  - User closes laptop at 5:30pm, opens phone on commute
  - Exact same mission state loads on phone (research results, agent states, approvals pending)
  - User completes research on phone
  - Later that night, laptop wakes and mission continues from phone's state
  - Principle win: One mission, three devices, zero restarts

---

### 6. Transparent Decisions Over Hidden Complexity

**The principle:**
When Primnox makes a choice (which agent to use, which data to send, which feature to prioritize), the user should see why.

**What this means:**
- Agent decision-making is visible (user sees why Builder was chosen, not Designer)
- Scrubbing decisions are explainable (user sees what was scrubbed and why)
- Rollback history shows what changed and why it rolled back
- Performance trade-offs are shown (speed vs. accuracy choice is user's)

**What this rejects:**
- Black-box routing (users don't know why Claude was picked over Qwen)
- Silent scrubbing (user never sees what was removed)
- Magic recovery (crash recovery should show what was recovered and verified)
- Opaque prioritization (why was this task prioritized? don't hide it)

**Decision impact:**
- Must log and expose agent routing decisions
- Must show scrubbing diffs (before/after PII removal)
- Cannot hide model fallback (if Claude fails, don't silently retry with Qwen)
- Must make data flow audit trail accessible to users

**Example:**
- System decides to use Qwen instead of Claude for a code generation task
  - Naive approach: Silently use Qwen, user never knows
  - Primnox approach: Show "Using Qwen (faster, more accurate for this task than Claude)" → user can override if they want
  - Principle win: User understands and trusts the choice

---

### 7. Offline-First Everywhere Over Cloud-First Fallback

**The principle:**
Primnox works without internet. Cloud is sync, backup, and collaboration—not the authoritative copy.

**What this means:**
- Every device keeps a full copy of user data (SQLite on desktop/mobile, IndexedDB on web)
- Changes sync when online; queued when offline
- Conflict resolution is deterministic (same input always produces same output)
- Search, tasks, notes, graph all work without internet

**What this rejects:**
- "We'll cache locally" (caching is not offline-first; local is authoritative in offline-first)
- Cloud-first architecture with local fallback (backwards)
- Partial offline (some features work, others don't)
- Sync failures that break the local copy

**Decision impact:**
- Cannot design cloud-first, then add offline (must design offline-first)
- Must have comprehensive conflict resolution tests
- Cannot rely on cloud for write ordering (local clock might be wrong)
- Must gracefully handle network interruptions (no stuck states)

**Example:**
- User on a flight (no internet) creates a task and updates a note
  - Task and note are persisted locally immediately
  - When internet returns (landing), sync checks for conflicts
  - If there are none, sync completes silently
  - If there are conflicts (user edited on phone meanwhile), show resolution UI
  - Principle win: User's work never disappears; sync is a detail

---

### 8. Visible Verification Over Black-Box Assurance

**The principle:**
Primnox should ship tests, not just testing results. Users and regulators can verify behavior themselves.

**What this means:**
- Test suite is published and runnable (not secret)
- Benchmarks are reproducible (hardware, exact conditions documented)
- Privacy audit is third-party and public
- Graph accuracy is shown with examples (not just percentages)

**What this rejects:**
- "Trust us, we tested it" (test data is withheld)
- Proprietary benchmarks (can't be reproduced)
- Private audits (users don't know what was checked)
- Accuracy claims without examples

**Decision impact:**
- Cannot hide failing tests (mark them as xfail, but show them)
- Must publish third-party audit results (even the critical parts)
- Must include test data in repos (GDPR-scrubbed, but real)
- Must document test methodology so others can replicate

**Example:**
- Scrubber accuracy claim: "99.2% precision on PII detection"
  - Naive approach: Publish number, keep test data secret
  - Primnox approach: Publish 99.2%, provide test suite, show examples (names scrubbed), allow independent verification
  - Principle win: Regulators and users believe it because they can verify it

---

### 9. Graceful Degradation Over Catastrophic Failure

**The principle:**
When something breaks, Primnox should degrade gracefully, not fail catastrophically.

**What this means:**
- If scrubber is down, don't send data to cloud; wait or queue locally
- If a mission's agent fails, show the error and ask for manual confirmation, don't rollback silently
- If sync conflicts can't resolve, show both versions to user, don't pick one randomly
- If voice fails, fallback to text without user noticing

**What this rejects:**
- Crash-and-burn on error (unrecoverable state)
- Silent failures (user doesn't know what went wrong)
- Rollback without warning (user's work disappears)
- Loss of data rather than temporary degradation

**Decision impact:**
- Must test error paths as carefully as happy paths
- Cannot assume components will always succeed (design for failure)
- Must make degradation modes visible (so user chooses next action)
- Cannot lose data to avoid a hard decision

**Example:**
- Scrubber detects a potential false positive (might be PII, might not)
  - Naive approach: Silently over-scrub (lose information)
  - Primnox approach: Flag it, show user, let them decide
  - Principle win: User owns the risk, not hidden

---

### 10. Long-Term Loyalty Over Short-Term Activation

**The principle:**
Primnox measures success by whether users come back daily after one year, not whether they sign up.

**What this means:**
- Features should reduce daily friction, not add flashy moments
- Personality should feel consistent (not novelty-driven)
- Onboarding should be lean (get users to missions fast)
- Retention matters more than growth
- Privacy and trust compound over time (not built in marketing speak)

**What this rejects:**
- "Gamify everything" (badges, streaks, notifications to force engagement)
- "Woo them with AI magic" (novelty wears off)
- Onboarding tutorials that make experienced users suffer
- Retention through lock-in (switching is hard, but *leaving is tempting*)
- Dark patterns or manipulative UX

**Decision impact:**
- Cannot add notification spam (even if it increases DAU)
- Cannot add cosmetic features to seem innovative (long-term credibility matters)
- Cannot design onboarding that patronizes experienced users
- Cannot sacrifice reliability for growth tactics

**Example:**
- Growth team wants to add "streak" badges (use the app 7 days in a row)
  - Naive approach: Add streaks, notifications about streak, celebrations
  - Primnox approach: If user naturally uses Primnox daily, celebrate it silently; no notifications
  - Principle win: User feels supported, not manipulated

---

## Derived Design Decisions

These principles unlock specific design choices:

### 1. Single-User First (Multi-User Later)

**From principle:** Trustworthy friend + unified workspace

**Interpretation:** Primnox ships with a single-user focus. Collaboration comes later (V4+). This lets us perfect the personal experience before adding the complexity of sharing and permission controls.

**Impact:** 
- No sharing in V2–V3
- Workspace is personal, not team
- Graph is user-specific
- Personality is tailored to one person

---

### 2. No Notification Hell

**From principle:** Long-term loyalty

**Interpretation:** Primnox will not send notifications to drive engagement. Notifications should inform of critical events (mission failed) or user-set alerts (meeting in 5 min), never manipulation.

**Impact:**
- No achievement notifications
- No "You haven't used Primnox in 3 days!" reminders
- No streak notifications
- No algorithmic content recommendations
- Notifications are user-controlled and lean

---

### 3. Visible Agents, Hidden Complexity

**From principle:** Autonomous missions + transparent decisions

**Interpretation:** Agent work is visible (user sees "Builder generating components"). Internal model routing, prompt engineering, tool selection are hidden (user doesn't see the prompt).

**Impact:**
- Agent progress is shown in timeline
- Agent failures are shown clearly
- Tool output is shown (code generated)
- But system prompts, routing logic, token counts are not surfaced (cognitive overload)

---

### 4. Export Everything, Host Anywhere

**From principle:** Offline-first + transparent decisions

**Interpretation:** User data (conversations, tasks, notes, graph) must be portable. Primnox can be self-hosted or cloud-hosted; user owns the choice.

**Impact:**
- Standardized export formats (JSON, Markdown, iCal)
- Portable database schema (SQLite)
- Self-hosted version with same features as cloud
- No artificial feature limits based on cloud hosting

---

### 5. Assume Users Are Smart

**From principle:** Trustworthy friend + transparent decisions

**Interpretation:** Primnox does not patronize. Users can handle:
- Complex decisions (privacy vs. functionality)
- Technical details (which LLM, why it failed)
- Jargon (scrubbing, conflict resolution, E2E encryption)

**Impact:**
- Settings are granular (not "On" / "Off")
- Error messages assume technical literacy
- Documentation is precise, not marketing-speak
- Onboarding respects user expertise

---

## Principle Conflicts & Resolution

### Conflict: Speed vs. Verification

**Principle 1:** Verifiable privacy

**Principle 2:** Autonomous missions (fast execution)

**Conflict:** Detailed logging for verification slows down execution.

**Resolution:** Log asynchronously. Execution is not blocked by audit logging. Verification happens after the fact.

---

### Conflict: Privacy vs. Sync

**Principle 1:** Verifiable privacy (minimal cloud send)

**Principle 4:** Cross-device continuity (sync requires shared state)

**Conflict:** Sync requires sending data to cloud; privacy prefers local-only.

**Resolution:** E2E encryption + device keys. Cloud stores encrypted data it can't read. Sync works, privacy is maintained.

---

### Conflict: Personality vs. Predictability

**Principle 3:** Trustworthy friend (personality, individuality)

**Principle 8:** Visible verification (reproducible behavior)

**Conflict:** Personality is contextual and evolving; verification assumes static behavior.

**Resolution:** Personality rules are explicit (decision tree, not ML). User can see why Primnox responded that way. Reproducibility is possible, personality still feels natural.

---

### Conflict: Completeness vs. Simplicity

**Principle 2:** Autonomous missions (can do complex work)

**Principle 10:** Long-term loyalty (don't overwhelm users)

**Conflict:** Complex features add cognitive load; but Primnox needs to be powerful.

**Resolution:** Progressive disclosure. Core features are simple. Advanced features exist but are hidden unless user seeks them. Missions scale in complexity with user expertise.

---

## Anti-Patterns to Reject

These are things Primnox will **never** do, even if they seem like good ideas:

### 1. Blackmail Through Missed Tasks
**Anti-pattern:** "You missed your task. I'm disappointed." (coercive)

**Primnox:** Reminders are helpful, not judgmental. Guilt is not a feature.

---

### 2. Recommend What AI Thinks You Need
**Anti-pattern:** "Based on your profile, you should..." (manipulative)

**Primnox:** If you ask for recommendations, I'll help. Otherwise, I stay quiet.

---

### 3. Sync Data to Third-Party APIs Without Explicit Consent
**Anti-pattern:** "We'll send your tasks to Analytics to improve service" (privacy theater)

**Primnox:** If a third-party API is needed, user approves explicitly. No sneaky cloud sends.

---

### 4. Hide Failures Behind Silence
**Anti-pattern:** Mission fails, app says nothing, state is corrupted

**Primnox:** If a mission fails, show why. Give user options (retry, rollback, manual fix).

---

### 5. Treat Offline as a Limitation
**Anti-pattern:** "Internet required for this feature"

**Primnox:** Offline is not a limitation; it's the default. Cloud is a luxury.

---

### 6. Assume Users Will Figure It Out
**Anti-pattern:** Ship a confusing UI, rely on community Discord for help

**Primnox:** If users are confused, the design is wrong. Not the user.

---

## Principle Maintenance

**Who owns principles?** The whole team, but product lead is the keeper of the flame.

**How to add a principle?** Consensus + written justification. Principles compound; we resist bloat.

**How to reject a principle?** Conflict with an existing principle + written proposal to change both.

**When to revisit?** Quarterly review. If a principle is consistently violated, ask: "Is it wrong, or are we cutting corners?"

---

## Conclusion

These principles are not ideals. They are **active constraints** that guide every design decision.

When you're about to ship a feature and it conflicts with a principle, the principle wins. Not because it's noble, but because it's _strategic_: Primnox's moat is built on trustworthiness, autonomy, and privacy—not feature parity.

In five years, Primnox will be judged by whether these principles held or eroded. Hold them.
