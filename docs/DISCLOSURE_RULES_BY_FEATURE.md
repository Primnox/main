# Disclosure Rules by Feature

Concrete mapping of each Primnox feature to the five disclosure levels, with frequency estimates and implementation guidance.

---

## Chat & Messaging

### Message Bubble

| Action | Level | Frequency | Rationale | Implementation |
|--------|-------|-----------|-----------|-----------------|
| Copy message text | 1-core | ~95% | Every conversation, essential | Always visible as inline button |
| Send message | 1-core | 100% | Every turn | Chat input + send button, always visible |
| Stop generation | 1-core | ~30% (conditional) | When model is thinking | Show only when active (not hidden) |
| Edit message | 2-common | ~65% | Power users correct mistakes | Inline button after [Copy] |
| Delete message | 2-common | ~45% | Housekeeping | In [More ▼] dropdown |
| Bookmark/favorite | 2-common | ~35% | Users save important answers | In [More ▼] dropdown |
| Regenerate/retry | 2-common | ~55% | Depends on model quality | Prominent retry button, separate from actions |
| Emoji reaction | 2-common | ~25% | Light users use, power users skip | In [More ▼] dropdown |
| Archive message | 3-advanced | ~15% | Advanced workflow | In [More ▼] → [Advanced] |
| Copy as markdown | 3-advanced | ~18% | Developers export content | In [More ▼] → [Advanced] |
| View raw JSON | 4-expert | ~3% | Debugging | Settings → [Debug] tab |
| Replay this turn | 4-expert | ~5% | Recovery from failure | Settings → [Advanced] tab |

### Chat Bubble Disclosure Layout

**Initial state (Level 1):**
```
┌─ Message ──────────────────┐
│ Here's a summary of your   │
│ document. Let me know if   │
│ you need more detail.      │
│                            │
│ [Copy] [More ▼]           │
└────────────────────────────┘
```

**Expanded (Level 2, after clicking More):**
```
┌─ Message ──────────────────┐
│ Here's a summary of your   │
│ document. Let me know if   │
│ you need more detail.      │
│                            │
│ [Copy] [More ▼]           │
│ ┌─ Actions ──────────────┐ │
│ │ [Edit]  [Bookmark]     │ │
│ │ [Delete] [Emoji 👍]    │ │
│ └────────────────────────┘ │
└────────────────────────────┘
```

**If user clicks [Edit]:**
- Composer appears with message text
- User can modify and submit

---

## Conversation Management

### Conversation List

| Action | Level | Frequency | Rationale | Implementation |
|--------|-------|-----------|-----------|-----------------|
| Switch conversation | 1-core | ~85% | Foundation of navigation | Always visible, searchable list |
| Create new | 1-core | ~50% | Start fresh chats | "New" button, always visible |
| Rename conversation | 2-common | ~30% | Organize long chats | Context menu [Rename] |
| Archive conversation | 2-common | ~35% | Clean up inactive | Context menu [Archive] |
| Pin conversation | 2-common | ~20% | Quick access to favorites | Context menu [Pin] |
| Share conversation | 3-advanced | ~12% | Rare, power-user feature | Context menu → [More] → [Share] |
| Export as PDF | 3-advanced | ~8% | Archival/documentation | Context menu → [More] → [Export PDF] |
| Delete permanently | 3-advanced | ~5% | Destructive action | Context menu → [More] → [Delete permanently] |
| View conversation metadata | 4-expert | ~2% | Debug/introspection | Settings → [Debug] → [Conversations] |
| Replay conversation | 4-expert | ~3% | Recovery from data loss | Settings → [Advanced] → [Replay/Restore] |

### Conversation Context Menu Layout

**Right-click on conversation:**
```
┌─ Conversation Menu ────────┐
│ Rename                     │
│ Archive                    │
│ Pin to top                 │
│ More ▼                     │
│   ├─ Share                 │
│   ├─ Export PDF            │
│   ├─ Delete permanently    │
│   └─ Metadata              │
└────────────────────────────┘
```

---

## Settings & Preferences

### Core Settings (Level 1)

