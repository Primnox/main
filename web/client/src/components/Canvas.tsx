import { useCallback, useEffect, useState } from 'react';
import { ChevronRight, FileText, History, Loader2, Maximize2, RotateCcw, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MD } from '../lib/md';
import { CopyButton } from './CopyButton';
import { Reveal } from './Reveal';

/* Whether this file is prose to be READ or source to be looked at.
 *
 * The first version rendered every document as raw monospace, so a markdown
 * document showed its own syntax: a `# Heading` line arrived as the literal
 * characters `# Heading`. The model writes markdown by default, which made
 * the common case the broken one.
 *
 * Decided by extension first because that is what the file actually is; the
 * workspace kind is the fallback for a file with no useful suffix. Source
 * files stay in <pre>, where the monospace is doing real work rather than
 * dressing prose up as something technical. */
const PROSE_EXT = /\.(md|markdown|txt|rst)$/i;
const PROSE_KINDS = new Set(['markdown', 'doc', 'text']);

function isProse(path: string | null, kind: string | undefined): boolean {
  if (path && /\.[a-z0-9]+$/i.test(path)) return PROSE_EXT.test(path);
  return PROSE_KINDS.has((kind ?? '').toLowerCase());
}

/* The canvas: a document the model authored, rendered where it was made.
 *
 * Everything behind this already existed - versions, revert, diff on the
 * backend, workspace() and revert() in lib/crs.ts. What was missing was any
 * surface at all, so a document announced itself as a dead chip and stayed
 * unreadable.
 *
 * It renders INLINE, inside the leg that produced it. A document is part of
 * what the turn said, not a separate destination, and on a track you can
 * retrace, the artifact belongs at the coordinate it was made at. The panel
 * variant exists only for when you want the wider measure to work in.
 *
 * Versions are the direction's recoverability line made literal: restoring is
 * a FORWARD move, exactly as the API documents. Restoring v1 writes a new v3
 * carrying v1's content, so the version you left is still on the list.
 *
 * Desktop reads api.workspace / api.revert on the loopback backend. On web a
 * workspace is rebuilt from sealed `workspace.created` / `workspace.updated`
 * events, so both arrive as props — the same injection TurnBlock uses for
 * retry. Without a loader the document reports itself unopenable rather than
 * spinning forever.
 */

export type Workspace = {
  id: string;
  title: string;
  kind: string;
  version: number;
  current_version: number;
  files: Record<string, string>;
  versions: { version: number; summary: string | null; created_at: number }[];
};

