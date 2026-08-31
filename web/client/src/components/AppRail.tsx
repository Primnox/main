import {
  Circle, MessageSquare, SlidersHorizontal,
} from 'lucide-react';
import { ThemeCycle } from './ThemePicker';

export type Section = 'chat' | 'settings';

/* Desktop also carries Knowledge (the graph viewer, DEV-gated) and Memory
 * ("what Primnox knows about you"). Neither has anything behind it on web —
 * there is no indexed corpus and no memory store — and a rail item that
 * navigates to an empty panel is worse than one that is absent. They land here
 * when their sections do. */
const ITEMS: { id: Section; label: string; icon: any; hint: string }[] = [
  { id: 'chat', label: 'Chats', icon: MessageSquare, hint: 'Conversations' },
  { id: 'settings', label: 'Settings', icon: SlidersHorizontal, hint: 'Theme, provider, vault' },
];

/* The primary navigation: 64px of icons, expanding to labels on hover.
 *
 * Every item is a real button carrying its own name, and the name is NOT the
 * hover expansion — `aria-label` is present whether the rail is expanded or
 * not. Hover-only labelling would leave the entire navigation unnamed for
 * anyone using a keyboard, a screen reader, or a touchscreen, which is most of
 * the ways this rail can be operated.
 *
 * `aria-current="page"` rather than a colour alone marks the active section, so
 * "where am I" survives without sight of the highlight.
 */
export function AppRail({
  section, onSection, connected, synced,
}: {
  section: Section;
  onSection: (s: Section) => void;
  connected: boolean;
  synced: boolean;
}) {
  return (
    // The reserved 64px column. The nav inside it expands OVER the content
    // rather than pushing it: animating width in-flow reflowed the entire app —
    // sidebar, transcript and context panel all shifting 132px — every time the
    // pointer crossed the rail.
    //
    // CSS width, and deliberately NOT transitioned. `transition-none` is
    // load-bearing — without it this rail does not expand at all. The desktop
    // file carries the full investigation; the short version is that a
    // pseudo-class-driven width change on this element does not animate, and
    // taking the transition off is what makes 64 -> 196 work.
    //
    // group-hover for the pointer, focus-within for the keyboard: Tab moves
    // through the rail without ever generating a hover, and a hover-only
    // expansion would leave a keyboard user stepping through unlabelled icons.
    <div className="group relative z-30 w-16 shrink-0 h-full">
      <nav
        aria-label="Primary"
        className="absolute inset-y-0 left-0 w-16 flex flex-col overflow-hidden
                   border-r border-on-surface/[0.07] bg-[var(--nav-bg)]
                   transition-none group-hover:w-[196px] focus-within:w-[196px]">

      {/* The real brand mark: a 7px dot and PRIMNOX in Syne bold at 0.18em
          tracking. The dot never leaves, so it IS the collapsed mark; the
          wordmark slides out from behind it on expand, which is what makes the
          expanded state read as `.Primnox` — the dot leading the name rather
          than a separate glyph swapped in. */}
      <div className="group/mark h-14 shrink-0 flex items-center gap-3 px-[22px]"
        role="img" aria-label="Primnox">
        <span aria-hidden="true"
          className="w-[7px] h-[7px] rounded-full bg-on-surface shrink-0
                     transition-transform duration-200 group-hover/mark:scale-125" />
        <span aria-hidden="true"
          className="px-wordmark font-display font-bold text-[13px] uppercase
                     tracking-[0.18em] whitespace-nowrap">
          Primnox
        </span>
      </div>

      {/* Destinations only. "New chat" and "Incognito" are actions, not places,
          and live with the conversation list they act on. */}
      <ul role="list" className="flex-1 px-3 pt-2 space-y-1">
        {ITEMS.map(item => (
          <li key={item.id}>
            <RailButton icon={item.icon} label={item.label} hint={item.hint}
              active={section === item.id} current={section === item.id}
              onClick={() => onSection(item.id)} />
          </li>
        ))}
      </ul>

      <div className="shrink-0 px-3 pb-3 pt-2 space-y-3 border-t border-on-surface/[0.07]">
        <div className="flex items-center gap-2 px-1.5 pt-2">
          <ThemeCycle />
          <span className="px-label whitespace-nowrap">Theme</span>
        </div>
        <div className="flex items-center gap-2 px-1.5">
          <Circle size={6} aria-hidden="true"
            className={`shrink-0 fill-current ${connected ? 'text-primary' : 'text-error'}`} />
          <span className="px-label whitespace-nowrap">
            {connected ? (synced ? 'Live' : 'Syncing') : 'Offline'}
          </span>
        </div>
      </div>
      </nav>
    </div>
  );
}

function RailButton({
  icon: Icon, label, active, current, onClick, hint,
}: {
  icon: any; label: string;
  active?: boolean; current?: boolean; onClick: () => void; hint?: string;
}) {
  return (
    <button type="button"
      onClick={e => {
        onClick();
        // The rail expands on `focus-within` so Tab-ing through it shows the
        // labels a keyboard user needs. A mouse click ALSO focuses the button,
        // which the same rule reads identically, so a mouse user got the
        // keyboard affordance they never asked for: the rail stayed expanded,
        // overlapping whatever section they just navigated to. Blurring after a
        // pointer click leaves keyboard Tab navigation completely alone.
        e.currentTarget.blur();
      }}
      aria-label={label} title={hint ?? label}
      aria-current={current ? 'page' : undefined}
      className={`px-interactive w-full flex items-center gap-3 rounded-xl py-2.5 px-[11px]
        ${active
          ? 'bg-on-surface/[0.08] text-on-surface'
          : 'text-on-surface/55 hover:text-on-surface hover:bg-on-surface/[0.04]'}`}>
      <Icon size={16} className="shrink-0" aria-hidden="true" />
      {/* Always rendered and always opaque. The rail's own `overflow-hidden`
          is what hides these at 64px, which means there is exactly one thing
          controlling visibility instead of a width and an opacity that can
          disagree — and the label stays in the accessibility tree at every
          width regardless. */}
      <span className="px-rail-label text-[13px] whitespace-nowrap">{label}</span>
    </button>
  );
}
