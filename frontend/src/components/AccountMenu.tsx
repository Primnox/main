import { useRef, useState } from 'react';
import { Circle, Share2, SlidersHorizontal } from 'lucide-react';
import { RowMenu } from './RowMenu';
import { MenuItem } from './MenuItem';
import { ThemeCycle } from './ThemePicker';

/* The account-style entry point a lot of chat apps anchor at the foot of
 * their one sidebar. Primnox had the same destinations — Knowledge,
 * Settings, theme, connection status — spread across a persistent 64px
 * icon rail instead. Folded here into a single trigger + popup so the
 * conversation sidebar is the app's only permanent navigation surface.
 *
 * Primnox has no login, so there is no real account behind this — it is
 * still a stable anchor for "the app, and how it's doing right now",
 * which is what the connection dot already said in the rail's footer.
 */
export function AccountMenu({
  connected, synced, onKnowledge, onSettings,
}: {
  connected: boolean;
  synced: boolean;
  onKnowledge: () => void;
  onSettings: () => void;
}) {
  const btnRef = useRef<HTMLButtonElement>(null);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);

  const open = () => setAnchor(btnRef.current!.getBoundingClientRect());
  const close = () => setAnchor(null);

  return (
    // Sticky, not just last-in-flow: ContextSidebar wraps its whole
    // scrollable body in one container, and this row sitting after a
    // conversation list of any real length meant it scrolled away with the
    // rest instead of staying anchored the way an account row should.
    <div className="sticky bottom-0 shrink-0 border-t border-on-surface/[0.07]
                    bg-[var(--nav-bg)] px-2 py-2">
      <button ref={btnRef} type="button" onClick={open}
        aria-haspopup="menu" aria-expanded={anchor !== null}
        className="px-interactive flex w-full items-center gap-2.5 rounded-lg px-2 py-2
                   text-left hover:bg-on-surface/[0.06]">
        <span aria-hidden="true"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full
                     bg-on-surface/[0.10] text-[11px] font-semibold uppercase text-on-surface/70">
          P
        </span>
        <span className="min-w-0 flex-1 truncate text-[13px] text-on-surface/85">Primnox</span>
        <Circle size={7} aria-hidden="true"
          className={`shrink-0 fill-current ${connected ? 'text-primary' : 'text-error'}`} />
      </button>

      {anchor && (
        <RowMenu anchor={anchor} onClose={close}>
          {import.meta.env.DEV && (
            // Same DEV gate AppRail used: the raw graph viewer answers "is
            // indexing working", a question for whoever is building this,
            // not for someone using it to chat.
            <MenuItem icon={<Share2 size={13} />} onClick={() => { onKnowledge(); close(); }}>
              Knowledge
            </MenuItem>
          )}
          <MenuItem icon={<SlidersHorizontal size={13} />} onClick={() => { onSettings(); close(); }}>
            Settings
          </MenuItem>
          <div className="my-1 h-px bg-on-surface/[0.08]" />
          <div className="flex items-center gap-2.5 px-3 py-1.5">
            <ThemeCycle />
            <span className="text-[12px] text-on-surface/60">Theme</span>
          </div>
          <div className="flex items-center gap-2.5 px-3 py-1.5">
            <Circle size={7} aria-hidden="true"
              className={`shrink-0 fill-current ${connected ? 'text-primary' : 'text-error'}`} />
            <span className="text-[12px] text-on-surface/60">
              {connected ? (synced ? 'Live' : 'Syncing') : 'Offline'}
            </span>
          </div>
        </RowMenu>
      )}
    </div>
  );
}
