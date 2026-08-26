# Mainstream Assistants UI Prototype

Interactive showcase of standard assistant UI patterns, implemented with Primnox's **Tactical Telemetry** aesthetic.

## Overview

This prototype demonstrates the converged UI patterns found across ChatGPT, Google Gemini, Microsoft Copilot, and Claude:

- **Left sidebar navigation** with chat history
- **Center conversation transcript** with message alternation (user → assistant)
- **Message actions** (Copy, Regenerate)
- **Bottom input field** with file attachment and voice input hints
- **Model selector** in top bar
- **Settings and user menu** in top-right
- **Empty state** with suggested prompts

## Key Features

### Standard Patterns Demonstrated

1. **Navigation Layout**
   - Left sidebar with conversation history
   - New chat button at top
   - Recent conversations list
   - Active conversation highlighting

2. **Message Display**
   - User messages right-aligned with accent border
   - Assistant messages left-aligned with accent avatar
   - Streaming animation placeholder
   - Avatar differentiation (system symbol ✦ vs. user label)

3. **Message Actions**
   - **Copy to clipboard** button
   - **Regenerate response** button
   - Hover-revealed action menu
   - Visual feedback (COPIED state after copy)

4. **Input Field**
   - Growing textarea (expands as user types)
   - File attachment button (paperclip icon)
   - Voice input button (microphone icon)
   - Send/Stop button (changes during generation)
   - Shift+Enter for new line hint

5. **Empty State**
   - Centered heading: "What are you working on?"
   - 4 suggested prompt cards
   - Hover interaction on prompt cards
   - Click to populate input field

6. **Model Selector**
   - Inline in top bar
   - Dropdown indicator (chevron)
   - Shows current model selection

## Styling: Tactical Telemetry Aesthetic

The prototype strictly adheres to Primnox's design specification:

### Color Palette
- **Substrate:** `#0A0A0A` (deactivated CRT, never pure black)
- **Text:** `#EAEAEA` (white phosphor, 16.46:1 contrast)
- **Accent (text):** `#FF2A2A` (hazard red, 5.30:1 contrast)
- **Accent (structure):** `#E61919` (hazard red structure, 4.26:1 contrast)
- **Terminal green:** `#4AF626` (rationed, state-only: success/connected)

### Typography
- **Interface:** JetBrains Mono (monospace, uppercase labels)
- **Tracking:** 0.05em–0.2em letter-spacing
- **Font size:** 10–12px for labels, 12px for body

### Geometry
- **Border radius:** 0 (strictly enforced)
- **Shadows:** None (inset hairlines only)
- **Gradients:** None (flat fields only)

### Motion
- **State animations only:** pulse on icon, slide-in on messages
- **No decorative effects:** animations respect `prefers-reduced-motion`

## Accessibility

- **WCAG 2.1 AA** compliant
- **Contrast verified:** all text meets minimum 4.5:1
- **Keyboard navigation:** all buttons interactive via Tab + Enter
- **Screen reader labels:** `aria-label` and `title` attributes
- **Motion preferences:** all animations disabled under `prefers-reduced-motion`

## Component Structure

```
MainstreamShowcase.tsx          Main container component
├── State management
│   ├── messages: Message[]
│   ├── input: string
│   ├── isGenerating: boolean
│   ├── selectedConversation: Conversation
│   └── selectedModel: string
├── Top bar (model selector, settings, user menu)
├── Left sidebar (chat history, new chat button)
├── Main area (conversation transcript or empty state)
└── Input area (textarea, actions, hints)

mainstream.css                  Tactical Telemetry styling
├── Layout grid (sidebar + main + input)
├── Component blocks (topbar, sidebar, transcript, input)
├── Message styling (user vs. assistant)
├── Action buttons and interactive states
├── Responsive breakpoints (mobile: hide sidebar)
└── Accessibility (prefers-reduced-motion, keyboard focus)
```

## Usage

### Import and Render

```tsx
import { MainstreamShowcase } from '@/components/proto/mainstream-assistants';

export default function ProtoPage() {
  return <MainstreamShowcase />;
}
```

### Customization

The component accepts no props but can be extended to:

- Connect to real API endpoints
- Persist conversation state to database
- Add more models to the selector
- Customize suggested prompts
- Add theme switcher (though Primnox is dark-only by design)

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## Responsive Behavior

### Mobile (< 768px)
- Sidebar hidden by default
- Hamburger menu for navigation
- Full-width conversation area
- Single-column suggested prompts
- Optimized touch targets (32px minimum)

### Desktop (≥ 768px)
- Sidebar always visible (240px width)
- Conversation area flexible
- 2-column suggested prompts grid
- Traditional mouse/keyboard interaction

## Known Limitations

1. **No real API integration** — responses are simulated with 1.5s delay
2. **No persistence** — state resets on page reload
3. **Dark-only theme** — Primnox intentionally has no light mode
4. **No streaming animation** — simplified placeholder for demonstration
5. **Mock data only** — conversation history is hardcoded

## Future Enhancements

- [ ] Real streaming responses with animation
- [ ] Actual file upload and preview
- [ ] Voice input integration
- [ ] Conversation persistence (localStorage or database)
- [ ] Export/share conversation (PDF, Markdown)
- [ ] Conversation search and filtering
- [ ] Suggested follow-up questions
- [ ] Reaction emoji feedback (👍 👎)

## Research Context

This prototype is built as part of **Unit 1: Mainstream Assistants UI Audit**. The full research findings are documented in:

**File:** `/docs/ui-research/01-mainstream-assistants.md`

**Key findings:**
- All mainstream assistants converge on a similar layout
- Primnox's "Dead Reckoning" navigation diverges significantly
- Missing standard patterns in Primnox: copy button, regenerate button, suggested prompts, search
- Primnox's strengths: WCAG AA compliance, honest uncertainty visualization, distinctive aesthetic

## Related Files

- `/docs/ui-research/01-mainstream-assistants.md` — Full research document
- `/frontend/src/components/TurnBlock.tsx` — Primnox's turn visualization
- `/frontend/src/components/Canvas.tsx` — Primnox's current conversation area
- `/DESIGN.md` — Primnox's design specification

---

**Prototype Version:** 1.0  
**Date Created:** August 2026  
**Status:** Demonstration / Reference
