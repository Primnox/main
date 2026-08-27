import { Fragment, useMemo, useState } from 'react';
import { ChevronRight, ExternalLink } from 'lucide-react';
import { Chip, Panel, SectionHeader } from '../../ui';
import {
  COMPETITORS,
  FILTERS,
  ROWS,
  UNKNOWN_CELL_COUNT,
  type FilterId,
  type Row,
  type Verdict,
} from './data';

/* Unit 13's artefact is a communication tool, so the thing being designed here
 * is legibility, not a table.
 *
 * A capability matrix fails in one of two ways. It is unreadable — twelve rows
 * by eight columns of prose, which nobody scans — or it is readable because it
 * was flattened into scores, which nobody can check. This renders behaviours in
 * the cells and puts the verdict in a separate, narrow column, so the eye has
 * one thing to scan down and the detail is one click away rather than crammed
 * in beside it.
 *
 * Everything below is mock data in the sense that it is hardcoded. It is not
 * mock in the sense that matters: every competitor cell traces to that vendor's
 * own documentation, and the eleven UNKNOWN cells are the ones nobody checked.
 */

/* Tone reinforces the verdict; it never carries it.
 *
 * The verdict is spelled out in the cell — "BEHIND", not a red square — because
 * DESIGN.md forbids colour as the only signal and because a reader scanning for
 * exposure should be able to do it in greyscale, or in a screenshot pasted into
 * a document that stripped the palette. */
const VERDICT_TONE: Record<Verdict, 'neutral' | 'primary' | 'warn' | 'error'> = {
  BETTER: 'primary',
  PARITY: 'neutral',
  BEHIND: 'error',
  CONVENTIONAL: 'neutral',
  'N/A': 'neutral',
  UNKNOWN: 'warn',
};

/* What the reader should do with each verdict, in one line, because "BEHIND"
 * on its own reads as a scoreboard and this document is meant to settle
 * arguments rather than keep score. */
const VERDICT_GLOSS: Record<Verdict, string> = {
  BETTER: 'genuinely ahead, and the reason fits in a sentence',
  PARITY: 'same outcome by a different route',
  BEHIND: 'mainstream is simply better here',
  CONVENTIONAL: 'do not innovate — copying is the correct answer',
  'N/A': 'a constraint, not a gap',
  UNKNOWN: 'not verified — do not build against this',
};

const ACTION_LABEL: Record<Row['action'], string> = {
  CHANGE: 'CHANGE',
  KEEP: 'KEEP',
  PROTOTYPE: 'PROTOTYPE',
  NONE: 'NO ACTION',
};

function VerdictCell({ verdict }: { verdict: Verdict }) {
  /* Chip with no `detail` renders a <span>, not a <button>. That matters: this
     sits inside a table row whose header cell already contains the expand
     button, and a button inside a button is a real DOM error rather than a
     warning to wave through. */
  return <Chip tone={VERDICT_TONE[verdict]}>{verdict}</Chip>;
}

function Cell({ text }: { text: string }) {
  const unverified = text === 'UNKNOWN';
  return (
    <span
      className={
        unverified
          ? 'text-[11px] leading-snug text-on-surface/50 italic'
          : 'text-[11px] leading-snug text-on-surface/70'
      }
    >
      {text}
    </span>
  );
}

