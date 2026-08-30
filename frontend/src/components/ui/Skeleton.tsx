/* A loading placeholder — not "empty," a promise that content is coming.
 *
 * Without this, every list in the app starts from an empty array and renders
 * its EmptyState on the very first frame, then swaps to real rows once the
 * fetch resolves. That reads as "there's nothing here" for a beat, then a
 * layout jump — the wrong message, however briefly. A skeleton says "this is
 * still loading" instead of "this is empty," which is the truth.
 *
 * `animate-pulse` is what actually signals "loading" rather than "just a
 * muted block" — a static bar and a genuinely empty placeholder look
 * identical, and this app already uses the same Tailwind utility for the
 * live-turn status dot (ContextRail's footer), so it costs nothing new.
 */
export function Skeleton({ className = '' }: { className?: string }) {
  return <span className={`block animate-pulse rounded bg-on-surface/[0.07] ${className}`} />;
}

/* One list row's worth of skeleton: a dot-shaped marker plus two lines of
 * varying width, the shape shared by every row-oriented list in this app
 * (conversations, memories, knowledge scopes, provider profiles). Built
 * once here instead of once per surface — `ModelProfiles.tsx` had its own
 * copy before this existed.
 */
export function RowSkeleton({ lines = 2 }: { lines?: 1 | 2 }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-on-surface/[0.07] px-4 py-3">
      <Skeleton className="h-1.5 w-1.5 shrink-0 rounded-full" />
      <span className="min-w-0 flex-1 space-y-1.5">
        <Skeleton className="h-3 w-32" />
        {lines === 2 && <Skeleton className="h-2.5 w-52 bg-on-surface/[0.05]" />}
      </span>
    </div>
  );
}

/* A stack of RowSkeletons, `aria-busy` so assistive tech knows this region
 * is mid-load rather than reporting an empty list. `count` should roughly
 * match how many rows a real load tends to produce — enough to read as "a
 * list is coming," not so many it overshoots into its own kind of lie.
 */
export function ListSkeleton({ count = 3, lines = 2 }: { count?: number; lines?: 1 | 2 }) {
  return (
    <div className="space-y-1.5" aria-busy="true">
      {Array.from({ length: count }, (_, i) => <RowSkeleton key={i} lines={lines} />)}
    </div>
  );
}
