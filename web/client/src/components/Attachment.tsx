import { useState, type ReactNode } from 'react';
import { ChevronRight, Download, FileText, Maximize2 } from 'lucide-react';
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
 *
 * Desktop mounts AssetPreview/AssetVersions directly, and both read the
 * loopback backend's preview layer — the one that parses docx, xlsx, pptx and
 * sqlite server-side. Web has no such layer, so those two arrive as slots
 * rather than imports. The row, the disclosure and the download are the chat
 * UI and are unchanged; the viewers plug in when web grows them.
 */
export function Attachment({
  asset,
  onExpand,
  downloadUrl,
  renderPreview,
  renderVersions,
}: {
  asset: { id: string; name: string; kind?: string };
  /* The modal is still the right home for a slide deck or a PDF you actually
     want to work through, so opening it stays one press away. */
  onExpand?: () => void;
  /* Desktop points this at `${API}/assets/:id/download`. */
  downloadUrl?: (asset: { id: string; name: string }) => string;
  renderPreview?: (asset: { id: string; name: string; kind?: string }) => ReactNode;
  renderVersions?: (assetId: string, onRestored: (id: string) => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  /* Sticky: the preview is fetched and parsed on first open, so it stays
     mounted afterwards and a second open costs nothing. */
  const [opened, setOpened] = useState(false);

  /* Restoring an old version makes a different asset current, and the preview
     has to follow or the reader restores v1 and goes on looking at v2. The
     turn still references the asset it produced — history is per-lineage, not
     per-turn — so this is local to the component rather than pushed upward. */
  const [restoredId, setRestoredId] = useState<string | null>(null);
  const shown = restoredId ? { ...asset, id: restoredId } : asset;

  const href = downloadUrl?.(shown);

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
            {href && (
              <a
                href={href}
                download={asset.name}
                aria-label={`Download ${asset.name}`}
                className="rounded-md p-1 text-on-surface/55 outline-none transition-colors
                           hover:bg-on-surface/[0.06] hover:text-on-surface
                           focus-visible:ring-2 focus-visible:ring-dr-fix/60"
              >
                <Download size={12} aria-hidden="true" />
              </a>
            )}
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
        {opened && renderPreview && (
          <div className="max-h-[26rem] overflow-auto custom-scrollbar">
            {renderPreview(shown)}
          </div>
        )}
        {opened && !renderPreview && (
          <p className="px-3 py-2 text-[11px] text-on-surface/50">
            No preview on web yet — download the file to open it.
          </p>
        )}
        {/* Below the preview, not above: the file is what the reader came for,
            and its history is context for it. Renders nothing unless this file
            has actually been regenerated. */}
        {opened && renderVersions?.(asset.id, setRestoredId)}
      </Reveal>
    </section>
  );
}
