import {
  Brain, Circle, MessageSquare, Share2, SlidersHorizontal,
} from 'lucide-react';
import { ThemeCycle } from './ThemePicker';

export type Section = 'chat' | 'knowledge' | 'memory' | 'settings';

const ITEMS: { id: Section; label: string; icon: any; hint: string }[] = [
  { id: 'chat', label: 'Chats', icon: MessageSquare, hint: 'Conversations' },
  { id: 'knowledge', label: 'Knowledge', icon: Share2, hint: 'The indexed corpus and what you have saved' },
  { id: 'memory', label: 'Memory', icon: Brain, hint: 'What Primnox knows about you' },
  { id: 'settings', label: 'Settings', icon: SlidersHorizontal, hint: 'Theme, provider, tuning' },
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
    // load-bearing — without it this rail does not expand at all.
    //
    // What is established: Motion's `animate={{ width }}` never ran, because
    // main.tsx sets MotionConfig reducedMotion="user" and this machine has
    // Reduce Motion on — so the rail sat at 64px forever and every label was
    // unreachable. Moving to a CSS width did not fix it on its own; the
    // `:focus-within` rule matched, won on specificity, and the element still
    // computed to 64px until the transition was taken off it. With
    // `transition-none` it goes 64 -> 196 on focus and back on blur, verified.
    //
    // What is NOT established is why. A plain control element's width
    // transitions fine under the same reduced-motion rule, so "0.01ms breaks
    // width transitions" is not the explanation — that was tested and
    // disproved. Something about a pseudo-class-driven width change on this
    // element specifically. Leaving the fix and the honest note rather than a
    // confident story, so nobody removes this class expecting nothing to break.
    //
    // Animating width is an anti-pattern anyway: it lays out every frame.
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

      {/* Wordmark: `P.` at 64px, `.Primnox` once there is room.
          Two spans swapped by the same group state that drives the width, not a
          clipped single string — the mark is not a truncation of the name, the
          dot moves from the end to the front. One aria-label on the wrapper so
          a screen reader hears the product name once, never "P dot" or both
          variants read in sequence. */}
      {/* The real brand mark, not an approximation of one.
          V1's Layout.tsx documents it: "mirrors the site's nav-logo: a pulsing
          dot and wide-tracked uppercase wordmark, no boxed icon" — a 7px dot
          and PRIMNOX in Syne bold at 0.18em tracking. V2 already carried it;
          it was replaced here with invented "P." text and is now restored.

          The dot never leaves, so it IS the collapsed mark; the wordmark slides
          out from behind it on expand, which is what makes the expanded state
          read as `.Primnox` — the dot leading the name rather than a separate
          glyph swapped in. */}
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

      {/* Destinations only.
          "New chat" and "Incognito" used to sit above these, and they do not
          belong: they are actions, not places. A rail item is somewhere you
          ARE — it takes aria-current="page" and stays lit while you are there —
          whereas pressing New chat performs something and leaves you in Chats,
          so two of the six icons could never light up and the column meant two
          different things at once. They now live with the conversation list
          they act on. */}
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
    <button type="button" onClick={onClick}
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
          width regardless.
          A fade was tried and removed: with `transition-opacity` the labels
          stayed at opacity 0 even once the rail had expanded — the same shape
          of failure as the width, and fixed the same way, by not transitioning
          it. */}
      <span className="px-rail-label text-[13px] whitespace-nowrap">{label}</span>
    </button>
  );
}
