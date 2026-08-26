# Unit 12: Familiarity & Design System

## What Familiarity Actually Requires

**Familiarity in design systems** is the degree to which users can predict interaction patterns and visual hierarchy based on mental models from:
1. Previous experience with similar applications
2. Cultural design conventions
3. Platform affordances (iOS, Material Design, web standards)
4. Cognitive shortcuts that reduce learning burden

Familiarity is NOT "using the same design as everything else"—it's about **cognitive efficiency**: can the user look at an element and immediately know what it does and how to interact with it?

## Tension: Archetype vs. Familiarity

Primnox's Tactical Telemetry archetype is *deliberately* unfamiliar. The design rejects modern conventions (radius, soft shadows, translucent glass) in favor of a terminal-like instrument aesthetic. This is not an oversight; it's intentional.

The question is not "should Primnox look like every other app?" but "does this specific archetype require changes to improve familiarity *within its own world*?"

### Key Principle
> Change only when evidence shows the current choice *violates* the archetype's own logic or creates real user friction that outweighs the archetype's benefits.

---

## Three Design Choices Under Scrutiny

### 1. Border Radius: ZERO (Hard Angles Everywhere)

#### Current State
- `--radius-control: 0px`
- `--radius-panel: 0px`
- Tailwind's entire `borderRadius` scale overridden to `0`
- **Verified:** 0 elements with non-zero computed border-radius

#### Familiarity Question
Does zero radius affect user recognition of interactive elements?

#### Evidence

**Against (Reduces Modern Familiarity):**
- Modern web & mobile design norms (iOS, Material Design, web): radius = 4–12px on controls
- Users from modern software expect rounded corners on buttons, inputs, cards
- Sharp corners read as "inactive," "retro," or "brutalist"—technically correct for Primnox, but not familiar

**For (Maintains Archetype):**
- Terminal UI never has rounded corners—it's the honest form language
- Primnox is positioned as a "runtime instrument," not a traditional app
- Removes visual clutter and "floating card" affordance that contradicts brutalism
- Consistent with the one-accent, no-shadow, no-glass rules that define the world
- Sharp corners + hairline borders reinforce "compartment" (structure) over "elevation"

#### User Friction Analysis
- **Accessibility:** Zero impact. Border radius has no accessibility value
- **Learnability:** Minimal friction. Users quickly recognize that sharp corners = Primnox identity
- **Muscle Memory:** No conflict with motor tasks (clicking, typing)—radius doesn't affect hit targets
- **Tone:** Radius affects perception ("polished" vs. "raw"), not function

#### Verdict: **KEEP**

**Reason:** Border radius is decorative, not functional. Removing it is consistent with the archetype's structural honesty. Yes, it's unfamiliar from a modern-design perspective, but familiarity is not the north-star here—**it's a side effect of the aesthetic choice, not a requirement.** The learning burden is negligible, and the visual consistency is strong.

The question isn't "does this break user expectations?" but "does this archetype work better with or without radius?" The archetype works better without it.

---

### 2. Monospace by Default (JetBrains Mono for UI/Labels/Data)

#### Current State
- `--body: 'JetBrains Mono'` for interface, labels, controls, navigation, telemetry
- `--body-prose: 'DM Sans'` for long-form reading (documented exception)
- Labels use uppercase + tight tracking (`0.12em–0.2em`)
- WCAG AA contrast verified: 0 text failures

#### Familiarity Question
Does monospace typography reduce or increase cognitive load for UI elements?

#### Evidence

**Against (Reduces Modern Familiarity):**
- Modern UIs (iOS, Material, web): sans-serif (Roboto, San Francisco, Segoe UI) for interface
- Monospace is *associated* with terminals, code, machine output—not typical app UI
- Users do not expect monospace for labels, buttons, or navigation
- Monospace reduces readability for long labels (poor kerning, wider characters)
- Ligatures in JetBrains Mono can cause unexpected rendering in all-caps text

**For (Maintains Archetype & Improves Accuracy):**
- Monospace is data-agnostic: one character = one width. Crucial for telemetry, logging, timestamps
- "The interface is data" — Primnox reports on itself. Data should not switch faces
- Uppercase monospace reads as "instrumental" and "authoritative"
- Reduces font-switching overhead; consistent with terminal tools (htop, top, tmux)
- Creates visual hierarchy: monospace (UI) vs. sans-serif (prose) = data vs. narrative
- **Measured benefit:** Tabular figures on `time`, `[data-measure]` ensure numbers don't reflow

**User Testing Proxy:**
- No friction observed in existing onboarding. Users recognize "this is different" within seconds
- Uppercase + tracking forces slow, deliberate reading—appropriate for control labels
- Monospace + numbers creates visual scanning advantage over sans-serif

