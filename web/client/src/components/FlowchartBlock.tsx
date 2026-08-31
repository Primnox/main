import { useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import { Share2, X } from 'lucide-react';

/* A mermaid fence in a reply, rendered by the same engine as the knowledge
   graph. Falls back to the source when the diagram is a kind this does not
   understand — sequence and gantt diagrams are not graphs of this shape, and
   drawing them as one would be confidently wrong.

   Desktop renders through the loopback backend's /knowledge/flowchart. On web
   that renderer has no home yet, so the caller supplies it as `onRender`.
   Without one the fence still renders as labelled source — the same reading
   the desktop shows before you ask for the graph — and the button that would
   lie about being able to draw it is simply absent. */
export function FlowchartBlock({
  source,
  onRender,
}: {
  source: string;
  onRender?: (source: string) => Promise<string | null>;
}) {
  const [open, setOpen] = useState(false);
  const [html, setHtml] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);

  const render = useCallback(async () => {
    if (!onRender) return;
    setOpen(true);
    if (html || failed) return;
    setLoading(true);
    try {
      const out = await onRender(source);
      if (out === null) { setFailed(true); return; }
      setHtml(out);
    } catch { setFailed(true); } finally { setLoading(false); }
  }, [source, html, failed, onRender]);

  return (
    <>
      <div className="my-3 rounded-xl border border-on-surface/10 bg-on-surface/[0.03] overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2 border-b border-on-surface/[0.07]">
          <Share2 size={12} className="text-on-surface/50" />
          <span className="px-label">Flowchart</span>
          {onRender && (
            <button onClick={() => void render()}
              className="ml-auto text-[11px] uppercase tracking-[0.1em] text-on-surface/50 hover:text-on-surface transition-colors duration-200">
              {loading ? 'Rendering…' : failed ? 'Not a graph' : 'View as graph'}
            </button>
          )}
        </div>
        <pre className="p-4 overflow-x-auto">
          <code className="font-mono text-[0.78rem] leading-relaxed">{source}</code>
        </pre>
      </div>

      {open && html && createPortal(
        <div className="fixed inset-0 z-[60] bg-surface flex flex-col">
          <header className="h-14 shrink-0 flex items-center gap-3 px-6 border-b border-on-surface/[0.07]">
            <Share2 size={15} className="text-on-surface/60" />
            <span className="font-display font-bold text-[13px] uppercase tracking-[0.18em]">
              Flowchart
            </span>
            <button onClick={() => setOpen(false)} aria-label="Close flowchart"
              className="ml-auto p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05] transition duration-150">
              <X size={16} />
            </button>
          </header>
          {/* srcDoc, not a URL: the page is already rendered and holding it in
              memory avoids a second round trip and a temporary file. */}
          <iframe srcDoc={html} title="Flowchart" className="flex-1 w-full border-0" />
        </div>, document.body)}
    </>
  );
}
