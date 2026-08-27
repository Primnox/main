import { useEffect, useState } from 'react';
import { History, RotateCcw } from 'lucide-react';
import { api, type AssetVersions as AssetVersionsData } from '../lib/crs';

/* An asset's lineage, when it has one.
 *
 * A document has had version history and revert since Canvas shipped; a
 * generated file had neither, so "regenerate that deck" replaced the old one
 * with nothing pointing back at it. This is the missing half.
 *
 * It renders nothing at all for a file that was never regenerated, which is
 * most files. A one-entry history is not history, and drawing it would put a
 * disclosure control on every uploaded PDF for no reason.
 *
 * Fetched on mount rather than on open, unlike the preview above it: this is
 * one small row from a table, not a parse of the file, and the component has
 * to know whether there IS a history before it can decide to draw the control
 * that would reveal it.
 */
export function AssetVersions({ assetId, onRestored }: {
  assetId: string;
  /** The turn re-reads the asset after a revert; the parent owns that. */
  onRestored?: (restoredAssetId: string) => void;
}) {
  const [data, setData] = useState<AssetVersionsData | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.assetVersions(assetId)
      .then(d => { if (live) setData(d); })
      // Silent: an asset with no lineage and an asset whose history could not
      // be read look the same to a reader, and neither is worth an error row
      // above a file that is otherwise displaying correctly.
      .catch(() => { if (live) setData(null); });
    return () => { live = false; };
  }, [assetId]);

  const versions = data?.versions ?? [];
  if (versions.length < 2) return null;

  const head = data?.head;
  // "history" retention keeps the record and treats superseded bytes as
  // disposable, so Revert cannot be promised. Offering a control that may fail
  // is worse than not offering it — that is the same defect as the retry
  // button that could never have worked.
  const restorable = data?.retention === 'keep';

  const restore = async (version: number) => {
    setBusy(version);
    setFailed(null);
    try {
      const result = await api.revertAsset(assetId, version);
      const refreshed = await api.assetVersions(assetId);
      setData(refreshed);
      onRestored?.(result.asset_id);
    } catch {
      setFailed(`Could not restore v${version}.`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="border-t border-dr-rule px-3 py-1.5">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="px-interactive flex items-center gap-1.5 text-[11px] text-on-surface/55
                   hover:text-on-surface/85"
      >
        <History size={11} aria-hidden="true" />
        <span>{versions.length} versions</span>
      </button>

      {open && (
        <ol className="mt-1.5 space-y-1">
          {[...versions].reverse().map(v => {
            const current = v.asset_id === head;
            return (
              <li key={v.version} className="flex items-center gap-2 text-[11px]">
                <span className="w-8 shrink-0 tabular-nums text-on-surface/50">
                  v{v.version}
                </span>
                <span className="min-w-0 flex-1 truncate text-on-surface/70">
                  {v.summary ?? 'edited'}
                </span>
                {current ? (
                  // Position, not colour — DESIGN.md's accessibility line, and
                  // "current" has to survive greyscale.
                  <span className="shrink-0 text-on-surface/50">current</span>
                ) : restorable ? (
                  <button
                    type="button"
                    onClick={() => restore(v.version)}
                    disabled={busy !== null}
                    aria-label={`Restore version ${v.version}`}
                    className="px-interactive flex shrink-0 items-center gap-1
                               text-on-surface/55 hover:text-on-surface disabled:opacity-50"
                  >
                    <RotateCcw size={10} aria-hidden="true" />
                    {busy === v.version ? 'restoring…' : 'restore'}
                  </button>
                ) : (
                  <span className="shrink-0 text-on-surface/40">not retained</span>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {failed && (
        <p role="status" className="mt-1 text-[11px] text-error">{failed}</p>
      )}
    </div>
  );
}
