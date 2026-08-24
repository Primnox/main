import { Lightbulb } from 'lucide-react';

export function PlanBlock({ plan }: { plan: string }) {
  return (
    <div className="mb-3 flex gap-2.5 rounded-xl border border-on-surface/[0.09] bg-on-surface/[0.02] px-3.5 py-3">
      <Lightbulb size={13} className="shrink-0 mt-0.5 text-on-surface/50" />
      <div className="min-w-0">
        <p className="px-label mb-1">Plan</p>
        <p className="text-[12px] leading-5 text-on-surface/65 whitespace-pre-wrap">{plan}</p>
      </div>
    </div>
  );
}

/* One sandbox run: what it was allowed to do, what it printed, what it changed. */
