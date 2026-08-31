import { useState } from 'react';
import type { PrimnoxClient, VaultState } from '../client';
import { isValidMnemonic } from '../crypto';

const field =
  'w-full border border-dr-rule-firm bg-[var(--bg)] px-2.5 py-2 font-mono text-[13px] text-on-surface outline-none focus-visible:border-primary';
const wrap = 'mx-auto mt-24 w-full max-w-[440px] px-5';
const err = 'mt-4 border border-primary/60 p-2 font-mono text-[11.5px] text-primary';
const sub = 'mb-4 font-mono text-[12px] text-on-surface-variant';

export function VaultGate({
  client,
  state,
  pendingRecovery = false,
}: {
  client: PrimnoxClient;
  state: VaultState;
  pendingRecovery?: boolean;
}) {
  const [pass, setPass] = useState('');
  const [mnemonic, setMnemonic] = useState<string | null>(null);
  const [confirmWords, setConfirmWords] = useState('');
  const [recovery, setRecovery] = useState('');
  const [mode, setMode] = useState<'unlock' | 'recover'>('unlock');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (state === 'no-vault' && !mnemonic && !pendingRecovery) {
    return (
      <div className={wrap}>
        <h2 className="px-eyebrow mb-1">[ Set a passphrase ]</h2>
        <p className={sub}>
          It derives a key that stays in this tab and wraps a random data key. Only ciphertext is
          ever stored. There is no reset.
        </p>
        <label className="px-label mb-1 block" htmlFor="np">
          Passphrase
        </label>
        <input id="np" className={field} type="password" value={pass} onChange={(e) => setPass(e.target.value)} autoComplete="new-password" />
        <button
          className="px-btn mt-5"
          disabled={busy || pass.length < 8}
          onClick={run(async () => {
            const { mnemonic: m } = await client.createVault(pass);
            setMnemonic(m);
            setPass('');
          })}
        >
          {busy ? 'Deriving…' : 'Create vault'}
        </button>
        {pass.length > 0 && pass.length < 8 && <p className="mt-2 font-mono text-[11px] text-primary">at least 8 characters</p>}
        {error && <div className={err}>{error}</div>}
      </div>
    );
  }

  if (mnemonic || pendingRecovery) {
    const ok =
      !!mnemonic && confirmWords.trim().split(/\s+/).filter(Boolean).length === 24 && isValidMnemonic(confirmWords);
    return (
      <div className={wrap}>
        <h2 className="px-eyebrow mb-1">[ Recovery phrase ]</h2>
        {mnemonic ? (
          <>
            <p className={sub}>Write these 24 words down offline. This is the only time they are shown.</p>
            <div className="border border-primary/70 p-3 font-mono text-[13px] leading-[1.9] tracking-[0.03em] text-on-surface">
              {mnemonic}
            </div>
            <p className="mt-2 font-mono text-[11px] text-primary">
              Without the passphrase and without this phrase, the data is permanently unreadable.
              Primnox cannot recover it.
            </p>
            <label className="px-label mb-1 mt-4 block" htmlFor="cw">
              Re-type the phrase to confirm
            </label>
            <textarea id="cw" className={`${field} min-h-[3.5rem] resize-y`} value={confirmWords} onChange={(e) => setConfirmWords(e.target.value)} />
            <button className="px-btn mt-4" disabled={!ok} onClick={() => { setMnemonic(null); client.acknowledgeRecovery(); }}>
              I have saved it
            </button>
          </>
        ) : (
          <>
            <p className={sub}>
              The phrase was shown on the device where this vault was created. Continue there, or
              unlock on this device with your passphrase.
            </p>
            <button className="px-btn" onClick={() => client.acknowledgeRecovery()}>
              Continue
            </button>
          </>
        )}
      </div>
    );
  }

  return (
    <div className={wrap}>
      <h2 className="px-eyebrow mb-3">[ Unlock ]</h2>
      {mode === 'unlock' ? (
        <>
          <label className="px-label mb-1 block" htmlFor="up">
            Passphrase
          </label>
          <input
            id="up"
            className={field}
            type="password"
            value={pass}
            onChange={(e) => setPass(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void run(() => client.unlock(pass))()}
            autoComplete="current-password"
          />
          <div className="mt-4 flex gap-2">
            <button className="px-btn" disabled={busy || !pass} onClick={run(() => client.unlock(pass))}>
              {busy ? 'Deriving…' : 'Unlock'}
            </button>
            <button className="px-btn-ghost" onClick={() => { setMode('recover'); setError(null); }}>
              Use recovery phrase
            </button>
          </div>
        </>
      ) : (
        <>
          <label className="px-label mb-1 block" htmlFor="rp">
            Recovery phrase
          </label>
          <textarea id="rp" className={`${field} min-h-[3.5rem] resize-y`} value={recovery} onChange={(e) => setRecovery(e.target.value)} placeholder="24 words" />
          <div className="mt-4 flex gap-2">
            <button
              className="px-btn"
              disabled={busy || !isValidMnemonic(recovery)}
              onClick={run(async () => {
                await client.unlockWithMnemonic(recovery);
                setRecovery('');
              })}
            >
              Recover
            </button>
            <button className="px-btn-ghost" onClick={() => { setMode('unlock'); setError(null); }}>
              Back
            </button>
          </div>
        </>
      )}
      {error && <div className={err}>{error}</div>}
    </div>
  );
}
