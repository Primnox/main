# Progressive Disclosure — Project Summary

## Overview

This project implements a **five-level progressive disclosure system** for Primnox that reduces cognitive overload by revealing features, options, and debugging information in stages based on user expertise and context.

## The Problem

Primnox's current UI reveals everything at once:
- Novice users see options they don't need → overwhelmed
- Power users have to dig for advanced features → frustrated
- Debugging information is scattered or absent → slow troubleshooting
- Mobile UI is cramped → hard to use

## The Solution: Five Levels

| Level | Visibility | Use Case | Example |
|-------|-----------|----------|---------|
| **1-core** | Always | Essential every session | Chat input, send button, stop |
| **2-common** | Shown by default | 40–80% of users | Edit, delete, bookmark message |
| **3-advanced** | Hidden, 1 click | Power users | Token breakdown, workspace browser |
| **4-expert** | Hidden, settings panel | Developers/experts | Token accounting, event logs |
| **5-debug** | Off by default, env-gated | Developers only | API inspector, sandbox traces |

## Key Benefits

- **Novices aren't overwhelmed** — see only essential options
- **Power users aren't frustrated** — advanced features are 1 click away
- **Debugging is faster** — errors auto-expand related logs
- **Mobile works better** — less clutter, bottom-sheet pattern for Level 3+
- **Adaptive to expertise** — interface grows with user knowledge

## What's Included

### 1. **Framework** — Strategic design
- **`docs/PROGRESSIVE_DISCLOSURE_FRAMEWORK.md`**
  - Five-level model with rationale
  - Context-aware disclosure rules
  - Expertise level progression
  - Visual language (chevrons, buttons, cards)

### 2. **Component** — Production-ready React code
- **`frontend/src/components/ProgressiveDisclosure.tsx`**
  - Main `<ProgressiveDisclosure />` component
  - Group wrapper for organizing sections
  - Hooks: `useUserExpertise()`, `useErrorContext()`
  - Badge component for learning mode
  - Supports all five levels, mobile/desktop

### 3. **Styles** — Complete CSS system
- **`frontend/src/styles/progressive-disclosure.css`**
  - All five levels styled
  - Responsive (desktop card, mobile bottom-sheet)
  - Dark mode support
  - Smooth animations (150–200ms)
  - Keyboard accessible

### 4. **Examples** — Copy-paste patterns
- **`frontend/src/components/examples/ProgressiveDisclosureExamples.tsx`**
  - Chat message actions (Level 2→3)
  - Settings panel (all levels)
  - Permission approval workflow
  - Error handling with auto-expand
  - Disclosure badges for education

### 5. **Implementation Guide** — Developer docs
- **`frontend/src/components/PROGRESSIVE_DISCLOSURE_README.md`**
  - API reference
  - Usage patterns
  - Testing examples
  - Theming guide
  - Troubleshooting

### 6. **Feature Mapping** — Concrete rules
- **`docs/DISCLOSURE_RULES_BY_FEATURE.md`**
  - Every Primnox feature mapped to a level
  - Frequency estimates (measured from usage patterns)
  - Layout mockups
  - Implementation guidance per feature
  - Success metrics to track

---

## Architecture

