import { useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { BENCH, UNKNOWN_TEXT } from './fixtures';
import { PrimitiveRenderer } from './PrimitiveRenderer';
import { decide, describeUnknown, type Level, type PrimitiveDescriptor } from './rule';

/* Unit 4's prototype.
 *
 * It is not a component gallery, and the difference is the point. Nothing here
 * is arranged by hand: every placement on this page came out of `decide()`,
 * and the bench prints the reason next to each one so a reader can check the
 * rule rather than admire the result.
 *
 * Four things it has to demonstrate, in order:
 *   1. the rule is total — every primitive in the brief gets a level;
 *   2. the rule is mechanical — the level moves when an INPUT moves, and not
 *      when the semantic type moves;
 *   3. the rule stops at `block` — panel and fullscreen are user acts;
 *   4. the rule is safe on a primitive it has never seen.
 */

const FLAGS = ['blocking', 'interact', 'evidence', 'handle', 'persists'] as const;
type Flag = (typeof FLAGS)[number];

function Section({ n, title, lede, children }: {
  n: string; title: string; lede: string; children: React.ReactNode;
}) {
  return (
    <section className="border-b border-on-surface/10 px-8 py-7">
      <div className="mb-4 max-w-3xl">
        <p className="px-label mb-1.5">
          <span className="tabular-nums text-on-surface/50">{n}</span> · {title}
        </p>
        <p className="text-[12.5px] leading-6 text-on-surface/60">{lede}</p>
      </div>
      {children}
    </section>
  );
}

/* ── 2. The bench ──────────────────────────────────────────────────────────
   Every primitive named in the brief, levelled. The columns that matter are
   the last two: the level, and the input that set it. Read down the DRIVER
   column and note that the answer is never "because it is a chart". */
function Bench() {
  const rows = useMemo(() => BENCH.map(p => ({ p, d: decide(p) })), []);
  return (
    <div className="overflow-x-auto custom-scrollbar">
      <table className="w-full border-collapse text-[11px]">
        <caption className="sr-only">
          Every response primitive, its measured inputs, and the level the rule gives it
        </caption>
        <thead>
          <tr>
            {['Primitive', 'Kind', 'Extent', ...FLAGS.map(f => f.slice(0, 4)), 'Level', 'Because'].map(h => (
              <th key={h} scope="col"
                className="whitespace-nowrap border-b border-on-surface/25 px-2 py-1.5 text-left
                           font-medium uppercase tracking-[0.08em] text-on-surface/70">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ p, d }) => (
            <tr key={p.id} className="hover:bg-on-surface/[0.03]">
              <td className="whitespace-nowrap border-b border-on-surface/[0.08] px-2 py-1 text-on-surface/85">{p.label}</td>
              <td className="whitespace-nowrap border-b border-on-surface/[0.08] px-2 py-1 font-mono text-on-surface/50">{p.kind}</td>
              <td className="whitespace-nowrap border-b border-on-surface/[0.08] px-2 py-1 tabular-nums text-on-surface/60">
                {p.extent.lines}{p.extent.cols ? `×${p.extent.cols}` : ''}
              </td>
              {FLAGS.map(f => (
                <td key={f} className="border-b border-on-surface/[0.08] px-2 py-1 text-center">
                  {p[f]
                    ? <span className="text-primary">Y</span>
                    : <span className="text-on-surface/50">·</span>}
                </td>
              ))}
              <td className="whitespace-nowrap border-b border-on-surface/[0.08] px-2 py-1">
                <span className={d.level === 'inline' ? 'text-on-surface/60' : 'text-on-surface'}>{d.level}</span>
              </td>
              <td className="border-b border-on-surface/[0.08] px-2 py-1 text-on-surface/60">
                <span className="font-mono text-on-surface/85">{d.driver.input}</span> — {d.driver.why}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── 3. The bench, live ────────────────────────────────────────────────────
   Flip an input, watch the level move. Flip the KIND and nothing moves,
   because `decide()` does not read it. This is the falsifiable part: if the
   rule were aesthetic rather than mechanical, this panel could not exist. */
function LiveBench() {
  const [id, setId] = useState('p-chart');
  const [overrides, setOverrides] = useState<Partial<Record<Flag, boolean>>>({});
  const [lines, setLines] = useState<number | null>(null);
  const [promoted, setPromoted] = useState<Level | null>(null);

  const base = BENCH.find(b => b.id === id) ?? BENCH[0];
  const p: PrimitiveDescriptor = {
    ...base,
    ...overrides,
    extent: { ...base.extent, lines: lines ?? base.extent.lines },
  };
  const d = decide(p);

  const pick = (nextId: string) => {
    setId(nextId); setOverrides({}); setLines(null); setPromoted(null);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[19rem_minmax(0,1fr)]">
      <div className="space-y-4">
        <div>
          <label htmlFor="rp-pick" className="px-label mb-1.5 block">Primitive</label>
          <select id="rp-pick" value={id} onChange={e => pick(e.target.value)}
            className="w-full border border-on-surface/20 bg-bg px-2 py-1.5 text-[12px] text-on-surface
                       outline-none focus-visible:ring-2 focus-visible:ring-primary/60">
            {BENCH.map(b => <option key={b.id} value={b.id}>{b.label}</option>)}
          </select>
        </div>

        <fieldset className="border border-on-surface/15 px-3 py-2.5">
          <legend className="px-label px-1">Inputs</legend>
          {FLAGS.map(f => (
            <label key={f} className="flex cursor-pointer items-center gap-2 py-1 text-[12px] text-on-surface/80">
              <input type="checkbox" checked={!!p[f]}
                onChange={e => setOverrides(o => ({ ...o, [f]: e.target.checked }))}
                className="accent-primary" />
              <span className="font-mono">{f}</span>
            </label>
          ))}
          <label htmlFor="rp-lines" className="mt-2 block text-[12px] text-on-surface/80">
            <span className="font-mono">extent.lines</span>
            <span className="ml-2 tabular-nums text-on-surface/60">{p.extent.lines}</span>
          </label>
          <input id="rp-lines" type="range" min={1} max={40} value={p.extent.lines}
            onChange={e => setLines(Number(e.target.value))}
            className="mt-1 w-full accent-primary" />
        </fieldset>

        {/* The explanation, not just the verdict. Every floor that was raised,
            so a disagreement lands on a specific line rather than on "it
            looks wrong". */}
        <div className="border border-on-surface/15 px-3 py-2.5">
          <p className="px-label mb-2">Floors raised</p>
          <ul className="space-y-1.5">
            {d.floors.map(f => (
              <li key={f.input} className="text-[11px] leading-4">
                <span className={f === d.driver ? 'text-primary' : 'text-on-surface/50'}>
                  {f === d.driver ? '▸' : '·'} <span className="font-mono">{f.input}</span> → {f.level}
                </span>
                <span className="block pl-3 text-on-surface/50">{f.why}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2.5 border-t border-on-surface/10 pt-2 text-[11px] text-on-surface/60">
            level <span className="text-on-surface">{d.level}</span>
            {' · '}offers {d.offers.length ? d.offers.join(' / ') : <span className="text-on-surface/50">nothing</span>}
          </p>
        </div>
      </div>

      <div className="min-w-0">
        <p className="px-label mb-2">Rendered at the level the rule chose</p>
        {/* max-w-prose, because a response primitive lives inside a reply and
            a reply has a measure. Rendering it full-bleed here would flatter
            every block and prove nothing. */}
        <div className="max-w-prose border border-dashed border-on-surface/15 px-4 py-3">
          <PrimitiveRenderer p={p} onPromote={setPromoted} />
        </div>

        {promoted && (
          <div className="mt-4 border border-primary/40 px-4 py-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="px-label flex-1 text-primary">
                Promoted to {promoted} — by the user, never by the rule
              </span>
              <button type="button" onClick={() => setPromoted(null)} aria-label="Close the promoted surface"
                className="p-1 text-on-surface/55 outline-none hover:text-on-surface
                           focus-visible:ring-2 focus-visible:ring-primary/60">
                <X size={12} aria-hidden="true" />
              </button>
            </div>
            <p className="text-[11.5px] leading-5 text-on-surface/60">
              {promoted === 'panel'
                ? 'Canvas.tsx variant="panel" — beside the conversation, surviving the next turn. Opened because this payload has a handle, not because it is large.'
                : 'AssetViewer.tsx — the viewport, dismissed on Escape. Same trigger, different commitment.'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── 4. Totality ───────────────────────────────────────────────────────────
   The rule has to place a primitive that does not exist yet, or it is a
   lookup table with extra steps. */
function Unknown() {
  const p = describeUnknown('p-unknown', 'plan.projection.v3', UNKNOWN_TEXT);
  const d = decide(p);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="max-w-prose border border-dashed border-on-surface/15 px-4 py-3">
        <PrimitiveRenderer p={p} />
      </div>
      <p className="max-w-md text-[12px] leading-6 text-on-surface/60">
        No renderer knows this kind. It still gets a level —{' '}
        <span className="font-mono text-on-surface/85">{d.level}</span>, because{' '}
        {d.driver.why} — and falls through to bounded, scrollable, inert text.
        <span className="mt-2 block">
          A frontend engineer adding <span className="font-mono">plan.projection.v3</span> for real
          writes one <span className="font-mono">case</span> in <span className="font-mono">Payload</span>.
          They do not make a layout decision, because the layout decision was already made from the
          descriptor. That is the difference between a rule and a catalogue.
        </span>
      </p>
    </div>
  );
}

export function ResponsePrimitivesDemo() {
  return (
    <div className="min-h-full bg-bg text-on-surface">
      <header className="border-b border-on-surface/15 px-8 py-6">
        <h1 className="font-display text-[15px] font-bold uppercase tracking-[0.18em]">
          Unit 04 · Response primitives
        </h1>
        <p className="mt-2 max-w-3xl text-[12.5px] leading-6 text-on-surface/60">
          The deliverable is a rule, not a component set. Five observable inputs decide whether a
          payload renders inline, in a block, or gets a door to a wider surface. Semantic type is
          not one of them.
        </p>
      </header>

      <Section n="01" title="The rule"
        lede="Each input independently imposes a floor. The level is the highest floor. Nothing raises it past a block — panel and fullscreen are things the user does.">
        <div className="max-w-3xl border border-on-surface/15">
          {[
            ['extent', '≤ 3 lines and no columns', 'inline', 'anything more', 'block'],
            ['interact', 'reading it needs no gesture', '—', 'it needs a gesture', 'block'],
            ['evidence', 'it states', '—', 'it substantiates', 'block, collapsed'],
            ['blocking', 'the turn continues', '—', 'the turn is parked', 'block, pinned open'],
            ['handle', 'nothing to take away', '—', 'editable, downloadable or cited', 'block + a door'],
          ].map(([input, lo, loL, hi, hiL]) => (
            <div key={input} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 border-b border-on-surface/10 px-3 py-2 last:border-b-0">
              <span className="font-mono text-[11.5px] text-primary">{input}</span>
              <span className="text-[11.5px] leading-5 text-on-surface/70">
                {loL !== '—' && <>{lo} → <span className="text-on-surface">{loL}</span>; </>}
                {hi} → <span className="text-on-surface">{hiL}</span>
              </span>
            </div>
          ))}
        </div>
        <p className="mt-3 max-w-3xl text-[12px] leading-6 text-on-surface/60">
          The door is offered on <span className="font-mono">handle</span> or{' '}
          <span className="font-mono">persists</span> — never on size. ChatGPT Canvas opens above
          ten lines and Claude Artifacts above fifteen because neither can observe reuse-intent.
          Primnox can: <span className="font-mono">workspace.created</span> and{' '}
          <span className="font-mono">asset.ready</span> are separate events from{' '}
          <span className="font-mono">token</span>.
        </p>
      </Section>

      <Section n="02" title="Every primitive in the brief, levelled"
        lede="Read the BECAUSE column. The reason is never the kind — a chart and a checklist of the same extent and handling land in the same place.">
        <Bench />
      </Section>

      <Section n="03" title="Mechanical, not aesthetic"
        lede="Flip an input and the level moves. Change the primitive without changing its inputs and it does not. The rendering below is produced by one component for all of them.">
        <LiveBench />
      </Section>

      <Section n="04" title="A primitive nobody has thought of yet"
        lede="The test of a rule is what it does with something it has never seen."
      >
        <Unknown />
      </Section>
    </div>
  );
}
