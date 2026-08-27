import { useState } from 'react';
import {
  AlertTriangle, BrainCircuit, Check, ChevronRight, FileSpreadsheet, Lock,
  Maximize2, PanelRight, Quote, Square, Terminal,
} from 'lucide-react';
import { decide, type Level, type PrimitiveDescriptor } from './rule';

/* The renderer that proves the rule is mechanical.
 *
 * One component, any primitive. It asks `decide()` where the payload goes,
 * then draws the chrome that level implies — and only then does it look at
 * `kind`, to choose how the bytes are drawn INSIDE the level it was given.
 *
 * That ordering is the entire argument of Unit 4. If `kind` were consulted
 * first, this file would be a switch statement with a layout decision in every
 * arm, which is what a component catalogue is and why one was not the
 * deliverable.
 */

// ── Payload drawing. The only place `kind` is read. ────────────────────────
//
// Every branch below produces DOM text. None of them produces a canvas or an
// <img>, which is why the chart and the map satisfy WCAG 1.1.1 by
// construction rather than by remembering to add an alt attribute: the values
// are already in the accessibility tree because they are already in the DOM.

function Bars({ series, unit }: { series: { label: string; value: number }[]; unit: string }) {
  const max = Math.max(...series.map(s => s.value));
  return (
    <div className="space-y-1.5">
      {series.map(s => (
        <div key={s.label} className="flex items-center gap-2 text-[11px]">
          <span className="w-28 shrink-0 truncate text-on-surface/60">{s.label}</span>
          {/* The bar is decoration over a number that is already readable.
              Remove the bar and nothing is lost but the comparison — which is
              precisely the job a bar is doing and the only job it should be
              given. */}
          <span aria-hidden="true" className="h-2 bg-primary/40" style={{ width: `${(s.value / max) * 60}%` }} />
          <span className="tabular-nums text-on-surface/85">{s.value.toLocaleString()} {unit}</span>
        </div>
      ))}
    </div>
  );
}