Always visible, no disclosure:
- Theme (light/dark/auto)
- Notifications (on/off)
- Account info

**Component:**
```tsx
<ProgressiveDisclosureGroup level="1-core" title="Core">
  <ThemeToggle />
  <NotificationToggle />
</ProgressiveDisclosureGroup>
```

### Appearance Settings (Level 2)

Shown by default in main settings:
- Font size
- Density (compact/normal/spacious)
- Sidebar width
- Chat bubble width
- Font family (monospace, serif, sans)

**Component:**
```tsx
<ProgressiveDisclosureGroup level="2-common" title="Appearance">
  <FontSizeSlider />
  <DensitySelector />
  <SidebarWidthSlider />
</ProgressiveDisclosureGroup>
```

### Advanced Settings (Level 3)

Collapse/expand card:
- Model/provider selection (most use defaults)
- Tool caching (on/off)
- Auto-approval level (off/once/turn/always)
- Streaming mode (on/off)
- Memory across conversations
- Context window size

**Component:**
```tsx
<ProgressiveDisclosure level="3-advanced" title="Advanced" cardStyle>
  <ModelSelector />
  <ToolCachingToggle />
  <AutoApprovalLevel />
</ProgressiveDisclosure>
```

### Debug Settings (Level 4)

Settings → [Debug] tab:
- Event logging (per-turn)
- Token accounting dashboard
- Provider call inspector
- Cache hit ratio
- Workspace snapshots
- Replay recorder

**Component:**
```tsx
<ProgressiveDisclosureGroup level="4-expert" title="Debug">
  <TokenAccounting />
  <ProviderCallLog />
  <CacheStats />
</ProgressiveDisclosureGroup>
```

### Environment-gated Debug (Level 5)

Only visible when `PRIMNOX_DEBUG=1`:
- Raw API payload inspector
- SQL query builder (for workspace)
- Sandbox introspection
- Full event trace timeline

---

## Permission Approval Workflow

### Permission Request Card (Level 1–3)

| Content | Level | Show | Trigger |
|---------|-------|------|---------|
| Tool name + brief description | 1-core | Always | – |
| [Allow once] [For this turn] [Deny] | 1-core | Always | – |
| Tool icon | 1-core | Always | – |
| Arguments (JSON preview) | 2-common | By default | Click [Details] |
| Sandbox constraints | 2-common | With details | Click [Details] |
| Historical run logs (if any) | 3-advanced | Nested | Click [More] inside details |
| Approval history | 4-expert | Settings panel | Settings → [Advanced] |

### Permission Card Layout

**Initial state (Level 1):**
```
┌─ Permission ───────────────┐
│ Run Python                 │
│ Execute Python code in a   │
│ sandboxed environment.     │
│                            │
│ [Allow once] [For turn]    │
│ [Deny]       [Details ▼]  │
└────────────────────────────┘
```

**After clicking [Details] (Level 2):**
```
┌─ Permission ───────────────┐
│ Run Python                 │
│ Execute Python code in a   │
│ sandboxed environment.     │
│                            │
│ Arguments:                 │
│ code: "print('hello')"     │
│                            │
│ Sandbox:                   │
│ ◇ Read Documents only      │
│ ◇ 30-second timeout        │
│ ◇ No network access        │
│                            │
│ [Allow once] [For turn]    │
│ [Deny]       [More ▼]     │
└────────────────────────────┘
```

**After clicking [More] (Level 3):**
```
...previous content...
│ Previous runs in this chat │
│ ├─ Turn 3: ✓ Success       │
│ ├─ Turn 5: ✓ Success       │
│ └─ Turn 7: ✓ Success       │
│                            │
│ [Allow once] [For turn]    │
│ [Deny]       [More ▲]     │
└────────────────────────────┘
```

---

## Error & Failure States

### Generic Error Message (Level 1)

**Always shown:**
```
⚠ Message failed. Try again.
[Retry] [Troubleshoot]
```

### Error Details (Level 2)

**Click [Troubleshoot]:**
```
Provider: claude-aerolink
Error: Rate limit (429)
Retried: 2/3
Next retry in: 4 seconds
[Retry now] [Open logs]
```

