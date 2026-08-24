import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronRight, Loader2 } from 'lucide-react';
import { api, type Guide } from '../lib/crs';

/* A guide, opened where the question is asked.
 *
 * The guides used to live in their own Settings tab. That is the arrangement
 * where documentation goes to die: it requires the reader to already suspect
 * an explanation exists, leave the thing they were doing, find it in a list,
 * and carry the answer back. Nobody does that while mid-task, so the tab was
 * read once and never again.
 *
 * So each guide is now attached to the control it explains. "How routing and
 * failover work" sits under the routing chain; "When a provider stops working"
 * sits with the profile that just failed a test. The reader is already looking
 * at the thing.
 *
 * NOT A MODAL, and not a tooltip. A modal would interrupt the task to explain
 * the task, and a tooltip cannot hold 800 words or a table. A disclosure keeps
 * the surface calm when closed, and keeps the surrounding controls visible and
 * usable when open — which matters, because the whole point is to read the
 * explanation while looking at the thing it describes.
 *
 * The body is fetched on FIRST OPEN, not on mount. Five guides is ~3,500 words
 * that most sessions never expand, and paying for them on every settings open
 * to have them sit collapsed is the version that makes the panel feel slow.
 */

const COMPONENTS = {
  h1: () => null,          // the disclosure's own summary is the title
  h2: ({ children }: any) => (
    <h4 className="mb-1.5 mt-4 text-[12px] font-semibold tracking-tight text-on-surface first:mt-0">
      {children}
    </h4>
  ),
  p: ({ children }: any) => (
    <p className="my-2 text-[12px] leading-[1.7] text-on-surface/70">{children}</p>
  ),
  ul: ({ children }: any) => <ul className="my-2 list-disc space-y-0 pl-4">{children}</ul>,
  ol: ({ children }: any) => <ol className="my-2 list-decimal space-y-0 pl-4">{children}</ol>,
  li: ({ children }: any) => (
    <li className="my-1 text-[12px] leading-[1.65] text-on-surface/70">{children}</li>
  ),
  strong: ({ children }: any) => <strong className="font-semibold text-on-surface">{children}</strong>,
  code: ({ children }: any) => (
    <code className="rounded bg-on-surface/[0.06] px-1 py-0.5 font-mono text-[11px] text-on-surface/85">
      {children}
    </code>
  ),
  a: ({ children }: any) => <span className="text-on-surface/85">{children}</span>,
  table: ({ children }: any) => (
    <div className="my-3 overflow-x-auto custom-scrollbar">
      <table className="w-full border-collapse text-[11.5px]">{children}</table>
    </div>
  ),
  th: ({ children }: any) => (
    <th className="whitespace-nowrap border-b border-on-surface/[0.12] px-2 py-1.5 text-left font-mono text-[10px] uppercase tracking-[0.12em] text-on-surface/50">
      {children}
    </th>
  ),
  td: ({ children }: any) => (
    <td className="border-b border-on-surface/[0.05] px-2 py-1.5 align-top text-on-surface/70">
      {children}
    </td>
  ),
};

export function GuideInline({ slug, label }: { slug: string; label: string }) {
  const [open, setOpen] = useState(false);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const body = useRef<HTMLDivElement>(null);

  const toggle = useCallback(() => setOpen(o => !o), []);

  useEffect(() => {
    if (!open || guide || loading) return;
    setLoading(true);
    api.guide(slug)
      .then(g => { setGuide(g); setFailed(false); })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, [open, guide, loading, slug]);

  return (
    <div className="rounded-lg border border-on-surface/[0.07]">
      <button onClick={toggle} aria-expanded={open}
        className="px-interactive flex w-full items-center gap-2 px-3 py-2 text-left
                   hover:bg-on-surface/[0.02]">
        <ChevronRight size={12} aria-hidden="true"
          className={`shrink-0 text-on-surface/50 transition-transform duration-200
                      ${open ? 'rotate-90' : ''}`} />
        <span className="min-w-0 flex-1 truncate font-mono text-[10px] uppercase tracking-[0.12em] text-on-surface/50">
          {label}
        </span>
        {loading && <Loader2 size={11} className="px-spin shrink-0 text-on-surface/50" />}
      </button>

      {open && (
        <div ref={body}
          className="animate-[settings-panel-in_160ms_cubic-bezier(0.23,1,0.32,1)]
                     border-t border-on-surface/[0.07] px-3 pb-3 pt-1">
          {failed && (
            <p className="py-2 text-[11px] text-on-surface/50">
              The guide did not load. It ships with the backend, so this usually
              means the backend is not running rather than the guide being missing.
            </p>
          )}
          {guide && (
            /* Prose measure even inside a wide panel: a 900px line of body text
               is unreadable however much room there is for it. */
            <div className="px-prose max-w-[68ch]">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
                {guide.body}
              </ReactMarkdown>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
