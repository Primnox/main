import { useState } from 'react';
import { Code2, ExternalLink, Eye } from 'lucide-react';

/* A generated HTML page, rendered — with its source one click away.
 *
 * `.html` sat in the TEXTUAL set, so the `frontend-slides` skill's entire
 * output — an animated 16:9 deck — opened as its own markup. The file was
 * fine; the viewer simply never showed it.
 *
 * ── The sandbox is the whole design ────────────────────────────────────────
 * This markup was written by a language model, which makes it untrusted input
 * no matter how it got here. The frame runs with `allow-scripts` because a deck
 * without JavaScript has no transitions and no keyboard navigation — and
 * WITHOUT `allow-same-origin`, deliberately.
 *
 * Those two together are the combination that must never appear: granting both
 * puts the frame in its own document's origin, from which it can reach up and
 * remove the sandbox attribute entirely, and the isolation was never real. With
 * scripts alone the page is dropped into an opaque origin — it animates, it
 * responds to keys, and it can touch neither this app's storage nor its DOM.
 *
 * `allow-popups` and `allow-top-navigation` are likewise withheld: a preview
 * that can navigate the tab it is previewed in can replace Primnox with
 * anything it likes.
 */
export function WebPreview({ src, name, source, truncated }: {
  src: string; name: string; source?: string; truncated?: boolean;
}) {
  const [showSource, setShowSource] = useState(false);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 flex items-center gap-1 px-3 py-2
                      border-b border-on-surface/[0.07]">
        <div role="group" aria-label="View as" className="flex items-center gap-1">
          <button onClick={() => setShowSource(false)} aria-pressed={!showSource}
            className={`px-interactive flex items-center gap-1.5 rounded-lg px-2.5 py-1 px-label
              ${!showSource ? 'bg-on-surface/[0.10] text-on-surface'
                            : 'text-on-surface/50 hover:bg-on-surface/[0.05]'}`}>
            <Eye size={12} aria-hidden="true" /> Preview
          </button>
          <button onClick={() => setShowSource(true)} aria-pressed={showSource}
            className={`px-interactive flex items-center gap-1.5 rounded-lg px-2.5 py-1 px-label
              ${showSource ? 'bg-on-surface/[0.10] text-on-surface'
                           : 'text-on-surface/50 hover:bg-on-surface/[0.05]'}`}>
            <Code2 size={12} aria-hidden="true" /> Source
          </button>
        </div>

        <span className="px-label ml-auto hidden sm:inline text-on-surface/35">
          sandboxed · no network access to Primnox
        </span>

        {/* The deck is built for a 1920×1080 stage. A preview pane is not that,
            so the way to actually present it is a real tab. */}
        <a href={src} target="_blank" rel="noopener noreferrer"
          className="px-interactive flex items-center gap-1.5 rounded-lg px-2.5 py-1 px-label
                     text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05]">
          <ExternalLink size={12} aria-hidden="true" /> Open full
        </a>
      </div>

      {showSource ? (
        <pre className="flex-1 min-h-0 overflow-auto custom-scrollbar p-5 font-mono
                        text-[12px] leading-relaxed whitespace-pre-wrap break-words
                        text-on-surface/80">
          {source}
          {truncated && <span className="text-on-surface/40">{'\n\n… truncated'}</span>}
        </pre>
      ) : (
        <iframe src={src} title={name}
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
          className="flex-1 min-h-0 w-full border-0 bg-white" />
      )}
    </div>
  );
}
