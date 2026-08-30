import { useEffect, useState } from 'react';
import { api, type Fact } from '../lib/crs';
import { ListSkeleton } from './ui';

/* What Primnox has worked out, and where each piece came from.
 *
 * Distinct from the memories above it on purpose. A memory is something you
 * told it to keep. A fact is something it recorded on its own — from a file,
 * a tool, a repository, or its own inference — and the difference between
 * those last two is the entire reason this surface exists.
 *
 * v2/world_model.py has stored source, origin and confidence on every fact
 * since it was written, and no interface ever displayed any of it. So a line
 * the assistant stated read identically whether the user had said it, a
 * lockfile had proved it, or a model had guessed it. Showing the text without
 * the provenance is what makes a guess look like a fact.
 *
 * `origin` is the load-bearing field and gets the most prominent treatment:
 * three coarse values, deliberately, because a confidence percentage next to
 * an unqualified guess is false precision.
 */

const ORIGIN_COPY: Record<Fact['origin'], string> = {
  stated: 'you said this',
  observed: 'seen directly',
  inferred: 'worked out',
};

/* Inference is marked, the other two are not. Colour-coding all three would
   make the list a traffic light and bury the one distinction that matters;
   an inference is the only one a reader should hesitate over. */
const ORIGIN_TONE: Record<Fact['origin'], string> = {
  stated: 'text-on-surface/55',
  observed: 'text-on-surface/55',
  inferred: 'text-warn',
};

export function FactList({ limit = 40 }: { limit?: number }) {
  const [facts, setFacts] = useState<Fact[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    api.facts({ limit })
      .then(d => { if (live) setFacts(d.facts ?? []); })
      .catch(() => { if (live) { setFacts([]); setFailed(true); } });
    return () => { live = false; };
  }, [limit]);

  // Already distinguished null-vs-empty before this file used a skeleton —
  // it just rendered nothing for the gap, which read as the panel doing
  // nothing rather than as loading.
  if (facts === null) return <ListSkeleton count={3} lines={1} />;

  if (failed) {
    return (
      <p className="text-[12px] text-on-surface/50">
        Could not read what Primnox has observed.
      </p>
    );
  }

  if (facts.length === 0) {
    return (
      <p className="text-[12px] text-on-surface/50">
        Nothing observed yet. These appear as Primnox reads files and runs
        tools — you do not add them by hand.
      </p>
    );
  }

  return (
    <ul role="list" className="space-y-2">
      {facts.map(fact => <FactRow key={fact.id} fact={fact} />)}
    </ul>
  );
}

function FactRow({ fact }: { fact: Fact }) {
  const [open, setOpen] = useState(false);

  return (
    <li className="border border-on-surface/[0.10] px-3 py-2">
      <p className="text-[12px] leading-snug text-on-surface/85">{fact.text}</p>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
        {/* Word, not a coloured dot. The distinction between what you said and
            what a model concluded has to survive greyscale. */}
        <span className={ORIGIN_TONE[fact.origin]}>{ORIGIN_COPY[fact.origin]}</span>

        <span className="text-on-surface/45">via {fact.source}</span>

        {fact.source_ref && (
          <span className="max-w-56 truncate font-mono text-on-surface/45"
                title={fact.source_ref}>
            {fact.source_ref}
          </span>
        )}

        {/* Only for inferences. A confidence number on something the user
            stated outright invites the reader to doubt their own sentence. */}
        {fact.origin === 'inferred' && (
          <span className="tabular-nums text-on-surface/45">
            {Math.round(fact.confidence * 100)}% sure
          </span>
        )}

        {fact.disputed === 1 && <span className="text-warn">disputed</span>}
        {fact.stale === 1 && <span className="text-on-surface/45">stale</span>}

        {fact.supersedes && (
          <button
            type="button"
            onClick={() => setOpen(o => !o)}
            aria-expanded={open}
            className="px-interactive text-on-surface/45 hover:text-on-surface/80"
          >
            replaced something
          </button>
        )}
      </div>

      {open && fact.supersedes && (
        <p className="mt-1.5 border-t border-on-surface/10 pt-1.5 font-mono text-[11px] text-on-surface/45">
          supersedes {fact.supersedes}
        </p>
      )}
    </li>
  );
}
