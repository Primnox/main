import { useState } from 'react';
import { ShieldCheck, ChevronRight } from 'lucide-react';
import { Collapsible } from '@base-ui-components/react/collapsible';
import type { ScrubItem } from '../lib/crs';

/* What the Privacy Mirror swapped out before this turn left the device.
 *
 * The runtime has always built this map — `ScrubSession.events`, emitted as
 * `privacy.scrub` — but between V1 and V2 nothing rendered it, so the only
 * privacy signal left in the UI was a single Scrubbed/Unscrubbed tile in
 * Mission Control. That answers "did it run", which is the less useful of the
 * two questions: a scrubber you cannot audit is one you have to take on faith,
 * and the whole claim of this product is that you do not have to.
 *
 * So: the count is always visible, the reveal is one press away. Collapsed by
 * default for the same reason ThinkingBlock is — this is evidence, not the
 * answer — and because the panel contains the real values, which is exactly
 * what someone reading over a shoulder should not get for free.
 *
 * Only mounted when something was actually replaced. "Nothing matched" and
 * "the mirror was off" are different statements and neither belongs here; the
 * composer badge already says which provider is in use and whether it is cloud.
 */
export function PrivacyMirrorBlock({ items }: { items: ScrubItem[] }) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}
      className="mb-3 rounded-xl border border-on-surface/[0.09] bg-on-surface/[0.02]">
      <Collapsible.Trigger
        className="px-interactive w-full flex items-center gap-2.5 px-3.5 py-3 text-left">
        <ShieldCheck size={13} className="shrink-0 text-on-surface/50" aria-hidden="true" />
        <span className="px-label flex-1">
          Privacy Mirror · {items.length} scrubbed
        </span>
        <ChevronRight size={12} aria-hidden="true"
          className={`shrink-0 text-on-surface/50 transition-transform duration-150 ${open ? 'rotate-90' : ''}`} />
      </Collapsible.Trigger>
      {/* Same height transition as ThinkingBlock, for the same reason: two
          collapsibles in one turn animating differently is the thing that
          reads as broken. */}
      <Collapsible.Panel
        className="overflow-hidden transition-[height] duration-200
                   ease-[cubic-bezier(0.23,1,0.32,1)]
                   h-[var(--collapsible-panel-height)]
                   data-[starting-style]:h-0 data-[ending-style]:h-0">
        <div className="px-3.5 pb-3">
          <p className="text-[11px] leading-4 text-on-surface/45 mb-2.5">
            Stayed on this device — the model saw the placeholder on the right.
          </p>
          <ul className="flex flex-col gap-1.5">
            {items.map((it, i) => (
              <li key={`${it.placeholder}-${i}`}
                className="flex items-baseline gap-2 text-[12px] leading-5">
                <span className="px-label shrink-0 text-on-surface/40 w-16 truncate"
                  title={it.label}>{it.label}</span>
                <span className="min-w-0 flex-1 truncate text-on-surface/80"
                  title={it.original}>{it.original}</span>
                <span aria-hidden="true" className="shrink-0 text-on-surface/30">→</span>
                <span className="shrink-0 font-mono text-[11px] text-primary/70">
                  {it.placeholder}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </Collapsible.Panel>
    </Collapsible.Root>
  );
}