#### Accessibility Consideration
- WCAG compliance: ✓ (0 failures, contrast verified)
- Readability: Monospace 10–12px is slightly slower than sans-serif, but not prohibitive
- Dyslexia: Monospace can *help* some dyslexic readers (consistent letterforms)
- Screen readers: No impact (DOM structure is unchanged)

#### Verdict: **KEEP**

**Reason:** Monospace is not an arbitrary style choice—it's core to the archetype's data-focused identity. Primnox reports on itself; the UI is telemetry. Sans-serif UI + monospace prose would break that unity.

The cognitive load is *lower*, not higher, because:
1. No font switching during navigation (UI stays one face)
2. Uppercase monospace *forces* deliberate reading—reduces cognitive shortcuts and errors
3. Tabular numbers prevent reflow bugs

Familiarity with modern conventions (sans-serif UI) trades away accuracy and architectural honesty. The loss is not acceptable.

---

### 3. Dark-Only (No Light Theme)

#### Current State
- `:root` (default): `--bg: #0A0A0A`, `--text: #EAEAEA`, one accent
- `[data-theme="tactical-dim"]` variant: slightly brighter substrate (`#121212`)
- No light theme defined
- No toggle or preference system for light/dark

#### Familiarity Question
Does dark-only reduce user recognition and comfort?

#### Evidence

**Against (Reduces Modern Familiarity):**
- Modern app convention: light as default, dark as opt-in
- ~60% of desktop users still prefer light themes (varies by product)
- Accessibility: some users with low-vision or migraines need light UI
- Contrast inversion on light (text = dark, bg = light) would require Material-3 bridge rebuild
- First-time user expectation: "where's light mode?"

**For (Maintains Archetype & Aligns with Product):**
- Terminal UIs are dark-only (design integrity)
- CRT phosphor model (deactivated CRT) is inherently dark
- Substrate = physical room metaphor. Dark room = the honest metaphor for a runtime instrument
- `tactical-dim` variant already exists for different room brightness—that's the scope
- No evidence of light-mode requests in product backlog
- Contrast is verified for dark substrates; light substrate would require full re-verification

**User Friction Analysis:**
- **New users expecting light mode:** Medium friction (minutes to acceptance or churn)
- **Accessibility:** Real concern. Users with visual impairments or migraines benefit from light UI
- **Cross-device:** Web users expect light/dark toggle. Desktop users more tolerate fixed themes

#### Accessibility Shortfall
WCAG 2.1 AA compliance is claimed in DESIGN.md. However, this is incomplete:
- Users who need light UI for medical reasons (migraines, photophobia, low vision) are partially excluded
- No workaround available (no browser dark-mode detection override)
- WCAG 2.1 does not mandate light/dark but AA does require accessible contrast ratios across supported presentations

#### Verdict: **CHANGE**

**Reason:** Dark-only is not a violation of the archetype—the archetype supports it. However, claiming WCAG AA compliance while excluding users who medically need light UI creates a compliance gap.

**The change is narrow:**
- Keep the archetype: dark is primary, brutalist, the honest design
- Add light as an accessibility accommodation, not a primary theme
- Light variant: invert substrate/text, keep typeface, radius, accent logic constant
- Preserve tonal hierarchy via Material-3 bridge (color-mix already scales)

**Implementation scope:**
1. Build `light` variant of themes.css (substrate inversion + re-verified contrast)
2. Add `[data-theme="light"]` + optional `[data-theme="light-dim"]`
3. No toggle UI required (yet); can be set via system preference if desired
4. Test: 0 contrast failures in light variant

This is an **accessibility win**, not a style pivot that abandons the archetype.

---

## Summary: KEEP, KEEP, CHANGE

| Decision | Verdict | Reason |
|----------|---------|--------|
| **Border Radius (zero)** | **KEEP** | Decorative, not functional. Consistent with archetype. No cognitive friction. |
| **Monospace by Default** | **KEEP** | Core to data-focused identity. Reduces font-switching overhead. Forces deliberate UI reading. |
| **Dark-Only** | **CHANGE** | Accessibility gap: users who medically need light UI are excluded. Light variant required for true AA compliance. |

---

## Next: Prototype

The prototype will show:
1. **Current:** Tactical Telemetry (dark, monospace, zero radius)
2. **Proposed Light Variant:** Dark-primary, light-accommodation, monospace preserved, radius zero preserved
3. Interactive toggle between dark/light to demonstrate accessibility while preserving archetype

See `frontend/src/components/proto/familiarity-design/` for live demo (port 5312).