### Raw Logs (Level 3)

**Click [Open logs]:**
```
[14:32:18.341] POST /api/messages
  Headers: {...}
  Payload: {...}

[14:32:19.102] Stream start
  Model: claude-3-5-sonnet
  First token: 45ms

[14:33:48.901] Timeout
  Elapsed: 30000ms
  Tokens sent: 1,450
  Status: 408 Request Timeout
```

### Debug Introspection (Level 4)

**Settings → [Debug] → [Error Logs]:**
- Full stack trace
- Provider-specific errors
- Sandbox output
- Network inspector

---

## Workspace & File Management

### Workspace File List (Level 2–3)

| Content | Level | Show | Trigger |
|---------|-------|------|---------|
| File list (read-only view) | 2-common | Expandable | Click [Files ▼] in message |
| Download file | 2-common | Shown if files exist | Direct download link |
| Copy file path | 3-advanced | In [More] | Click [More ▼] on file |
| View file metadata | 3-advanced | Nested | Click [More ▼] on file |
| Delete file | 3-advanced | In [More] | Click [More ▼] on file |
| Raw file contents | 4-expert | Settings panel | Settings → [Debug] → [Workspace] |
| Workspace snapshot | 4-expert | Settings panel | Settings → [Advanced] → [Snapshots] |

### File Browser Disclosure

**Collapsed (Level 2):**
```
[Files ▼] (showing count: 3 files, 2.4 MB)
```

**Expanded (Level 2):**
```
Files ▼
├─ summary.md (1.2 MB)
├─ data.csv (800 KB)
└─ chart.png (400 KB)
[Download all]
```

**File context menu (Level 3):**
```
Right-click on file:
├─ Download
├─ Copy path
├─ More ▼
│  ├─ View metadata
│  ├─ Delete
│  └─ View raw
```

---

## Model & Provider Selection

### Current Model Display (Level 1)

Always shown in header or chat input:
```
Model: Claude 3.5 Sonnet
```

### Model Selector (Level 3)

Click on model name → disclosure opens:
```
┌─ Model Selection ──────────┐
│ ◇ Claude 3.5 Sonnet        │
│ ◇ Claude 3 Opus            │
│ ◇ Claude 3 Haiku           │
│ ◇ Local Llama (if avail.)  │
│                            │
│ [Advanced ▼]              │
└────────────────────────────┘
```

**After clicking [Advanced]:**
```
Provider: claude-aerolink
Endpoint: https://api.anthropic.com
Timeout: 30s
Max tokens: 8192
Tool calling: ✓ Supported
```

### Provider Configuration (Level 4)

Settings → [Advanced] → [Provider Config]:
- API key validation
- Endpoint URL
- Custom timeouts
- Custom headers
- Rate limit settings

---

## Notifications & Alerts

### Toast/Notification (Level 1–2)

| Type | Level | Display | Dismiss |
|------|-------|---------|---------|
| Success | 1-core | Brief (4s) | Auto |
| Warning | 1-core | 6s | Auto |
| Error | 2-common | Persistent | Manual |
| Info | 2-common | 4s | Auto |

**Example:**
```
✓ Message saved
[Details ▼]  (click for more info)
```

### Detailed Notification (Level 3)

**Click [Details]:**
```
Message saved to conversation "Project Ideas"
Saved at: 2026-08-26 14:32:18 UTC
Size: 1.2 KB
[Undo save]
```

---

## Keyboard Shortcuts & Help

### Shortcut Hints (Level 2)

Show on hover or focus:
```
Copy message     Ctrl+C
Edit message     Ctrl+E
Send message     Ctrl+Enter
```

### Full Shortcut List (Level 3)

Click [?] or [Help] → opens disclosure:
```
Editor
  Ctrl+Z       Undo
  Ctrl+Shift+Z Redo
  Ctrl+B       Bold
  Ctrl+I       Italic
  Ctrl+K       Insert link

Navigation
  Ctrl+/       Command palette
  Ctrl+J       Jump to conversation
  Ctrl+N       New conversation
  Escape       Close modals

System
  Ctrl+,       Settings
  Ctrl+?       Help
  Ctrl+Q       Quit (desktop)
```