```
ProgressiveDisclosure (root component)
├── Expertise Detection
│   ├── Read from localStorage
│   ├── Infer from conversation count
│   └── Allow manual override
│
├── Level Determination
│   ├── 1-core: always show
│   ├── 2-common: show if expertise ≥ novice
│   ├── 3-advanced: show if expertise ≥ intermediate
│   ├── 4-expert: show if expertise ≥ expert
│   └── 5-debug: show if PRIMNOX_DEBUG=1
│
├── Trigger Modes
│   ├── click (default)
│   ├── hover (keyboard-accessible)
│   ├── auto-on-error (open when error occurs)
│   └── always (for testing/learning)
│
└── Rendering
    ├── Level 1: bare content (no button)
    ├── Level 2: inline button + dropdown
    ├── Level 3+: card-style button + content block
    └── Mobile: bottom-sheet for Level 3+
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1–2)
- [x] Framework design (complete)
- [x] React component (complete)
- [x] CSS styles (complete)
- [x] Examples (complete)
- [ ] **TODO:** Integrate into Primnox
- [ ] **TODO:** Wire up expertise detection

### Phase 2: Chat Surface (Week 3)
- [ ] Message actions disclosure
  - [ ] Move edit/delete/bookmark to [More]
  - [ ] Keep copy/retry visible
  - [ ] Test with 5 power users
- [ ] Settings panel disclosure
  - [ ] Core (always shown)
  - [ ] Common (appearance)
  - [ ] Advanced (model, caching)

### Phase 3: Advanced Features (Week 4–5)
- [ ] Permission approval workflow
  - [ ] Auto-expand details on click
  - [ ] Nested runs history
- [ ] Error handling
  - [ ] Auto-expand logs on failure
  - [ ] Troubleshoot button → opens logs
- [ ] Workspace/file browser
  - [ ] Collapse by default, expand on click

### Phase 4: Expert/Debug (Week 6)
- [ ] Settings → [Debug] tab
  - [ ] Token accounting
  - [ ] Event log viewer
  - [ ] Provider call inspector
- [ ] Env-gated Level 5 features
  - [ ] API payload inspector
  - [ ] Sandbox introspection
  - [ ] Database query builder

### Phase 5: Polish (Week 7–8)
- [ ] Mobile testing
- [ ] Accessibility audit
- [ ] User feedback & iterate
- [ ] Performance optimization
- [ ] Documentation finalization

---

## Getting Started

### 1. Import the component

```tsx
import { ProgressiveDisclosure } from '@/components/ProgressiveDisclosure';
import '@/styles/progressive-disclosure.css';
```

### 2. Use in your component

```tsx
<ProgressiveDisclosure level="2-common" title="More options">
  <button>Edit</button>
  <button>Delete</button>
</ProgressiveDisclosure>
```

### 3. Run examples

```bash
npm run dev
# Navigate to /disclosure-examples to see all patterns
```

---

## Key Design Decisions

### Why Five Levels?

- **1-core**: The absolute minimum (no disclosure needed)
- **2-common**: Features most users need (shown by default)
- **3-advanced**: Features some users need (1 click away)
- **4-expert**: Features very few users need (settings panel)
- **5-debug**: Developer-only (env-gated, not in UI)

More levels → more complexity. Fewer levels → things get hidden.

### Why Frequency-based, Not Task-based?

Some decisions could be:
- "Hide things users might not understand" → patronizing, leads to feature blindness
- "Hide things by task complexity" → hard to predict in a tool that does many things
- **"Hide things users don't use often"** ← chosen, based on real usage data

### Why Auto-expand on Error?

When something fails, users need context to understand why. Auto-expanding disclosure helps:
- Shows relevant logs without extra clicks
- Reduces "something went wrong" frustration
- Keeps casual users from diving into logs most of the time

### Why Mobile Bottom-Sheet?

- Popovers/dropdowns get clipped on mobile
- Bottom sheets take full height, are swipeable
- Material Design + iOS standard
- Feels less modal than a full overlay

---

## Metrics to Track

After launch, measure:

### Engagement
- % of users who reach Level 3+
- Average clicks to reach advanced feature
- Time spent in advanced disclosures

### Satisfaction
- NPS by expertise level
- "UI feels simpler" survey responses
- Support tickets about "where is X?"

### Performance
- Session duration by level
- Scroll depth (should decrease)
- Feature adoption over time

### Learning Curve
- Time from first turn to first [More] click
- % of users graduating to intermediate level
- Correlation between features used and expertise level

---

## Testing Strategy

### Unit Tests
- Component renders correctly per level
- Expertise detection works
- Error auto-expand triggers
- Keyboard navigation (Tab, Enter, Escape)

### Integration Tests
- Disclosure + settings integration
- Expertise persistence across sessions
- Error workflow end-to-end

### User Testing
- Novice users (< 5 conversations)
- Intermediate users (5–50 conversations)
- Expert users (> 50 conversations)
- Measure: can they find advanced features? How long?

---

## Known Limitations & Future Work

### Current Implementation
- ✅ Five-level model implemented
- ✅ React component with all features
- ✅ CSS with dark mode + responsive
- ✅ Examples & documentation
- ❌ Not yet integrated into Primnox

### Phase 2: Integration
- [ ] Wire up to existing Primnox components
- [ ] Migrate settings panel to use disclosure groups
- [ ] Add expertise detection from conversation history
- [ ] Test with real users

### Phase 3+: Enhancements (optional)
- Predictive disclosure (auto-show advanced options for power users)
- Onboarding tutorial showing each level
- "Feature spotlight" highlighting Level 3+ features periodically
- Telemetry-driven level adjustment (if a Level 3 feature is used 50%+ of the time, move to Level 2)

---

## File Structure

```
Primnox/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ProgressiveDisclosure.tsx (main component)
│   │   │   ├── PROGRESSIVE_DISCLOSURE_README.md (dev docs)
│   │   │   └── examples/
│   │   │       └── ProgressiveDisclosureExamples.tsx (copy-paste patterns)
│   │   └── styles/
│   │       └── progressive-disclosure.css (all styles)
│   └── ...
│
├── docs/
│   ├── PROGRESSIVE_DISCLOSURE_FRAMEWORK.md (strategy)
│   ├── DISCLOSURE_RULES_BY_FEATURE.md (feature mapping)
│   └── PROGRESSIVE_DISCLOSURE_SUMMARY.md (this file)
│
└── ...
```

---

## How to Use This System

### For Designers
- Read: `PROGRESSIVE_DISCLOSURE_FRAMEWORK.md`
- Reference: `DISCLOSURE_RULES_BY_FEATURE.md` for feature layouts
- Design mockups using the five levels

### For Developers
- Read: `frontend/src/components/PROGRESSIVE_DISCLOSURE_README.md`
- Copy examples from: `ProgressiveDisclosureExamples.tsx`
- Import component and styles, use in your component

### For Product Managers
- Reference: `DISCLOSURE_RULES_BY_FEATURE.md` for all feature decisions
- Track metrics from "Metrics to Track" section
- Gather user feedback on specific levels

### For QA / Testing
- Test checklist in `PROGRESSIVE_DISCLOSURE_README.md` (Testing section)
- Test all five levels across desktop/mobile/dark mode
- Test expertise progression (novice → expert)
- Test error auto-expansion

---

## Quick Reference

### Component Props
```tsx
<ProgressiveDisclosure
  level="2-common"           // 1-core to 5-debug
  title="More"               // Button text
  userExpertise="novice"     // Optional override
  expandOnError={true}       // Auto-expand on error?
  errorContext={null}        // Error message
  cardStyle={true}           // Card or inline?
  onOpen={() => {}}          // Callback
