/**
 * Extracted Navigation Rail Component
 *
 * DO-NOT-CHANGE:
 * - Width: 64px (exact, logo sizing depends on it)
 * - Expansion: transition-none with CSS width (not animated, reduced-motion safe)
 * - Accessibility: aria-label always present (not hidden at 64px)
 * - Active indicator: aria-current="page" (not color-only)
 */

import { Brain, Circle, MessageSquare, SlidersHorizontal } from 'lucide-react';
import { ThemeCycle } from '../../ThemePicker';

export type RailSection = 'chat' | 'knowledge' | 'memory' | 'settings';

export interface RailItem {
  id: RailSection;
  label: string;
  icon: React.ComponentType<{ size: number; className?: string }>;
  hint: string;
}

export interface NavigationRailProps {
  section: RailSection;
  onSection: (s: RailSection) => void;
  connected: boolean;
  synced: boolean;
  showKnowledge?: boolean;
}

// DO-NOT-CHANGE: Item order is canonical for screen readers
const RAIL_ITEMS: RailItem[] = [
  { id: 'chat', label: 'Chats', icon: MessageSquare, hint: 'Conversations' },
  { id: 'memory', label: 'Memory', icon: Brain, hint: 'What Primnox knows about you' },
  { id: 'settings', label: 'Settings', icon: SlidersHorizontal, hint: 'Theme, provider, tuning' },
];

/**
 * Left navigation rail: 64px of icons, expanding to labels on hover/focus.
 *
 * DO-NOT-CHANGE:
 * - Base width 64px (logo and icon sizing depend on exact measurement)
 * - Expansion to 196px on hover/focus-within (tuned for label visibility)
 * - transition-none on width (reduced-motion interaction is fragile, see AppRail.tsx lines 51-67)
 * - aria-label always present (not hidden at 64px, ensures keyboard users see navigation)
 * - aria-current="page" marks active (not color-only, WCAG requirement)
 *
 * Logo: Dot + wordmark (not icon swap). Dot is brand identity and never leaves.
 */
export function NavigationRail({
  section,
  onSection,
  connected,
  synced,
  showKnowledge = false,
}: NavigationRailProps) {
  const items = showKnowledge
    ? [
        RAIL_ITEMS[0], // chat
        { id: 'knowledge' as const, label: 'Knowledge', icon: MessageSquare, hint: 'The indexed corpus' },
        RAIL_ITEMS[1], // memory
        RAIL_ITEMS[2], // settings
      ]
    : RAIL_ITEMS;

  return (
    // Reserved 64px column; nav inside expands OVER content (not pushing it)
    // Animating width in-flow reflowed entire app; CSS width with no transition is correct
    <div className="group relative z-30 w-16 shrink-0 h-full">
      <nav
        aria-label="Primary"
        className="absolute inset-y-0 left-0 w-16 flex flex-col overflow-hidden
                   border-r border-on-surface/[0.07] bg-[var(--nav-bg)]
                   transition-none group-hover:w-[196px] focus-within:w-[196px]"
      >
        {/* Logo: Pulsing dot + wordmark (mirrors website branding)
            Dot never leaves (it IS the collapsed mark)
            Wordmark slides out from behind dot on expand
            Rendered at 64px but only visible when expanded due to parent overflow-hidden */}
        <div
          className="group/mark h-14 shrink-0 flex items-center gap-3 px-[22px]"
          role="img"
          aria-label="Primnox"
        >
          <span
            aria-hidden="true"
            className="w-[7px] h-[7px] rounded-full bg-on-surface shrink-0
                       transition-transform duration-200 group-hover/mark:scale-125"
          />
          <span
            aria-hidden="true"
            className="px-wordmark font-display font-bold text-[13px] uppercase
                       tracking-[0.18em] whitespace-nowrap"
          >
            Primnox
          </span>
        </div>

        {/* Navigation destinations (not actions)
            "New Chat" and "Incognito" belong with the conversation list, not here.
            Rail items are places you ARE (aria-current="page"), not actions you DO. */}
        <ul role="list" className="flex-1 px-3 pt-2 space-y-1">
          {items.map((item) => (
            <li key={item.id}>
              <RailButton
                icon={item.icon}
                label={item.label}
                hint={item.hint}
                active={section === item.id}
                current={section === item.id}
                onClick={() => onSection(item.id)}
              />
            </li>
          ))}
        </ul>

        {/* Footer: Theme toggle and connection status
            Both use label + icon so status survives at collapsed width */}
        <div className="shrink-0 px-3 pb-3 pt-2 space-y-3 border-t border-on-surface/[0.07]">
          <div className="flex items-center gap-2 px-1.5 pt-2">
            <ThemeCycle />
            <span className="px-label whitespace-nowrap text-[12px]">Theme</span>
          </div>
          <div className="flex items-center gap-2 px-1.5">
            <Circle
              size={6}
              aria-hidden="true"
              className={`shrink-0 fill-current ${connected ? 'text-primary' : 'text-error'}`}
            />
            <span className="px-label whitespace-nowrap text-[12px]">
              {connected ? (synced ? 'Live' : 'Syncing') : 'Offline'}
            </span>
          </div>
        </div>
      </nav>
    </div>
  );
}

interface RailButtonProps {
  icon: React.ComponentType<{ size: number; className?: string }>;
  label: string;
  active?: boolean;
  current?: boolean;
  onClick: () => void;
  hint?: string;
}

/**
 * Rail button: icon + label (always labeled, not hover-only)
 *
 * DO-NOT-CHANGE:
 * - aria-label always present (keyboard users stepping through unlabelled icons is broken)
 * - aria-current="page" marks active (color alone doesn't work for colorblind/greyscale)
 * - No fade transition on label (width transitions fine, opacity doesn't under reduced-motion)
 */
function RailButton({
  icon: Icon,
  label,
  active,
  current,
  onClick,
  hint,
}: RailButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={hint ?? label}
      aria-current={current ? 'page' : undefined}
      className={`px-interactive w-full flex items-center gap-3 rounded-xl py-2.5 px-[11px]
        ${
          active
            ? 'bg-on-surface/[0.08] text-on-surface'
            : 'text-on-surface/55 hover:text-on-surface hover:bg-on-surface/[0.04]'
        }`}
    >
      <Icon size={16} className="shrink-0" aria-hidden="true" />
      {/* Always rendered and always opaque. Parent's overflow-hidden hides at 64px.
          One thing (width) controls visibility, not width + opacity that can disagree. */}
      <span className="px-rail-label text-[13px] whitespace-nowrap">{label}</span>
    </button>
  );
}