### Command Palette (Level 1)

Always accessible:
```
Ctrl+K → Search & run commands
```

---

## Token Accounting & Costs

### Token Display (Level 3)

In message footer (collapsed):
```
↓ View token breakdown [▼]
```

**Expanded (Level 3):**
```
Tokens used:
  Input:  1,450 tokens
  Output:   280 tokens
  Cache:    622 (read)
  Total:  2,352 effective
```

### Detailed Accounting (Level 4)

Settings → [Debug] → [Token Accounting]:
- Per-conversation totals
- Per-turn breakdown
- Cache hit ratio (% of input from cache)
- Cost estimation (if using paid API)
- Efficiency metrics

---

## Accessibility & Keyboard Navigation

### Focus Indicators (Level 1)

Always visible (fixed by recent CSS changes):
- Keyboard focus ring (2px primary color)
- Visible on all interactive elements

### Accessible Names (Level 1)

All icon buttons must have aria-label or title:
```tsx
<button aria-label="Delete message">
  <Trash2 size={16} />
</button>
```

### ARIA Annotations (Level 2)

For complex interactive states:
```tsx
<button
  aria-expanded={isOpen}
  aria-controls="disclosure-content"
>
  More options
</button>
```

---

## Mobile-Specific Disclosures

### Mobile Adjustments

| Feature | Desktop | Mobile |
|---------|---------|--------|
| Message actions | Inline buttons + [More] | Slide-up action sheet |
| Settings | Sidebar panel | Bottom tab navigation |
| Permission dialog | Modal card | Bottom sheet |
| File browser | Inline disclosure | Full-screen list |

### Bottom Sheet Pattern (Level 3+ on Mobile)

```
────────────────────────────
        ╱────╲  (drag handle)
       │ Settings    ✕ │
────────────────────────────
│ [General] [Advanced]    │
│                         │
│ Font size:    [slider]  │
│ Theme:        [select]  │
│                         │
│ [Save]  [Cancel]        │
────────────────────────────
```

---

## Implementation Roadmap

### Week 1: Audit & Plan
- [ ] Measure frequency of each control (survey + logs)
- [ ] Create mapping spreadsheet
- [ ] Categorize by level
- [ ] Share with team for validation

### Week 2: Level 2 Implementation
- [ ] Chat message actions → [More] disclosure
- [ ] Test with 5 power users
- [ ] Iterate on label/organization

### Week 3: Level 3 Implementation
- [ ] Settings panel refactor
- [ ] Permission details expansion
- [ ] Error details expansion
- [ ] File browser collapse/expand

### Week 4: Levels 4–5 Implementation
- [ ] Settings → [Debug] tab
- [ ] Token accounting display
- [ ] Event log viewer
- [ ] Env-gated debug features

### Week 5: Polish & Launch
- [ ] Mobile/responsive testing
- [ ] Accessibility audit
- [ ] User feedback & iterate
- [ ] Documentation

---

## Success Metrics

Track after rollout:

1. **Discoverability**
   - % of users who find Level 3+ features
   - Time to discover advanced options
   - Support tickets about "missing" features

2. **Cognitive Load**
   - Session duration (should decrease)
   - Scroll depth (should decrease for novices)
   - Feature adoption rates

3. **User Satisfaction**
   - NPS (Net Promoter Score)
   - "UI feels cleaner" survey responses
   - Support ticket volume

4. **Expertise Progression**
   - % of users graduating to each level
   - Time to graduation from novice → intermediate → expert

---

## Notes for Implementation

- **Frequency estimates** are based on similar products (Cursor, ChatGPT, Notion) and Primnox v1 telemetry
- **Adjust levels based on actual usage** — measure after implementation
- **Don't hide essential features** — when in doubt, show it (better to clutter than hide)
- **Test with real users** — especially power users and novices separately
- **Mobile matters** — bottom sheets work better than popovers on touch devices
- **Accessibility first** — ensure all disclosures are keyboard-navigable and screen-reader friendly
