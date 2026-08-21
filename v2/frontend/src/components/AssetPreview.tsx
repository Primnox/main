import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { API, api } from '../lib/crs';
import { SheetTable } from './SheetTable';
import { SlideDeck } from './SlideDeck';
import { WebPreview } from './WebPreview';

/* Rendering a file, by whatever kind the backend decided it is.
 *
 * Lifted out of AssetViewer so the modal and the inline attachment show the
 * same thing. It was the whole body of that component, which meant an inline
 * viewer would have been a second copy of eight format branches, drifting
 * from the first the moment either changed.
 *
 * `bounded` is the one real difference between the two homes: the modal owns
 * a fixed 85vh and can hand full height to a PDF frame or a slide deck, while
 * the inline version lives inside a scrolling transcript and must declare a
 * height instead of trying to fill one.
 */
export function AssetPreview({
  asset,
  bounded = false,
}: {
  asset: { id: string; name: string };
  bounded?: boolean;
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

  const src = `${API}/assets/${asset.id}/download?inline=1`;
  /* A media frame needs a real height in both homes: `h-full` inside a
     transcript resolves to zero, which is how an inline PDF renders as an
     invisible nothing rather than a document. */
  const frame = bounded ? 'h-[26rem]' : 'h-full';

  if (error) return <p className="p-5 text-sm text-error">Could not load a preview: {error}</p>;
  if (!preview) {
    return (
      <p className="p-5 px-label flex items-center gap-2">
        <Loader2 size={12} className="px-spin" aria-hidden="true" /> Reading…
      </p>
    );
  }

  return (
    <>
      {/* The PDF frame stays white in every theme, and correctly so: a PDF
          page is paper. Tinting it would misrepresent the document. */}
      {preview.kind === 'pdf' && (
        <iframe src={src} title={asset.name} className={`w-full ${frame} border-0 bg-white`} />
      )}

      {preview.kind === 'image' && (
        <div className={`flex items-center justify-center p-5 ${bounded ? 'max-h-[26rem]' : 'h-full'}`}>
          <img src={src} alt={asset.name} className="max-w-full max-h-full object-contain" />
        </div>
      )}

      {preview.kind === 'web' && (
        <WebPreview src={src} name={asset.name}
          source={preview.text} truncated={preview.truncated} />
      )}

      {preview.kind === 'text' && (
        <pre className="p-5 font-mono text-[12px] leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere] text-on-surface/80">
          {preview.text}
          {preview.truncated && <span className="text-on-surface/40">{'\n\n… truncated'}</span>}
        </pre>
      )}

      {preview.kind === 'sheets' && preview.sheets?.length > 0 && (
        <div className={bounded ? 'flex flex-col' : 'h-full flex flex-col'}>
          {preview.sheets.length > 1 && (
            <div className="flex gap-1 px-3 pt-3 shrink-0 flex-wrap">
              {preview.sheets.map((s: any, i: number) => (
                <button key={s.name + i} onClick={() => setSheet(i)}
                  aria-current={i === sheet}
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

      {preview.kind === 'document' && (
        <article className={`mx-auto max-w-2xl space-y-3 ${bounded ? 'p-5' : 'p-8'}`}>
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

      {preview.kind === 'slides' && (
        <SlideDeck assetId={asset.id} slides={preview.slides}
          aspect={preview.aspect ?? 16 / 9} />
      )}

      {(preview.kind === 'unsupported' || preview.kind === 'unreadable'
        || preview.kind === 'missing') && (
        <div className="p-6 text-center">
          <p className="px-body text-sm mb-1">
            {preview.kind === 'missing' ? 'The stored file is gone.'
              : preview.kind === 'unreadable' ? 'This file could not be read.'
                : 'No built-in viewer for this format.'}
          </p>
          {preview.error && <p className="px-label mb-3">{preview.error}</p>}
          <p className="px-label">Download it to open it elsewhere.</p>
        </div>
      )}
    </>
  );
}
