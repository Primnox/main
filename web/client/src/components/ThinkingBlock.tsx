import { useState } from 'react';
import { BrainCircuit, ChevronRight } from 'lucide-react';
import { Collapsible } from '@base-ui-components/react/collapsible';

/* The model's reasoning, when the provider sends any — Anthropic's extended
 * thinking (opt-in in Settings → Provider, since it changes the request
 * itself) or a reasoning model's unprompted `reasoning_content`. Absent for
 * every other model, which is why this renders nothing at all rather than an
 * empty "Thinking" shell when `thinking` is blank — TurnBlock only mounts it
 * once there is something to show.
 *
 * Collapsed by default and real collapse state (Base UI's Collapsible, not a
 * CSS max-height trick), the same reasoning as PlanBlock staying always-open:
 * a plan is a few lines meant to be read; reasoning can run to several
 * paragraphs and is process, not the answer — worth having, not worth
 * defaulting to full height above every reply.
 */
export function ThinkingBlock({ thinking, live }: { thinking: string; live: boolean }) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}
      className="mb-3 rounded-xl border border-on-surface/[0.09] bg-on-surface/[0.02]">
      <Collapsible.Trigger
        className="px-interactive w-full flex items-center gap-2.5 px-3.5 py-3 text-left">
        <BrainCircuit size={13} className="shrink-0 text-on-surface/50" aria-hidden="true" />
        <span className="px-label flex-1">
          {live && !open ? 'Thinking…' : 'Thinking'}
        </span>
        <ChevronRight size={12} aria-hidden="true"
          className={`shrink-0 text-on-surface/50 transition-transform duration-150 ${open ? 'rotate-90' : ''}`} />
      </Collapsible.Trigger>
      {/* Base UI measures the panel and publishes the result as
          `--collapsible-panel-height`, but nothing was reading it, so this
          block snapped open while the artifact rows elsewhere in the same
          turn animated. Two collapsibles behaving differently in one view is
          the cohesion problem, not the missing 200ms.

          A transition and not a keyframe, so toggling it twice quickly
          retargets from the current height instead of restarting from zero.
          Reduced motion drops it to instant on its own: `height` is not on
          the allowlist in tailwind.css. */}
      <Collapsible.Panel
        className="overflow-hidden transition-[height] duration-200
                   ease-[cubic-bezier(0.23,1,0.32,1)]
                   h-[var(--collapsible-panel-height)]
                   data-[starting-style]:h-0 data-[ending-style]:h-0">
        <p className="px-3.5 pb-3 text-[12px] leading-5 text-on-surface/60 whitespace-pre-wrap">
          {thinking}
        </p>
      </Collapsible.Panel>
    </Collapsible.Root>
  );
}
