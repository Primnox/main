# Progressive Disclosure — Implementation Guide

A five-level disclosure system for Primnox that reduces cognitive overload by revealing information and options in stages.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Core Concepts](#core-concepts)
3. [Component API](#component-api)
4. [Usage Patterns](#usage-patterns)
5. [Styling & Theming](#styling--theming)
6. [Testing](#testing)
7. [Migration Checklist](#migration-checklist)

---

## Quick Start

### Import and use in your component

```tsx
import { ProgressiveDisclosure } from '@/components/ProgressiveDisclosure';

export function MyComponent() {
  return (
    <ProgressiveDisclosure level="2-common" title="More options">
      <button>Bookmark</button>
      <button>Archive</button>
    </ProgressiveDisclosure>
  );
}
```

### Import styles

```tsx
// In your main layout or app component
import '@/styles/progressive-disclosure.css';
```

---

## Core Concepts

### The Five Levels

| Level | Used when | Visibility | Trigger |
|-------|-----------|------------|---------|
| **1-core** | In 80%+ of sessions | Always shown | None |
| **2-common** | In 40–80% of sessions | Shown by default | Click "More" |
| **3-advanced** | In 10–40% of sessions | Hidden, 1 click | Click button |
| **4-expert** | In < 10% of sessions | Hidden, deep menu | Settings panel |
| **5-debug** | Developers only | Off by default | Env flag |

### Expertise Levels

Users automatically graduate as they use the app:

- **Novice** (< 5 conversations): Sees Levels 1–2
- **Intermediate** (5–50 conversations): Sees Levels 1–3
- **Expert** (> 50 conversations): Sees Levels 1–4
- **Developer** (env flag): Sees all levels

Users can manually set their expertise in settings.

---

## Component API

### `<ProgressiveDisclosure />`

The main disclosure component.

#### Props

| Prop | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `level` | `'1-core' \| '2-common' \| '3-advanced' \| '4-expert' \| '5-debug'` | Yes | — | Disclosure level |
| `title` | `string` | No | `'More'` | Text shown on trigger button |
| `children` | `ReactNode` | Yes | — | Content to reveal |
| `userExpertise` | `UserExpertise` | No | Inferred from localStorage | User's expertise level |
| `triggerMode` | `'click' \| 'hover' \| 'auto-on-error' \| 'always'` | No | `'click'` | How to trigger reveal |
| `expandOnError` | `boolean` | No | `true` | Auto-expand if error context set |
| `errorContext` | `string \| null` | No | `null` | Error message (triggers expand if set) |
| `className` | `string` | No | `''` | Additional CSS classes |
| `onOpen` | `() => void` | No | — | Callback when opened |
| `onClose` | `() => void` | No | — | Callback when closed |
| `icon` | `ReactNode` | No | `<ChevronDown />` | Custom icon for trigger |
| `collapsedDescription` | `string` | No | — | Description shown in collapsed state |
| `forceVisible` | `boolean` | No | `false` | Always show, even if expertise too low |
| `cardStyle` | `boolean` | No | `false` | Render as card (Level 3+) or inline |

#### Example

```tsx
<ProgressiveDisclosure
  level="3-advanced"
  title="Advanced Settings"
  cardStyle={true}
  onOpen={() => console.log('User opened advanced settings')}
>
  <SettingsList />
</ProgressiveDisclosure>
```

### `<ProgressiveDisclosureGroup />`

Wrapper for organizing multiple disclosure items (e.g., in settings panel).

#### Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `level` | `DisclosureLevel` | — | Disclosure level |
| `title` | `string` | — | Group title |
| `children` | `ReactNode` | — | Content |
| `userExpertise` | `UserExpertise` | Inferred | User expertise |
| `className` | `string` | `''` | Additional CSS classes |

#### Example

```tsx
<ProgressiveDisclosureGroup level="2-common" title="Appearance">
  <ThemeSelector />
  <DensitySelector />
</ProgressiveDisclosureGroup>

<ProgressiveDisclosureGroup level="3-advanced" title="Advanced">
  <TokenAccounting />
  <CacheSettings />
</ProgressiveDisclosureGroup>
```

### Hooks

#### `useUserExpertise()`

Get and update user expertise level.

```tsx
const { expertise, updateExpertise } = useUserExpertise();

// Read current level
console.log(expertise); // 'intermediate'

// Update to higher level
updateExpertise('expert');
```

#### `useErrorContext()`

Manage error-driven disclosure expansion.

```tsx
const { errorContext, triggerExpand, clearError } = useErrorContext();

// In error handler
if (error) {
  triggerExpand(error.message);
}

// When user fixes it
if (resolved) {
  clearError();
}
```

### Components

#### `<DisclosureLevelBadge />`

Visual badge showing a level (for documentation, learning mode).

```tsx
<DisclosureLevelBadge level="3-advanced" />
// Renders: a colored badge with "Advanced" label
```

---

## Usage Patterns

### Pattern 1: Message Actions (Common + Advanced)

Show common actions inline, advanced actions in dropdown:

```tsx
<div>
  <p>{message.text}</p>
  <div className="flex gap-2">
    {/* Level 1: Always shown */}
    <CopyButton text={message.text} />

    {/* Level 2: Common actions in disclosure */}
    <ProgressiveDisclosure level="2-common" title="More">
      <EditButton messageId={message.id} />
      <BookmarkButton messageId={message.id} />
      <DeleteButton messageId={message.id} />
    </ProgressiveDisclosure>
  </div>
</div>
```

### Pattern 2: Settings Panel (All Levels)

Organize settings by disclosure level:

```tsx
<div>
  {/* Level 1: Core appearance */}
  <ProgressiveDisclosureGroup level="1-core" title="Core">
    <ThemeToggle />
  </ProgressiveDisclosureGroup>

  {/* Level 2: Common settings */}
  <ProgressiveDisclosureGroup level="2-common" title="Appearance">
    <FontSizeSlider />
    <DensitySelector />
  </ProgressiveDisclosureGroup>

  {/* Level 3: Power-user options */}
  <ProgressiveDisclosure level="3-advanced" title="Advanced" cardStyle>
    <ToolCachingToggle />
    <StreamingToggle />
  </ProgressiveDisclosure>

  {/* Level 4: Expert debugging */}
  <ProgressiveDisclosure level="4-expert" title="Debug Info" cardStyle>
    <TokenAccounting />
    <EventLog />
  </ProgressiveDisclosure>
</div>
```

### Pattern 3: Permission Approval (Context-aware)

Auto-expand details when user needs them:

```tsx
const { errorContext, triggerExpand } = useErrorContext();

return (
  <PermissionCard>
    <h3>Run Python</h3>

    {/* Level 1: Basic options */}
    <button>Allow Once</button>
    <button>For This Turn</button>
    <button onClick={() => triggerExpand('User denied')}>
      Deny
    </button>

    {/* Level 3: Details (auto-expands if user clicked Deny) */}
    <ProgressiveDisclosure
      level="3-advanced"
      title="Details"
      expandOnError={true}
      errorContext={errorContext}
    >
      <ToolDetails />
      <SandboxInfo />
      <PreviousRuns />
    </ProgressiveDisclosure>
  </PermissionCard>
);
```

### Pattern 4: Error Handling with Progressive Debugging

Auto-expand logs when error occurs:

```tsx
const [error, setError] = useState<string | null>(null);
const { errorContext, triggerExpand } = useErrorContext();

const handleError = (err: Error) => {
  setError(err.message);
  triggerExpand(err.message); // Auto-opens disclosure
};

return (
  <div>
    {error && (
      <ProgressiveDisclosure
        level="3-advanced"
        title="Error Details"
        expandOnError={true}
        errorContext={errorContext}
        cardStyle
      >
        <ErrorLogs />
        <ProviderInfo />
        <RetryButton />
      </ProgressiveDisclosure>
    )}
  </div>
);
```

### Pattern 5: Nested Disclosure (Multi-level drilling)

For expert users who need deep debugging:

```tsx
<ProgressiveDisclosure level="3-advanced" title="Execution Details">
  <div>
    <p>Time: 1.8s | Tokens: 1,450 in, 280 out</p>

    {/* Nested: Level 4 inside Level 3 */}
    <ProgressiveDisclosure level="4-expert" title="Raw API Logs">
      <CodeBlock>{JSON.stringify(apiResponse, null, 2)}</CodeBlock>
    </ProgressiveDisclosure>

    {/* Another nested: Level 4 inside Level 3 */}
    <ProgressiveDisclosure level="4-expert" title="Sandbox Trace">
      <CodeBlock>{sandboxTrace}</CodeBlock>
    </ProgressiveDisclosure>
  </div>
</ProgressiveDisclosure>
```

---

## Styling & Theming

### CSS Variables Used

```css
/* Colors */
--color-primary: #3b82f6;
--color-text-primary: #1f2937;
--color-text-secondary: #6b7280;
--color-text-tertiary: #9ca3af;
--color-bg-primary: #ffffff;
--color-bg-secondary: #f9fafb;
--color-bg-tertiary: #f3f4f6;
--color-border: #d1d5db;
--color-border-light: #e5e7eb;
--color-error: #ef4444;

/* Dark mode variants */
--color-text-primary-dark: #f9fafb;
--color-bg-primary-dark: #1f2937;
--color-border-dark: #374151;
```

### Custom Styling

Override styles by adding your own CSS or by setting CSS variables:

```css
/* Customize colors */
:root {
  --color-primary: #06b6d4; /* Custom blue */
  --color-border: #cbd5e1;   /* Custom border */
}

/* Customize specific level */
.disclosure-level-3 {
  border-width: 2px; /* Thicker border */
  border-radius: 1rem; /* More rounded */
}

/* Customize dark mode */
@media (prefers-color-scheme: dark) {
  .disclosure-trigger-common {
    background: rgba(255, 255, 255, 0.05);
  }
}
```

### Responsive Behavior

- Desktop: Card-style for Level 3+, inline for Level 2
- Mobile: Bottom-sheet for Level 3+ (slides up from bottom)
- Touch: Tap to toggle (no hover states)

---

## Testing

### Unit Tests

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProgressiveDisclosure } from '@/components/ProgressiveDisclosure';

describe('ProgressiveDisclosure', () => {
  it('shows trigger but hides content initially', () => {
    render(
      <ProgressiveDisclosure level="2-common" title="More">
        <div>Hidden content</div>
      </ProgressiveDisclosure>
    );

    expect(screen.getByRole('button', { name: /more/i })).toBeInTheDocument();
    expect(screen.queryByText('Hidden content')).not.toBeInTheDocument();
  });

  it('reveals content when trigger clicked', async () => {
    const user = userEvent.setup();
    render(
      <ProgressiveDisclosure level="2-common" title="More">
        <div>Hidden content</div>
      </ProgressiveDisclosure>
    );

    const trigger = screen.getByRole('button', { name: /more/i });
    await user.click(trigger);

    expect(screen.getByText('Hidden content')).toBeInTheDocument();
  });

  it('respects user expertise level', () => {
    render(
      <ProgressiveDisclosure
        level="4-expert"
        title="Expert Only"
        userExpertise="novice"
      >
        <div>Expert content</div>
      </ProgressiveDisclosure>
    );

    // Should not render for novice users
    expect(screen.queryByRole('button', { name: /expert only/i })).not.toBeInTheDocument();
  });

  it('auto-expands on error context', () => {
    const { rerender } = render(
      <ProgressiveDisclosure
        level="3-advanced"
        title="Details"
        expandOnError={true}
        errorContext={null}
      >
        <div>Error details</div>
      </ProgressiveDisclosure>
    );

    // Initially hidden
    expect(screen.queryByText('Error details')).not.toBeInTheDocument();

    // Rerender with error
    rerender(
      <ProgressiveDisclosure
        level="3-advanced"
        title="Details"
        expandOnError={true}
        errorContext="Request failed"
      >
        <div>Error details</div>
      </ProgressiveDisclosure>
    );

    // Now visible
    expect(screen.getByText('Error details')).toBeInTheDocument();
  });
});
```

### Integration Tests

```tsx
it('integrates with permission workflow', async () => {
  const user = userEvent.setup();
  render(<PermissionApprovalFlow />);

  // User sees basic options
  expect(screen.getByRole('button', { name: /allow once/i })).toBeInTheDocument();

  // User clicks "Details" to expand
  await user.click(screen.getByRole('button', { name: /details/i }));

  // Details appear
  expect(screen.getByText(/sandbox/i)).toBeInTheDocument();
  expect(screen.getByText(/read documents only/i)).toBeInTheDocument();
});
```

---

## Migration Checklist

### Phase 1: Audit Existing UI (Week 1)

- [ ] List all interactive elements in chat, settings, permission panels
- [ ] Measure frequency of each control (% of sessions)
- [ ] Categorize by disclosure level based on frequency
- [ ] Document in spreadsheet

### Phase 2: Implement Level 2 (Week 2)

- [ ] Mark Level 2 actions in components with metadata
- [ ] Create "More" disclosure for message actions
- [ ] Test with 5 power users
- [ ] Iterate based on feedback

### Phase 3: Implement Levels 3–4 (Week 3–4)

- [ ] Refactor Settings panel with tiers
- [ ] Add "Advanced" tab for Level 3
- [ ] Add "Debug" tab for Level 4
- [ ] Wire up token accounting display

### Phase 4: Error-driven Expansion (Week 5)

- [ ] Implement auto-expand on error
- [ ] Add error badges to disclosures
- [ ] Test failure scenarios

### Phase 5: Polish & Iteration (Week 6+)

- [ ] Refine CSS animations
- [ ] Test mobile/responsive
- [ ] Gather user feedback
- [ ] Iterate on disclosure timing

---

## Best Practices

### Do

- ✅ Use Level 2 for controls in 40–80% of sessions
- ✅ Nest disclosures for expert users drilling deeper
- ✅ Auto-expand on error to aid troubleshooting
- ✅ Provide a "More" button label that's descriptive ("Advanced", "Details", "Debug")
- ✅ Test with real users at different expertise levels
- ✅ Document which controls are which level

### Don't

- ❌ Put Level 3+ controls in Level 1 (hides them forever)
- ❌ Require more than 2 clicks to reach common features
- ❌ Auto-expand for trivial content (only do it on error or manual action)
- ❌ Hide the help text; always show what disclosure contains
- ❌ Use disclosure as a "make it smaller" tool (use it for frequency, not space)

---

## Troubleshooting

### "Content isn't showing even after clicking"

Check that:
1. `level` prop matches user's `userExpertise`
2. `forceVisible` is not `false` when it should be `true`
3. CSS class `.disclosure-content-inline` or `.disclosure-content-card` is not hidden by parent

### "Mobile looks broken (bottom-sheet clipped)"

Ensure:
1. `.disclosure-level-3.card-style` etc. have `position: fixed` (applied by default)
2. Parent container doesn't have `overflow: hidden`
3. Z-index doesn't conflict with other modals

### "Auto-expand on error isn't working"

Check that:
1. `expandOnError={true}` is set
2. `errorContext` is passed with a non-empty string
3. Component is re-rendering when error state changes

---

## Examples

See `ProgressiveDisclosureExamples.tsx` for:
- Chat message actions
- Settings panel with tiers
- Permission approval workflow
- Error handling with debugging
- Disclosure level badges

Run the examples:

```bash
npm run dev
# Navigate to /disclosure-examples
```

---

## References

- **Framework doc**: `docs/PROGRESSIVE_DISCLOSURE_FRAMEWORK.md`
- **Examples**: `frontend/src/components/examples/ProgressiveDisclosureExamples.tsx`
- **Styles**: `frontend/src/styles/progressive-disclosure.css`
- **Component**: `frontend/src/components/ProgressiveDisclosure.tsx`
