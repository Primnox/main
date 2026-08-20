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
        <BrainCircuit size={13} className="shrink-0 text-on-surface/40" aria-hidden="true" />
        <span className="px-label flex-1">
          {live && !open ? 'Thinking…' : 'Thinking'}
        </span>
        <ChevronRight size={12} aria-hidden="true"
          className={`shrink-0 text-on-surface/35 transition-transform duration-150 ${open ? 'rotate-90' : ''}`} />
      </Collapsible.Trigger>
      <Collapsible.Panel className="overflow-hidden">
        <p className="px-3.5 pb-3 text-[12px] leading-5 text-on-surface/60 whitespace-pre-wrap">
          {thinking}
        </p>
      </Collapsible.Panel>
    </Collapsible.Root>
  );
}
