import { useState } from 'react';
import { ChevronRight, Download, FileText, Maximize2 } from 'lucide-react';
import { API } from '../lib/crs';
import { AssetPreview } from './AssetPreview';
import { Reveal } from './Reveal';

/* A file, in the turn it belongs to.
 *
 * Same shape as an authored document (see Canvas): closed it is one row you
 * can skim, pressing the name opens the file where it is. Files used to be a
 * chip that threw a full-screen modal over the conversation, so looking at an
 * attachment meant leaving the thing you were reading; a document and a file
 * are both artifacts of the same turn and now read the same way.
 *
 * The preview is fetched on first open, never on mount - a turn carrying
 * several attachments would otherwise parse every one of them before the
 * reader had asked for any.
 */
export function Attachment({
  asset,
  onExpand,
}: {
  asset: { id: string; name: string; kind?: string };
  /* The modal is still the right home for a slide deck or a PDF you actually
     want to work through, so opening it stays one press away. */
  onExpand?: () => void;
}) {
  const [open, setOpen] = useState(false);
  /* Sticky: the preview is fetched and parsed on first open, so it stays
     mounted afterwards and a second open costs nothing. */
  const [opened, setOpened] = useState(false);

  return (
    <section
      aria-label={`File: ${asset.name}`}
      className="mb-3 overflow-hidden rounded-lg border border-dr-rule bg-dr-plate"
    >
      <header className={`flex items-center gap-2 px-3 py-1.5 ${open ? 'border-b border-dr-rule' : ''}`}>
        <button
          type="button"
          onClick={() => { setOpen(o => !o); setOpened(true); }}
          aria-expanded={open}
          className="group -mx-1 flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-0.5 text-left
                     outline-none focus-visible:ring-2 focus-visible:ring-dr-fix/60"
        >
          <FileText size={12} className="shrink-0 text-on-surface/50 group-hover:text-on-surface/80" aria-hidden="true" />
          <span className="min-w-0 truncate font-mono text-[11px] text-on-surface/85 group-hover:text-on-surface">
            {asset.name}
          </span>
          <ChevronRight
            size={12} aria-hidden="true"
            className={`shrink-0 text-on-surface/50 transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
          />
        </button>

        {open && (
          <>
            <a
              href={`${API}/assets/${asset.id}/download`}
              download={asset.name}
              aria-label={`Download ${asset.name}`}
              className="rounded-md p-1 text-on-surface/55 outline-none transition-colors
                         hover:bg-on-surface/[0.06] hover:text-on-surface
                         focus-visible:ring-2 focus-visible:ring-dr-fix/60"
            >
              <Download size={12} aria-hidden="true" />
            </a>
            {onExpand && (
              <button
                type="button"
                onClick={onExpand}
                aria-label={`Open ${asset.name} full screen`}
                className="rounded-md p-1 text-on-surface/55 outline-none transition-colors
                           hover:bg-on-surface/[0.06] hover:text-on-surface
                           focus-visible:ring-2 focus-visible:ring-dr-fix/60"
              >
                <Maximize2 size={12} aria-hidden="true" />
              </button>
            )}
          </>
        )}
      </header>

      <Reveal open={open}>
        {/* Mounted only once opened, and kept mounted after: the preview
            parses the file, so re-fetching it on every collapse would make
            closing an attachment cost something. */}
        {opened && (
          <div className="max-h-[26rem] overflow-auto custom-scrollbar">
            <AssetPreview asset={asset} bounded />
          </div>
        )}
      </Reveal>
    </section>
  );
}