>
  {children}
</ProgressiveDisclosure>
```

### CSS Classes
```css
.disclosure-level-1         /* Core content (no styling) */
.disclosure-level-2         /* Common (inline disclosure) */
.disclosure-level-3         /* Advanced (card) */
.disclosure-level-4         /* Expert (card) */
.disclosure-level-5         /* Debug (card) */
.disclosure-trigger-common  /* Level 2 button */
.disclosure-trigger-advanced /* Level 3+ button */
.disclosure-content-inline  /* Level 2 revealed content */
.disclosure-content-card    /* Level 3+ revealed content */
```

### Hooks
```tsx
const { expertise, updateExpertise } = useUserExpertise();
const { errorContext, triggerExpand, clearError } = useErrorContext();
```

---

## Next Steps

1. **Review & Validate** — Is this the right model for Primnox?
2. **Integration** — Migrate one surface (e.g., settings panel) to use disclosure
3. **Test with Users** — Gather feedback from novice → expert users
4. **Iterate** — Adjust levels based on real usage
5. **Roll Out** — Phase 2+ implementation across all surfaces

---

## Questions?

- **Framework questions** → Read `PROGRESSIVE_DISCLOSURE_FRAMEWORK.md`
- **Implementation questions** → Read `PROGRESSIVE_DISCLOSURE_README.md`
- **Feature-specific questions** → Read `DISCLOSURE_RULES_BY_FEATURE.md`
- **Examples** → See `ProgressiveDisclosureExamples.tsx` (runnable showcase)

---

## Acknowledgments

- UI/UX Pro Max skill for progressive disclosure best practices
- Material Design & iOS HIG for mobile patterns
- Cursor, ChatGPT, Notion for real-world disclosure patterns
- Primnox community for feature requests & feedback

---

**Status:** Framework & component complete. Ready for integration into Primnox.
**Next milestone:** Phase 2 integration (Week 3).