function Payload({ p }: { p: PrimitiveDescriptor }) {
  const v = p.payload as any;

  switch (p.kind) {
    case 'heading':
      return <p className="text-[14px] font-semibold tracking-tight text-on-surface">{String(v)}</p>;

    case 'text':
    case 'warning':
      return <p className="text-[13px] leading-6 text-on-surface/85">{String(v)}</p>;

    case 'command':
      return (
        <span className="inline-flex items-center gap-1.5 font-mono text-[12px] text-primary">
          <Terminal size={11} aria-hidden="true" /> {String(v)}
        </span>
      );

    case 'code':
    case 'tool_result':
    case 'reasoning':
    case 'error':
      return (
        <pre className="overflow-x-auto">
          <code className="font-mono text-[11.5px] leading-relaxed text-on-surface/80">{String(v)}</code>
        </pre>
      );

    case 'table':
      return (
        <table className="w-full border-collapse text-[11.5px]">
          <thead>
            <tr>
              {v.header.map((h: string) => (
                <th key={h} className="border-b border-on-surface/20 px-2 py-1.5 text-left font-medium text-on-surface">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {v.rows.map((r: string[], i: number) => (
              <tr key={i}>
                {r.map((c, j) => (
                  <td key={j} className="border-b border-on-surface/[0.08] px-2 py-1 align-top text-on-surface/80">{c}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      );

    case 'chart':
      return (
        <figure className="m-0">
          <Bars series={v.series} unit={v.unit} />
          {/* Visible, not sr-only. A sighted reader checking a number should
              not have to trust the bar's length either. */}
          <figcaption className="mt-2 text-[11px] leading-5 text-on-surface/50">{p.textAlternative}</figcaption>
        </figure>
      );

    case 'checklist':
      return (
        <ul className="space-y-1">
          {v.map((it: { text: string; done: boolean }) => (
            <li key={it.text} className="flex items-start gap-2 text-[12px] leading-5">
              {it.done
                ? <Check size={12} className="mt-0.5 shrink-0 text-primary" aria-hidden="true" />
                : <Square size={12} className="mt-0.5 shrink-0 text-on-surface/50" aria-hidden="true" />}
              <span className={it.done ? 'text-on-surface/50 line-through' : 'text-on-surface/85'}>{it.text}</span>
              <span className="sr-only">{it.done ? ' (done)' : ' (not done)'}</span>
            </li>
          ))}
        </ul>
      );

    case 'citation':
      return (
        <ol className="space-y-1.5">
          {v.map((c: { title: string; detail: string }, i: number) => (
            <li key={c.title} className="flex gap-2 text-[11.5px] leading-5">
              <span className="tabular-nums text-on-surface/50">[{i + 1}]</span>
              <span>
                <span className="font-mono text-on-surface/85">{c.title}</span>
                <span className="text-on-surface/50"> — {c.detail}</span>
              </span>
            </li>
          ))}
        </ol>
      );

    case 'timeline':
      return (
        <ol className="space-y-1.5 border-l border-on-surface/15 pl-3">
          {v.map((e: { at: string; text: string }) => (
            <li key={e.at} className="text-[11.5px] leading-5">
              <span className="mr-2 tabular-nums font-mono text-on-surface/50">{e.at}</span>
              <span className="text-on-surface/80">{e.text}</span>
            </li>
          ))}
        </ol>
      );

    case 'progress':
      // Inline on purpose. `aria-valuenow` rather than a live region: a bar
      // that announces itself every tick is a bar nobody can listen past.
      return (
        <span className="inline-flex items-center gap-2 text-[11px] text-on-surface/70">
          <span role="progressbar" aria-valuenow={v.done} aria-valuemin={0} aria-valuemax={v.total}
            aria-label="Documents ingested"
            className="inline-block h-1.5 w-24 bg-on-surface/15">
            <span aria-hidden="true" className="block h-full bg-primary/60" style={{ width: `${(v.done / v.total) * 100}%` }} />
          </span>
          <span className="tabular-nums">{v.done} / {v.total}</span>
        </span>
      );

    case 'permission':
    case 'form':
      return (
        <div className="space-y-2.5">
          <p className="text-[12px] leading-5 text-on-surface/75">{v.detail}</p>
          <div className="flex gap-2">
            {v.options.map((o: { id: string; label: string }) => (
              <button key={o.id} type="button"
                className="border border-on-surface/20 px-3 py-1 text-[11px] uppercase tracking-[0.1em]
                           text-on-surface/75 outline-none transition-colors
                           hover:bg-on-surface/[0.06] hover:text-on-surface
                           focus-visible:ring-2 focus-visible:ring-primary/60">
                {o.label}
              </button>
            ))}
          </div>
        </div>
      );

    case 'map':
      return (
        <div>
          <ul className="space-y-1 text-[11.5px] text-on-surface/80">
            {v.places.map((pl: string) => <li key={pl}>· {pl}</li>)}
          </ul>
          <p className="mt-2 text-[11px] text-on-surface/50">{p.textAlternative}</p>
        </div>
      );

    case 'spreadsheet':
      return (
        <p className="flex items-center gap-2 text-[11.5px] text-on-surface/70">
          <FileSpreadsheet size={12} aria-hidden="true" />
          {v.rows.toLocaleString()} rows × {v.cols} columns · {(v.bytes / 1024).toFixed(0)} KB
        </p>
      );

    case 'slides':
      return <p className="text-[11.5px] text-on-surface/70">{v.slides} slides · {p.textAlternative}</p>;

    default:
      /* The primitive nobody has thought of yet.
         Not an error state and not a blank: bounded, scrollable, inert text.
         Whatever it is, the reader can at least see it and copy it. */
      return (
        <pre className="overflow-x-auto">
          <code className="font-mono text-[11.5px] leading-relaxed text-on-surface/70">
            {typeof v === 'string' ? v : JSON.stringify(v, null, 2)}
          </code>
        </pre>
      );
  }
}

// ── Level chrome ───────────────────────────────────────────────────────────

const ICON: Record<string, typeof Terminal> = {
  reasoning: BrainCircuit,
  citation: Quote,
  permission: Lock,
  form: Lock,
  error: AlertTriangle,
  warning: AlertTriangle,
};

/** A primitive, at whatever level the rule gives it.
 *
 *  `onPromote` is how `panel` and `fullscreen` happen. The renderer never
 *  reaches those levels on its own — it draws a door and hands the decision
 *  up, which is the same shape `Attachment.tsx` and `Canvas.tsx` already use
 *  (`onExpand`). Passing nothing simply means no door is drawn. */
export function PrimitiveRenderer({
  p,
  onPromote,
}: {
  p: PrimitiveDescriptor;
  onPromote?: (level: Level) => void;
}) {
  const d = decide(p);
  // Evidence opens closed; everything else opens open. Blocking cannot close
  // at all, which is why `pinned` forces the state rather than seeding it.
  const [open, setOpen] = useState(!d.collapsed);
  const shown = d.pinned || open;
  const Icon = ICON[p.kind] ?? null;

  if (d.level === 'inline') {
    /* No chrome at all. This is the level most primitives should reach, and
       the one a component catalogue never offers because a catalogue's unit
       of work is a component — so everything in it gets a border. */
    return <div className="py-1"><Payload p={p} /></div>;
  }

  return (
    <section
      aria-label={p.label}
      className="my-3 border border-on-surface/[0.09] bg-on-surface/[0.02]"
    >
      {/* The trigger and the doors are SIBLINGS, never nested. A button inside
          a button is invalid HTML and the browser un-nests it in ways that
          break the keyboard order — the reason Attachment.tsx lays its header
          out the same way. */}
      <div className={`flex items-center gap-2 px-3 py-2 ${shown ? 'border-b border-on-surface/[0.09]' : ''}`}>
        {d.pinned ? (
          <span className="flex min-w-0 flex-1 items-center gap-2">
            {Icon && <Icon size={12} className="shrink-0 text-primary/80" aria-hidden="true" />}
            <span className="px-label truncate">{p.label}</span>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => setOpen(o => !o)}
            aria-expanded={shown}
            className="group flex min-w-0 flex-1 items-center gap-2 text-left outline-none
                       focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            {Icon
              ? <Icon size={12} className="shrink-0 text-on-surface/50" aria-hidden="true" />
              : <ChevronRight size={12} aria-hidden="true"
                  className={`shrink-0 text-on-surface/50 transition-transform duration-150 ${shown ? 'rotate-90' : ''}`} />}
            <span className="px-label truncate group-hover:text-on-surface">{p.label}</span>
          </button>
        )}

        {/* The door, offered only where the rule says there is somewhere to go.
            `handle || persists` is the whole test — never size. */}
        {shown && d.offers.includes('panel') && onPromote && (
          <button type="button" onClick={() => onPromote('panel')}
            aria-label={`Open ${p.label} in a side panel`}
            className="p-1 text-on-surface/55 outline-none transition-colors
                       hover:bg-on-surface/[0.06] hover:text-on-surface
                       focus-visible:ring-2 focus-visible:ring-primary/60">
            <PanelRight size={12} aria-hidden="true" />
          </button>
        )}
        {shown && d.offers.includes('fullscreen') && onPromote && (
          <button type="button" onClick={() => onPromote('fullscreen')}
            aria-label={`Open ${p.label} full screen`}
            className="p-1 text-on-surface/55 outline-none transition-colors
                       hover:bg-on-surface/[0.06] hover:text-on-surface
                       focus-visible:ring-2 focus-visible:ring-primary/60">
            <Maximize2 size={12} aria-hidden="true" />
          </button>
        )}
      </div>

      {shown && (
        <div className={`px-3 py-2.5 ${d.scroller ? 'max-h-56 overflow-auto custom-scrollbar' : ''}`}>
          <Payload p={p} />
        </div>
      )}

      {/* Violations are shown rather than swallowed. A rule whose failures are
          invisible in the prototype is a rule that will ship broken. */}
      {d.violations.length > 0 && (
        <ul className="border-t border-error/30 bg-error/[0.06] px-3 py-2">
          {d.violations.map(v => (
            <li key={v} className="flex items-start gap-1.5 text-[11px] leading-5 text-error">
              <AlertTriangle size={11} className="mt-0.5 shrink-0" aria-hidden="true" /> {v}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
