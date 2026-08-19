import { useEffect, useState } from 'react';
import { Download, FileText, Loader2, X } from 'lucide-react';
import { API, api } from '../lib/crs';
import { SheetTable } from './SheetTable';
import { SlideDeck } from './SlideDeck';
import { WebPreview } from './WebPreview';

export function AssetViewer({ asset, onClose }: {
  asset: { id: string; name: string }; onClose: () => void;
}) {
  const [preview, setPreview] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState(0);

  useEffect(() => {
    let live = true;
    setPreview(null); setError(null); setSheet(0);
    api.preview(asset.id)
      .then(p => { if (live) setPreview(p); })
      .catch(e => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [asset.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const src = `${API}/assets/${asset.id}/download?inline=1`;

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
          {error && <p className="p-6 text-sm text-error">Could not load a preview: {error}</p>}
          {!preview && !error && (
            <p className="p-6 px-label flex items-center gap-2">
              <Loader2 size={12} className="px-spin" /> Reading…
            </p>
          )}

          {/* The PDF frame stays white in every theme, and correctly so: a PDF
              page is paper. Tinting it would misrepresent the document. */}
          {preview?.kind === 'pdf' && (
            <iframe src={src} title={asset.name} className="w-full h-full border-0 bg-white" />
          )}

          {preview?.kind === 'image' && (
            <div className="h-full flex items-center justify-center p-6">
              <img src={src} alt={asset.name} className="max-w-full max-h-full object-contain" />
            </div>
          )}

          {preview?.kind === 'web' && (
            <WebPreview src={src} name={asset.name}
              source={preview.text} truncated={preview.truncated} />
          )}

          {preview?.kind === 'text' && (
            <pre className="p-5 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words text-on-surface/80">
              {preview.text}
              {preview.truncated && <span className="text-on-surface/40">{'\n\n… truncated'}</span>}
            </pre>
          )}

          {preview?.kind === 'sheets' && preview.sheets?.length > 0 && (
            <div className="h-full flex flex-col">
              {preview.sheets.length > 1 && (
                <div className="flex gap-1 px-3 pt-3 shrink-0 flex-wrap">
                  {preview.sheets.map((s: any, i: number) => (
                    <button key={s.name + i} onClick={() => setSheet(i)}
                      className={`px-2.5 py-1 rounded-lg px-label transition-colors duration-200
                        ${i === sheet ? 'bg-on-surface/[0.10] text-on-surface'
                                      : 'text-on-surface/50 hover:bg-on-surface/[0.05]'}`}>
                      {s.name}
                    </button>
                  ))}
                </div>
              )}
              <SheetTable sheet={preview.sheets[Math.min(sheet, preview.sheets.length - 1)]} />
            </div>
          )}

          {preview?.kind === 'document' && (
            <article className="mx-auto max-w-2xl p-8 space-y-3">
              {preview.blocks.map((b: any, i: number) =>
                b.type === 'heading'
                  ? <h2 key={i} className={b.level <= 1 ? 'px-display px-display-sm' : 'text-[15px] font-semibold'}>{b.text}</h2>
                  : b.type === 'bullet'
                    ? <p key={i} className="text-sm leading-6 pl-5 relative before:content-['•'] before:absolute before:left-1 before:opacity-40">{b.text}</p>
                    : b.type === 'table'
                      ? <SheetTable key={i} sheet={{ name: '', header: b.rows[0] ?? [], rows: b.rows.slice(1), total_rows: b.rows.length - 1, truncated: false }} />
                      : <p key={i} className="text-sm leading-6 text-on-surface/80">{b.text}</p>)}
              {preview.blocks.length === 0 && <p className="px-label">This document has no text in it.</p>}
            </article>
          )}

          {preview?.kind === 'slides' && (
            <SlideDeck assetId={asset.id} slides={preview.slides}
              aspect={preview.aspect ?? 16 / 9} />
          )}

          {(preview?.kind === 'unsupported' || preview?.kind === 'unreadable'
            || preview?.kind === 'missing') && (
            <div className="p-8 text-center">
              <p className="px-body text-sm mb-1">
                {preview.kind === 'missing' ? 'The stored file is gone.'
                  : preview.kind === 'unreadable' ? 'This file could not be read.'
                    : 'No built-in viewer for this format.'}
              </p>
              {preview.error && <p className="px-label mb-3">{preview.error}</p>}
              <p className="px-label">Download it to open it elsewhere.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* One table, used for spreadsheets, CSVs, database tables and the tables
   inside a Word document — they are all the same shape once parsed. */