export function CapabilityMatrix() {
  const [filter, setFilter] = useState<FilterId>('all');
  const [openRow, setOpenRow] = useState<string | null>(null);

  const rows = useMemo(() => {
    const f = FILTERS.find((x) => x.id === filter) ?? FILTERS[0];
    return ROWS.filter((r) => f.match(r));
  }, [filter]);

  const tally = useMemo(() => {
    const counts: Partial<Record<Verdict, number>> = {};
    for (const r of ROWS) counts[r.verdict] = (counts[r.verdict] ?? 0) + 1;
    return counts;
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg text-on-surface">
      <header className="shrink-0 space-y-4 border-b border-on-surface/15 px-6 py-5">
        <SectionHeader
          title="Unit 13 — capability matrix"
          level={2}
          note="The proposed Primnox architecture against seven AI interfaces. Cells state a behaviour, never a score: a scored column invites you to add it up, and nothing here was measured on a scale."
        />

        {/* The tally is the honest headline. A matrix where the home product
            wins every row is marketing, so the count of BEHIND rows is stated
            first and at the same weight as the count of BETTER ones. */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-on-surface/70">
          <span>
            <span className="text-on-surface">{ROWS.length}</span> dimensions ·{' '}
            <span className="text-on-surface">{COMPETITORS.length + 1}</span> products
          </span>
          {(['BETTER', 'BEHIND', 'CONVENTIONAL', 'N/A', 'UNKNOWN'] as Verdict[])
            .filter((v) => tally[v])
            .map((v) => (
              <span key={v} className="flex items-center gap-1.5">
                <VerdictCell verdict={v} />
                <span className="tabular-nums">{tally[v]}</span>
              </span>
            ))}
          <span>
            <span className="text-on-surface tabular-nums">{UNKNOWN_CELL_COUNT}</span> unverified
            cells
          </span>
        </div>

        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter rows">
          {FILTERS.map((f) => {
            const on = f.id === filter;
            return (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                aria-pressed={on}
                className={[
                  'px-interactive rounded-lg border px-3 py-1.5 font-mono text-[10px]',
                  'uppercase tracking-[0.14em] transition-none',
                  on
                    ? 'border-on-surface/40 bg-on-surface/10 text-on-surface'
                    : 'border-on-surface/[0.12] text-on-surface/70 hover:border-on-surface/30 hover:text-on-surface',
                ].join(' ')}
              >
                {f.label}
              </button>
            );
          })}
        </div>
      </header>

      {/* The scroll container is here rather than on the gallery, because both
          sticky axes resolve against the nearest scrolling ancestor: the header
          row has to survive scrolling down twelve dimensions, and the dimension
          column has to survive scrolling right across eight products. Put the
          overflow anywhere else and one of the two silently stops sticking. */}
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">
            Primnox benchmarked against ChatGPT, Claude, Gemini, Perplexity, Microsoft Copilot,
            Cursor and Manus across {ROWS.length} dimensions. Each row expands to show the reasoning
            and its sources.
          </caption>

          <thead>
            <tr>
              <th
                scope="col"
                className="sticky left-0 top-0 z-30 w-[15rem] min-w-[15rem] border-b border-r border-on-surface/20 bg-bg px-4 py-3 align-bottom"
              >
                <span className="px-eyebrow">Dimension</span>
              </th>
              <th
                scope="col"
                className="sticky top-0 z-20 w-[8rem] min-w-[8rem] border-b border-on-surface/20 bg-bg px-3 py-3 align-bottom"
              >
                <span className="px-eyebrow">Verdict</span>
              </th>
              <th
                scope="col"
                className="sticky top-0 z-20 w-[15rem] min-w-[15rem] border-b border-r border-on-surface/20 bg-bg px-3 py-3 align-bottom"
              >
                <span className="px-eyebrow">Primnox (proposed)</span>
              </th>
              {COMPETITORS.map((c) => (
                <th
                  key={c.id}
                  scope="col"
                  className="sticky top-0 z-20 w-[10rem] min-w-[10rem] border-b border-on-surface/20 bg-bg px-3 py-3 align-bottom"
                >
                  <span className="px-eyebrow">{c.label}</span>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {rows.map((row, i) => {
              const open = openRow === row.id;
              const panelId = `bm-detail-${row.id}`;
              /* Zebra, at 2%. Twelve rows by ten columns is exactly the density
                 where the eye loses its place mid-row, and a hairline alone
                 does not hold it. Well under the /50 text floor because it is a
                 fill, not type. */
              const zebra = i % 2 === 1 ? 'bg-on-surface/[0.02]' : '';

              return (
                <Fragment key={row.id}>
                  <tr className={zebra}>
                    {/* bg-bg and not the zebra tint: this cell is sticky, so
                        whatever scrolls under it would otherwise show through a
                        translucent fill. An opaque column is the cost of being
                        able to scroll right and still know which row you are on. */}
                    <th
                      scope="row"
                      className="sticky left-0 z-10 border-b border-r border-on-surface/10 bg-bg p-0 align-top font-normal"
                    >
                      {/* The whole dimension name is the control, so the target
                          is a name-width row rather than a chevron. The verdict
                          lives in the next cell and is deliberately NOT inside
                          this button — nesting it would be a button in a button. */}
                      <button
                        type="button"
                        onClick={() => setOpenRow(open ? null : row.id)}
                        aria-expanded={open}
                        aria-controls={panelId}
                        className="px-interactive flex w-full items-start gap-2 px-4 py-3 text-left hover:bg-on-surface/[0.05]"
                      >
                        <ChevronRight
                          size={12}
                          aria-hidden="true"
                          className={`mt-0.5 shrink-0 text-on-surface/50 transition-transform duration-150 ${
                            open ? 'rotate-90' : ''
                          }`}
                        />
                        <span className="text-[12px] leading-snug text-on-surface">
                          {row.dimension}
                        </span>
                      </button>
                    </th>

                    <td className="border-b border-on-surface/10 px-3 py-3 align-top">
                      <VerdictCell verdict={row.verdict} />
                    </td>

                    <td className="border-b border-r border-on-surface/10 px-3 py-3 align-top">
                      <Cell text={row.primnox} />
                    </td>

                    {COMPETITORS.map((c) => (
                      <td
                        key={c.id}
                        className="border-b border-on-surface/10 px-3 py-3 align-top"
                      >
                        <Cell text={row.cells[c.id]} />
                      </td>
                    ))}
                  </tr>

                  {open && (
                    <tr>
                      {/* One cell spanning the table, so the prose gets a
                          reading measure instead of a 10rem column. colSpan is
                          the whole width including the sticky ones — a detail
                          row that stopped short of the right edge would read as
                          belonging to the first few columns only. */}
                      <td
                        id={panelId}
                        colSpan={COMPETITORS.length + 3}
                        className="border-b border-on-surface/20 bg-on-surface/[0.03] p-0"
                      >
                        <div className="sticky left-0 w-[calc(100vw-20rem)] max-w-[68ch] space-y-3 px-6 py-4">
                          <p className="text-[12px] leading-relaxed text-on-surface/70">
                            {row.detail}
                          </p>

                          <div className="flex flex-wrap items-center gap-2">
                            <Chip tone={row.action === 'CHANGE' ? 'primary' : 'neutral'}>
                              {ACTION_LABEL[row.action]}
                            </Chip>
                            <span className="font-mono text-[11px] leading-snug text-on-surface/60">
                              {row.file}
                            </span>
                          </div>

                          <p className="text-[11px] leading-snug text-on-surface/55">
                            <span className="text-on-surface/70">{row.verdict}</span> —{' '}
                            {VERDICT_GLOSS[row.verdict]}
                          </p>

                          {row.sources.length > 0 && (
                            <ul className="space-y-1">
                              {row.sources.map((s) => (
                                <li key={s.href}>
                                  <a
                                    href={s.href}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="px-interactive inline-flex items-center gap-1.5 text-[11px] text-on-surface/70 underline decoration-on-surface/30 underline-offset-2 hover:text-on-surface"
                                  >
                                    {s.label}
                                    <ExternalLink size={10} aria-hidden="true" />
                                  </a>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>

        {rows.length === 0 && (
          <p className="px-6 py-8 text-[12px] text-on-surface/55">
            No rows match that filter.
          </p>
        )}

        <Panel variant="bare" className="m-6 space-y-2 p-4">
          <SectionHeader
            title="Reading the verdicts"
            level={3}
            note="Six values, and two of them are refusals to answer. That is the point."
          />
          <ul className="space-y-1.5">
            {(Object.keys(VERDICT_GLOSS) as Verdict[]).map((v) => (
              <li key={v} className="flex items-baseline gap-2.5">
                <span className="shrink-0">
                  <VerdictCell verdict={v} />
                </span>
                <span className="text-[11px] leading-snug text-on-surface/60">
                  {VERDICT_GLOSS[v]}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