export function Canvas({
  id,
  onClose,
  onExpand,
  variant = 'panel',
  title,
  version,
  loadWorkspace,
  revertWorkspace,
}: {
  id: string;
  onClose?: () => void;
  onExpand?: () => void;
  variant?: 'panel' | 'inline';
  /* Known from the turn's own event before anything is fetched, so a closed
     artifact can name itself without a request. */
  title?: string;
  version?: number;
  loadWorkspace?: (id: string, version?: number) => Promise<Workspace>;
  revertWorkspace?: (id: string, version: number) => Promise<void>;
}) {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showVersions, setShowVersions] = useState(false);

  const inline = variant === 'inline';

  /* Inline artifacts sit closed. A turn can produce several, and a
     conversation full of documents that all render in full turns the
     transcript into a filing cabinet you have to scroll past to reach the
     next thing anyone said. Closed, an artifact is one line you can skim; a
     click opens it where it is. The panel variant is always open, because
     opening it was the whole instruction. */
  const [open, setOpen] = useState(!inline);

  const load = useCallback(async (version?: number) => {
    setError(null);
    if (!loadWorkspace) {
      setError('That document could not be opened.');
      return;
    }
    try {
      const data = await loadWorkspace(id, version);
      setWs(data);
      setPath(prev => (prev && data.files[prev] ? prev : Object.keys(data.files)[0] ?? null));
    } catch {
      setError('That document could not be opened.');
    }
  }, [id, loadWorkspace]);

  /* Fetched when first opened, not when mounted. Eight artifacts in a
     conversation were eight requests fired before the reader had looked at
     any of them. */
  useEffect(() => { if (open && !ws) void load(); }, [open, ws, load]);

  /* Escape closes the panel. Inline has nothing to dismiss, so it does not
     steal the key from whatever else is listening. */
  useEffect(() => {
    if (inline || !onClose) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [inline, onClose]);

  const revert = useCallback(async (version: number) => {
    if (!revertWorkspace) return;
    setBusy(true);
    try {
      await revertWorkspace(id, version);
      await load();
      setShowVersions(false);
    } catch {
      setError('That version could not be restored.');
    } finally {
      setBusy(false);
    }
  }, [id, load, revertWorkspace]);

  const files = ws ? Object.keys(ws.files) : [];
  const body = ws && path ? ws.files[path] ?? '' : '';
  const behind = !!ws && ws.version !== ws.current_version;

  const Root: any = inline ? 'section' : 'aside';
  const name = ws?.title ?? title ?? 'Document';
  const shownVersion = ws?.version ?? version;

  return (
    <Root
      aria-label={`Document: ${name}`}
      className={
        inline
          /* A plate on the table: a step off the working surface, hairline
             edge, no shadow and no radius jump. Not a card. Closed, it is one
             line; open, the plate grows to hold the document. */
          ? 'mb-3 overflow-hidden rounded-lg border border-dr-rule bg-dr-plate'
          : 'flex h-full w-full flex-col border-l border-dr-rule bg-dr-plate'
      }
    >
      <header className={`flex items-center gap-2 px-3 ${inline ? 'py-1.5' : 'py-3'} ${open ? 'border-b border-dr-rule' : ''}`}>
        {/* Closed, the mark and the name ARE the control: the whole row opens
            it, so the target is a row rather than a 12px glyph. */}
        {inline ? (
          <button
            type="button"
            onClick={() => setOpen(o => !o)}
            aria-expanded={open}
            className="group -mx-1 flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-0.5 text-left
                       outline-none focus-visible:ring-2 focus-visible:ring-dr-fix/60"
          >
            <FileText size={12} className="shrink-0 text-on-surface/50 group-hover:text-on-surface/80" aria-hidden="true" />
            <span className="min-w-0 truncate text-[12px] font-medium text-on-surface/85 group-hover:text-on-surface">
              {name}
            </span>
            {shownVersion !== undefined && !open && (
              <span className="dr-measure shrink-0 text-[10px] text-on-surface/50">v{shownVersion}</span>
            )}
            <ChevronRight
              size={12} aria-hidden="true"
              className={`shrink-0 text-on-surface/50 transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
            />
          </button>
        ) : (
          <>
            <FileText size={12} className="shrink-0 text-on-surface/50" aria-hidden="true" />
            <h3 className="min-w-0 flex-1 truncate text-[12px] font-medium">{name}</h3>
          </>
        )}
        {/* The working controls belong to an artifact you are actually
            looking at. Closed, they are noise on a line that is meant to be
            skimmed. */}
        {open && ws && (
          <>
            <button
              type="button"
              onClick={() => setShowVersions(v => !v)}
              aria-expanded={showVersions}
              aria-label={`Version ${ws.version}. Show history`}
              className="dr-measure flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px]
                         text-on-surface/65 outline-none transition-colors
                         hover:bg-on-surface/[0.06] hover:text-on-surface
                         focus-visible:ring-2 focus-visible:ring-dr-fix/60"
            >
              <History size={11} aria-hidden="true" />
              v{ws.version}
            </button>
            {body && <CopyButton text={body} label="Copy" />}
            {inline && onExpand && (
              <button
                type="button"
                onClick={onExpand}
                aria-label="Open document beside the track"
                className="rounded-md p-1 text-on-surface/55 outline-none transition-colors
                           hover:bg-on-surface/[0.06] hover:text-on-surface
                           focus-visible:ring-2 focus-visible:ring-dr-fix/60"
              >
                <Maximize2 size={12} aria-hidden="true" />
              </button>
            )}
          </>
        )}
        {!inline && onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close document"
            className="rounded-md p-1 text-on-surface/55 outline-none transition-colors
                       hover:bg-on-surface/[0.06] hover:text-on-surface
                       focus-visible:ring-2 focus-visible:ring-dr-fix/60"
          >
            <X size={13} aria-hidden="true" />
          </button>
        )}
      </header>

      {open && behind && (
        <p className="border-b border-dr-reckoning/30 bg-dr-reckoning/[0.07] px-3 py-2 text-[11px] text-on-surface/80">
          Showing version {ws!.version}. The current version is {ws!.current_version}.
        </p>
      )}

      {open && error && (
        <p role="alert" className="border-b border-dr-refusal/30 px-3 py-2 text-[11px] text-dr-refusal">
          {error}
        </p>
      )}

      {open && showVersions && ws && (
        <ul className="max-h-48 overflow-y-auto border-b border-dr-rule">
          {[...ws.versions].reverse().map(v => (
            <li key={v.version} className="flex items-center gap-3 px-3 py-2">
              <button
                type="button"
                onClick={() => { void load(v.version); setShowVersions(false); }}
                className="dr-measure shrink-0 rounded px-1 text-[10px] text-on-surface/65
                           outline-none hover:text-on-surface
                           focus-visible:ring-2 focus-visible:ring-dr-fix/60"
              >
                v{v.version}
              </button>
              <span className="min-w-0 flex-1 truncate text-[11px] text-on-surface/70">
                {v.summary || 'no summary'}
              </span>
              {v.version !== ws.current_version && revertWorkspace && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void revert(v.version)}
                  className="flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px]
                             text-on-surface/65 outline-none transition-colors
                             hover:text-on-surface disabled:opacity-40
                             focus-visible:ring-2 focus-visible:ring-dr-fix/60"
                >
                  {busy ? <Loader2 size={10} className="animate-spin" aria-hidden="true" />
                        : <RotateCcw size={10} aria-hidden="true" />}
                  Restore
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {open && files.length > 1 && (
        <div className="flex gap-1 overflow-x-auto border-b border-dr-rule px-3 py-1.5">
          {files.map(f => (
            <button
              key={f}
              type="button"
              onClick={() => setPath(f)}
              aria-current={f === path}
              className={[
                'dr-measure shrink-0 rounded px-2 py-1 text-[10px] outline-none transition-colors',
                'focus-visible:ring-2 focus-visible:ring-dr-fix/60',
                f === path
                  ? 'bg-on-surface/[0.09] text-on-surface'
                  : 'text-on-surface/60 hover:text-on-surface',
              ].join(' ')}
            >
              {f}
            </button>
          ))}
        </div>
      )}

      {/* Inline is bounded and scrolls its own overflow: a long document must
          not push the rest of the conversation off the screen. The panel owns
          the full height it was given. */}
      <Reveal open={open}>
      <div className={
        inline
          ? 'max-h-[26rem] overflow-y-auto custom-scrollbar'
          : 'min-h-0 flex-1 overflow-y-auto custom-scrollbar'
      }>
        {!ws && !error && (
          <p className="px-3 py-5 text-[12px] text-on-surface/55">Opening…</p>
        )}
        {ws && !body && (
          <p className="px-3 py-5 text-[12px] text-on-surface/55">This document is empty.</p>
        )}
        {body && (
          isProse(path, ws?.kind) ? (
            /* Prose renders as prose. Same markdown components the reply body
               uses, so a heading, a list and a code span look the same
               wherever they appear. */
            <div className="px-3 py-3 text-[13px] leading-6">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{body}</ReactMarkdown>
            </div>
          ) : (
            /* Source stays monospace. pre-wrap, never `pre`: it wraps to the
               measure rather than growing a horizontal scroller - the same
               defect that made a backticked prompt unreadable in the reply. */
            <pre className="whitespace-pre-wrap [overflow-wrap:anywhere] px-3 py-3
                            font-mono text-[12px] leading-relaxed text-on-surface/90">
              {body}
            </pre>
          )
        )}
      </div>
      </Reveal>
    </Root>
  );
}
