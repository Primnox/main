import { useEffect } from 'react';
import { Download, FileText, X } from 'lucide-react';
import { API } from '../lib/crs';
import { AssetPreview } from './AssetPreview';

export function AssetViewer({ asset, onClose }: {
  asset: { id: string; name: string }; onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);


  /* Deliberately not a `motion` element, unlike the rest of this file.
     Wrapped in AnimatePresence as a custom component, the backdrop mounted
     with its `initial` styles — opacity 0, translateY(8px) — and no animation
     ever started, so the viewer was present in the DOM, readable to a script,
     and completely invisible to a person. A modal that silently fails to
     appear is a worse defect than a modal without a fade, so the entry
     animation is plain CSS with nothing to go wrong. */
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--scrim)] p-6"
      onClick={onClose}>
      <div
        role="dialog" aria-modal="true" aria-label={`Preview of ${asset.name}`}
        onClick={e => e.stopPropagation()}
        className="w-full max-w-5xl h-[85vh] flex flex-col rounded-2xl border border-on-surface/[0.12] bg-surface overflow-hidden shadow-2xl">

        <header className="h-12 shrink-0 flex items-center gap-3 px-4 border-b border-on-surface/[0.09]">
          <FileText size={14} className="opacity-60 shrink-0" />
          <span className="font-mono text-[12px] truncate">{asset.name}</span>
          <span className="px-label shrink-0 opacity-50">read-only</span>
          <div className="flex-1" />
          <a href={`${API}/assets/${asset.id}/download`} download={asset.name}
            className="px-2.5 py-1 rounded-lg border border-on-surface/[0.12] hover:bg-on-surface/[0.06] transition-colors duration-200 px-label inline-flex items-center gap-1.5">
            <Download size={11} /> Download
          </a>
          <button onClick={onClose} aria-label="Close preview"
            className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-on-surface/[0.08] transition-colors duration-200">
            <X size={14} />
          </button>
        </header>

        <div className="flex-1 min-h-0 overflow-auto custom-scrollbar bg-on-surface/[0.02]">
          {/* Eight format branches used to live here. They are shared with the
              inline attachment now, so the two cannot drift apart. */}
          <AssetPreview asset={asset} />
        </div>
      </div>
    </div>
  );
}

/* One table, used for spreadsheets, CSVs, database tables and the tables
   inside a Word document — they are all the same shape once parsed. */
