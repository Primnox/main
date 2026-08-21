import { useCallback } from 'react';
import { TERMINAL, type Turn } from '../lib/crs';

/* One leg of the reckoning track.
 *
 * The rail is not a line drawn beside a list of messages. It is the first
 * column of the grid every turn is laid out on, so the track cannot drift out
 * of alignment with the thing it is tracking, and nothing can float across it.
 * The frame is the grid.
 *
 * State is carried in FORM first and hue second, always both, never hue alone:
 *
 *   fix        solid mark, full-weight rule      a confirmed position
 *   reckoning  dashed rule, hollow mark          carried forward, unconfirmed
 *   refusal    struck mark                       the runtime declined
 *   stale      half-height rule                  cancelled, went nowhere
 *
 * That is a WCAG 1.4.1 obligation (PRODUCT.md records AA), but it is also just
 * how a chart is read: you can photocopy one and it still tells you where the
 * ship was.
 */

type TrackState = 'fix' | 'reckoning' | 'refusal' | 'stale';

function stateOf(turn: Turn): TrackState {
  if (turn.status === 'failed') return 'refusal';
  if (turn.status === 'cancelled') return 'stale';
  if (TERMINAL.includes(turn.status)) return 'fix';
  return 'reckoning';
}

/* The turn id carries its own creation time (UUIDv7 prefix on the backend),
   but the shell never needs to decode it: the ordinal IS the useful
   coordinate here. A navigator numbers the legs. */
function ordinalLabel(index: number): string {
  return String(index + 1).padStart(2, '0');
}

const RULE_BY_STATE: Record<TrackState, string> = {
  fix: 'border-l border-dr-track',
  reckoning: 'border-l border-dashed border-dr-reckoning/70',
  refusal: 'border-l border-dr-refusal/50',
  stale: 'border-l border-dr-track/40',
};

const DESCRIPTION_BY_STATE: Record<TrackState, string> = {
  fix: 'confirmed',
  reckoning: 'in progress',
  refusal: 'failed',
  stale: 'cancelled',
};

export function TrackRow({
  turn,
  index,
  children,
}: {
  turn: Turn;
  index: number;
  children: React.ReactNode;
}) {
  const state = stateOf(turn);
  const open = state === 'reckoning';

  /* Returning to an earlier leg is a scroll, never a mode: nothing is
     destroyed and nothing is hidden, so there is no state to restore. */
  const goTo = useCallback(() => {
    document.getElementById(`leg-${turn.id}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [turn.id]);

  return (
    <div
      id={`leg-${turn.id}`}
      className="grid grid-cols-[var(--dr-rail-w)_1fr] items-start
                 md:grid-cols-[var(--dr-rail-w-wide)_1fr]"
    >
      {/* The rail cell. It draws its own segment of the continuous track, so
          the track is assembled from the legs rather than painted over them. */}
      <div className={`relative self-stretch pt-[0.6rem] ${RULE_BY_STATE[state]}`}>
        <button
          type="button"
          onClick={goTo}
          title={`Leg ${ordinalLabel(index)}, ${DESCRIPTION_BY_STATE[state]}`}
          className="group absolute -left-px top-[0.6rem] flex items-center gap-2
                     rounded-sm pl-0 pr-1 outline-none
                     focus-visible:ring-2 focus-visible:ring-dr-fix/60"
        >
          {/* The mark. Form first: solid, hollow, or struck. */}
          <span
            aria-hidden="true"
            className={[
              'block h-[7px] w-[7px] shrink-0 -translate-x-1/2 rotate-45',
              state === 'fix' && 'bg-dr-tick group-hover:bg-dr-tick-open',
              state === 'reckoning' && 'border border-dr-reckoning bg-transparent',
              state === 'refusal' && 'bg-dr-refusal',
              state === 'stale' && 'bg-dr-track',
            ].filter(Boolean).join(' ')}
          />
          <span
            className={[
              'dr-measure text-[10px] leading-none transition-colors duration-150',
              open ? 'text-dr-reckoning' : 'text-on-surface/65 group-hover:text-on-surface/90',
              state === 'refusal' && 'line-through decoration-dr-refusal',
            ].filter(Boolean).join(' ')}
          >
            {ordinalLabel(index)}
          </span>
          <span className="sr-only">
            Leg {ordinalLabel(index)}, {DESCRIPTION_BY_STATE[state]}. Jump to it.
          </span>
        </button>
      </div>

      {/* The plate. A lighter region of the same table, not a card: no radius
          jump, no shadow, no border boxing it in on four sides. */}
      <div className="min-w-0 pb-10 pl-5 pr-4 pt-2 md:pl-7">
        <div className="max-w-plate">{children}</div>
      </div>
    </div>
  );
}
