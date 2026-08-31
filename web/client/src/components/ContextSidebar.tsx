import { PanelLeftClose, X } from 'lucide-react';
import type { ReactNode } from 'react';

/* The second column: 280px of whatever the active section needs.
 *
 * One sidebar rather than one per section. Four sections each carrying their
 * own would be four near-identical scroll containers, four headers to keep
 * consistent, and four places to fix a bug — and the user would see the whole
 * column reflow on every section change instead of just its contents.
 *
 * `open` governs it at EVERY width, with two presentations: below `md` it is a
 * drawer over the transcript with a scrim, at `md` and up it is an inline
 * column. One piece of state, so "is the conversation list showing" has a
 * single answer rather than one per breakpoint.
 *
 * The collapse control is here; the control that brings it BACK is the rail's
 * Chats button, which is pinned and always visible. V1 hit exactly this and
 * left a note: its collapse toggle sat at the foot of the rail, fell below the
 * fold on a short window, and collapsing the sidebar could leave no way to
 * restore it. A way back that can scroll out of reach is not a way back.
 */
export function ContextSidebar({
  title, actions, open, onClose, children,
}: {
  title: string;
  actions?: ReactNode;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <>
      {/* Scrim, narrow widths only — there the drawer overlays the transcript,
          and a tap outside is how anyone expects to dismiss it. Inline at md+,
          where nothing is covered and a scrim would be wrong. */}
      {open && (
        <button type="button" aria-label={`Close ${title.toLowerCase()}`} onClick={onClose}
          className="md:hidden fixed inset-0 z-30 bg-[var(--scrim)]" />
      )}

      <aside aria-label={title}
        className={`w-[280px] max-w-[calc(100vw-4rem)] shrink-0 flex-col
                    border-r border-on-surface/[0.07] bg-[var(--nav-bg)]
                    ${open
                      ? 'flex fixed inset-y-0 left-16 z-40 shadow-2xl ' +
                        'md:relative md:inset-y-auto md:left-auto md:z-auto md:shadow-none'
                      : 'hidden'}`}>
        <div className="h-14 shrink-0 flex items-center gap-2 px-4 border-b border-on-surface/[0.07]">
          <h2 className="px-label truncate">{title}</h2>
          <div className="ml-auto flex items-center gap-1">
            {actions}
            <button type="button" onClick={onClose}
              aria-label={`Hide ${title.toLowerCase()}`}
              aria-expanded={open}
              title="Hide — bring it back from the rail"
              className="px-interactive p-1.5 rounded-lg text-on-surface/50
                         hover:text-on-surface hover:bg-on-surface/[0.05]">
              {/* A chevron pointing into the rail at desktop widths, an X in the
                  drawer — the same action, but "collapse toward there" and
                  "dismiss this overlay" are different gestures to a reader. */}
              <PanelLeftClose size={14} aria-hidden="true" className="hidden md:block" />
              <X size={15} aria-hidden="true" className="md:hidden" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {children}
        </div>
      </aside>
    </>
  );
}
