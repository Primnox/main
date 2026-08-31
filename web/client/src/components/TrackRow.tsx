import { TERMINAL, type Turn } from '../lib/crs';

/* One leg of the reckoning track.
 *
 * The rail is not a line drawn beside a list of messages. It is the first
 * column of the grid every turn is laid out on, so the track cannot drift out
 * of alignment with the thing it is tracking, and nothing can float across it.
 * The frame is the grid.
 *
 * Each tick is also the control that sets a FIX - a position you are willing
 * to call known-good. That is deliberate: the rail was already made of
 * buttons, so declaring a fix costs no new chrome and no new place to look.
 * Everything after the fix is dead reckoning, and the rule says so by getting
 * heavier the further it runs unconfirmed.
 *
 * State is carried in FORM first and hue second, always both, never hue alone:
 *
 *   fix        filled mark, solid rule           the confirmed position
 *   confirmed  solid mark, solid rule            before the fix, settled
 *   reckoning  hollow mark, dashed rule          carried forward, unconfirmed
 *   refusal    struck label                      the runtime declined
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

const DESCRIPTION_BY_STATE: Record<TrackState, string> = {
  fix: 'confirmed',
  reckoning: 'in progress',
  refusal: 'failed',
  stale: 'cancelled',
};

export function TrackRow({
  turn,
  index,
  isFix,
  drift,
  onFix,
  children,
}: {
  turn: Turn;
  index: number;
  /** This leg is the current fix. */
  isFix: boolean;
  /** How many legs have run since the fix. 0 means this leg is at or before it. */
  drift: number;
  onFix: (turnId: string) => void;
  children: React.ReactNode;
}) {
  const state = stateOf(turn);
  const confirmed = drift === 0;

  /* The rule earns weight with distance from the last fix. One leg out is a
     hairline; several legs out is heavier and more saturated, so accumulated
     uncertainty is something you watch build rather than a number you read. */
  const rule = confirmed
    ? { borderLeft: '1px solid var(--dr-track)' }
    : {
        borderLeft: `${drift > 1 ? 2 : 1}px dashed color-mix(in srgb, var(--dr-reckoning) ${
          Math.min(30 + drift * 22, 85)}%, transparent)`,
      };

  return (
    <div
      id={`leg-${turn.id}`}
      className="grid grid-cols-[var(--dr-rail-w)_1fr] items-start
                 md:grid-cols-[var(--dr-rail-w-wide)_1fr]"
    >
      {/* The rail cell. It draws its own segment of the continuous track, so
          the track is assembled from the legs rather than painted over them. */}
      <div className="relative self-stretch pt-[0.6rem]" style={rule}>
        <button
          type="button"
          onClick={() => onFix(turn.id)}
          aria-pressed={isFix}
          title={isFix
            ? `Turn ${ordinalLabel(index)} is your checkpoint — everything below is measured as drift from here`
            : `Mark turn ${ordinalLabel(index)} as your checkpoint (a "fix") — a known-good point to measure from`}
          className="group absolute -left-px top-[0.6rem] flex items-center gap-2
                     rounded-sm pl-0 pr-1 outline-none
                     focus-visible:ring-2 focus-visible:ring-dr-fix/60"
        >
          {/* The mark. Form first: filled, solid, hollow, or struck. */}
          <span
            aria-hidden="true"
            className={[
              'block h-[7px] w-[7px] shrink-0 -translate-x-1/2 rotate-45',
              'transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]',
              isFix && 'scale-[1.45] bg-dr-fix',
              !isFix && confirmed && 'bg-dr-tick group-hover:bg-dr-tick-open',
              !isFix && !confirmed && state === 'refusal' && 'bg-dr-refusal',
              !isFix && !confirmed && state !== 'refusal' && 'border border-dr-reckoning bg-transparent',
            ].filter(Boolean).join(' ')}
          />
          <span
            className={[
              'dr-measure text-[10px] leading-none transition-colors duration-150',
              isFix ? 'text-dr-fix'
                : confirmed ? 'text-on-surface/65 group-hover:text-on-surface/90'
                : 'text-dr-reckoning',
              state === 'refusal' && 'line-through decoration-dr-refusal',
            ].filter(Boolean).join(' ')}
          >
            {ordinalLabel(index)}
          </span>
          {isFix && (
            <span className="dr-measure text-[10px] leading-none tracking-[0.12em] text-dr-fix">
              FIX
            </span>
          )}
          <span className="sr-only">
            Turn {ordinalLabel(index)}, {DESCRIPTION_BY_STATE[state]}.
            {isFix
              ? ' This is your confirmed checkpoint.'
              : ` ${drift > 0 ? `${drift} turn${drift > 1 ? 's' : ''} since your last checkpoint. ` : ''}Mark this as a checkpoint (a "fix") to reset that count.`}
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
