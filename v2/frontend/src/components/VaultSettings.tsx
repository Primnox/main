import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, Copy, Lock, ShieldAlert, Unlock } from 'lucide-react';
import { API } from '../lib/crs';
import { Button, Chip, SectionHeader } from './ui';

type VaultStatus = { enabled: boolean; locked: boolean };

/* BIP-39 encryption for primnox.db at rest.
 *
 * Three states, three UIs — never one component trying to be all of them:
 *   - off:      an explanation and one button.
 *   - just set up: the mnemonic, shown exactly once, gated behind an
 *     explicit "I've saved it" acknowledgement rather than a timer or a
 *     second screen — the phrase does not exist anywhere else once this
 *     closes, not in the database, not recoverable from the app.
 *   - on:       a status chip and a two-step disable, same inline-confirm
 *     shape as deleting a chat (see ChatRow) rather than window.confirm(),
 *     which several embedded webviews silently swallow.
 *
 * KNOWN GAP, stated rather than hidden: there is currently no way to unlock
 * a vault from this UI if the OS keychain entry is ever lost (a new
 * machine, a cleared keychain) — app.py's startup only unlocks
 * automatically from the keychain, and refuses to boot otherwise. Recovery
 * would need a way to supply the mnemonic BEFORE the database opens, which
 * this HTTP-endpoint-based UI cannot reach (the server that would serve it
 * is the thing waiting on the unlock). That's a separate piece of work.
 */
export function VaultSettings() {
  const [status, setStatus] = useState<VaultStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirmingDisable, setConfirmingDisable] = useState(false);

  const load = useCallback(() => {
    fetch(`${API}/vault`).then(r => r.json()).then(setStatus).catch(() => setStatus(null));
  }, []);
  useEffect(load, [load]);

  const setup = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const r = await fetch(`${API}/vault/setup`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      const d = await r.json();
      if (!r.ok) { setError(d.detail ?? 'Could not enable encryption.'); return; }
      setRevealed(d.mnemonic);
      setSaved(false);
      load();
    } finally { setBusy(false); }
  }, [load]);

  const disable = useCallback(async () => {
    setBusy(true); setError(null); setConfirmingDisable(false);
    try {
      const r = await fetch(`${API}/vault/disable`, { method: 'POST' });
      if (!r.ok) { const d = await r.json(); setError(d.detail ?? 'Could not disable encryption.'); return; }
      load();
    } finally { setBusy(false); }
  }, [load]);

  const copy = useCallback(() => {
    if (!revealed) return;
    navigator.clipboard?.writeText(revealed).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => undefined);
  }, [revealed]);

  if (revealed) {
    const words = revealed.split(' ');
    return (
      <section className="space-y-4">
        <SectionHeader title="Vault" level={3} />
        <div className="rounded-xl border border-warn/40 bg-warn/[0.06] p-4 space-y-4">
          <div className="flex items-start gap-3">
            <AlertTriangle size={16} className="shrink-0 mt-0.5 text-warn" aria-hidden="true" />
            <div className="min-w-0 space-y-1">
              <p className="text-[13px] font-medium">Write down these 12 words now.</p>
              <p className="text-[12px] text-on-surface/60 leading-relaxed">
                This is the only time they're shown. They aren't stored anywhere this app
                can read back — not in the database, not in a log. Lose them and an
                encrypted primnox.db cannot be opened again, by you or anyone.
              </p>
            </div>
          </div>

          <ol className="grid grid-cols-3 gap-2" aria-label="Recovery phrase, 12 words in order">
            {words.map((w, i) => (
              <li key={i}
                className="flex items-center gap-2 rounded-lg border border-on-surface/[0.10] px-2.5 py-1.5">
                <span className="font-mono text-[10px] text-on-surface/35 tabular-nums w-4 text-right shrink-0">
                  {i + 1}
                </span>
                <span className="font-mono text-[12px] truncate">{w}</span>
              </li>
            ))}
          </ol>

          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={copy}>
              {copied ? <Check size={12} /> : <Copy size={12} />}
              <span className="ml-1.5">{copied ? 'Copied' : 'Copy'}</span>
            </Button>
          </div>

          <label className="flex items-start gap-2.5 cursor-pointer">
            <input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)}
              className="mt-0.5 accent-[var(--color-primary)]" />
            <span className="text-[12px] text-on-surface/70">
              I've written this down somewhere that isn't this screen.
            </span>
          </label>

          <Button variant="solid" size="sm" disabled={!saved}
            onClick={() => setRevealed(null)}>
            Done
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <SectionHeader title="Vault" level={3}
        note="Encrypts primnox.db at rest with a 12-word key only you hold." />

      {error && (
        <p className="flex items-center gap-2 text-[12px] text-error">
          <ShieldAlert size={13} className="shrink-0" aria-hidden="true" />{error}
        </p>
      )}

      {status === null ? null : !status.enabled ? (
        <div className="flex items-start gap-3 rounded-xl border border-on-surface/[0.10] p-4">
          <Unlock size={16} className="shrink-0 mt-0.5 text-on-surface/50" aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-3">
            <p className="text-[12px] text-on-surface/60 leading-relaxed">
              Off. primnox.db sits on disk in the clear — readable by anything with
              filesystem access, including a backup tool or another account on this
              machine. Turning this on generates a 12-word phrase, encrypts the database
              with a key derived from it, and unlocks automatically on normal startup —
              nothing changes about how you use the app day to day.
            </p>
            <Button variant="solid" size="sm" onClick={setup} disabled={busy}>
              {busy ? 'Setting up…' : 'Set up encryption'}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-3 rounded-xl border border-on-surface/[0.10] p-4">
          <Lock size={16} className="shrink-0 mt-0.5 text-on-surface/50" aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-3">
            <div className="flex items-center gap-2">
              <Chip tone="success">Encrypted</Chip>
              {status.locked && <Chip tone="warn">Locked</Chip>}
            </div>
            <p className="text-[12px] text-on-surface/60 leading-relaxed">
              primnox.db is encrypted at rest and unlocks automatically on startup using
              the key this machine's OS keychain holds.
            </p>
            {confirmingDisable ? (
              <div className="flex items-center gap-2">
                <span className="text-[12px] text-error">
                  Turn off encryption? The database goes back to plain text.
                </span>
                <Button variant="danger" size="sm" onClick={disable} disabled={busy}>
                  {busy ? 'Disabling…' : 'Confirm'}
                </Button>
                <Button variant="quiet" size="sm" onClick={() => setConfirmingDisable(false)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => setConfirmingDisable(true)}>
                Disable encryption
              </Button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
