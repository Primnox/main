import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, ExternalLink, Loader2, RotateCw } from 'lucide-react';
import { api, type OmniRouteStatus } from '../lib/crs';
import { SectionHeader } from './ui';
import { GuideInline } from './GuideInline';

/* OmniRoute — how Primnox reaches every hosted model.
 *
 * WHAT THIS REPLACED. For a while Primnox shipped OmniRoute's catalogue: 346
 * providers, ported out of their source into our schema. It was the wrong
 * thing to build. Only 103 of them carried an endpoint we could actually call,
 * and keeping the rest current would have meant tracking someone else's
 * release cycle by hand, forever, to stay a worse copy of it.
 *
 * So Primnox points at OmniRoute rather than impersonating it. One endpoint,
 * and the providers behind it are OmniRoute's to maintain — including the
 * keys, which now live there instead of in our keyring, and the 290-provider
 * dashboard, which is a whole product we were never going to out-build inside
 * a settings tab.
 *
 * NOT INSTALLED IS A NORMAL STATE, NOT AN ERROR. On a fresh machine this is
 * the expected answer, so it renders as one command and a reason rather than
 * as a red failure. What is NOT normal — and is called out separately — is
 * OmniRoute running with nothing connected to it: reachable with zero models
 * looks identical to healthy from a status code, and sending a turn into it
 * fails in a way that reads as Primnox's fault.
 */

const CHANNEL_NOTE: Record<string, string> = {
  'auto': 'Balanced. Sticks to the last provider that worked.',
  'auto/coding': 'Weighted toward quality for code.',
  'auto/fast': 'Lowest latency first.',
  'auto/cheap': 'Cheapest per token first.',
  'auto/offline': 'Most quota headroom first.',
  'auto/smart': 'Quality first, with some exploration.',
};

export function OmniRoute({ onChanged }: { onChanged: () => void }) {
  const [status, setStatus] = useState<OmniRouteStatus | null>(null);
  const [probing, setProbing] = useState(true);
  const [copied, setCopied] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [active, setActive] = useState<string>('');

  const probe = useCallback(async () => {
    setProbing(true);
    try { setStatus(await api.omnirouteStatus()); }
    catch { setStatus(null); }
    finally { setProbing(false); }
  }, []);

  useEffect(() => {
    probe();
    api.models().then((d: any) => {
      const row = (d.profiles ?? []).find((p: any) => p.name === (d.primary ?? 'OmniRoute'));
      if (row) setActive(row.model ?? '');
    }).catch(() => undefined);
  }, [probe]);

  const copy = useCallback(() => {
    navigator.clipboard?.writeText(status?.install ?? '');
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }, [status]);

  const chooseChannel = useCallback(async (channel: string) => {
    setChoosing(true);
    try {
      await api.useModel('OmniRoute', channel);
      setActive(channel);
      onChanged();
    } finally { setChoosing(false); }
  }, [onChanged]);

  const running = !!status?.running;
  const empty = running && !status?.configured;

  return (
    <section className="space-y-3">
      <SectionHeader title="OmniRoute" level={3}
        note="Primnox's route to every hosted model. It runs on this machine and forwards to whichever provider it picks, so your keys live there rather than here."
        right={
          <button onClick={probe} aria-label="Check OmniRoute again"
            className="px-interactive p-1.5 text-on-surface/50 hover:text-on-surface">
            {probing ? <Loader2 size={12} className="px-spin" /> : <RotateCw size={12} />}
          </button>
        } />

      <div className="border border-on-surface/[0.12]">
        <div className="flex items-center gap-2.5 border-b border-on-surface/[0.07] px-4 py-3">
          <span className={`h-1.5 w-1.5 shrink-0 ${running ? (empty ? 'bg-warn' : 'bg-success') : 'bg-on-surface/30'}`}
            aria-hidden="true" />
          <span className="text-[13px]">
            {probing ? 'Looking for it…'
              : !running ? 'Not installed'
                : empty ? 'Running, but no providers connected'
                  : 'Running'}
          </span>
          {running && !empty && (
            <span className="px-label">
              {status!.model_count} model{status!.model_count === 1 ? '' : 's'}
            </span>
          )}
          <span className="ml-auto truncate font-mono text-[10px] text-on-surface/50">
            {status?.host ?? ''}
          </span>
          {running && (
            <a href={status!.dashboard} target="_blank" rel="noreferrer noopener"
              className="px-interactive flex shrink-0 items-center gap-1 font-mono text-[10px]
                         uppercase tracking-[0.12em] text-on-surface/50 hover:text-on-surface">
              Dashboard <ExternalLink size={10} />
            </a>
          )}
        </div>

        {/* Not installed. One command and the reason it is worth running,
            rather than a red error for the expected state of a fresh machine. */}
        {!running && !probing && (
          <div className="space-y-2.5 px-4 py-3">
            <p className="text-[11px] leading-relaxed text-on-surface/70">
              Primnox needs OmniRoute to reach hosted models. It is a local
              gateway that fronts around 290 providers behind one endpoint, so
              Primnox does not have to carry a provider catalogue of its own —
              and your API keys stay in it rather than in this app.
            </p>
            <div className="flex items-center gap-2 border border-on-surface/[0.12] px-3 py-2">
              <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-on-surface/85">
                {status?.install ?? 'npm install -g omniroute && omniroute'}
              </code>
              <button onClick={copy} aria-label="Copy the install command"
                className="px-interactive flex shrink-0 items-center gap-1.5 font-mono text-[10px]
                           uppercase tracking-[0.12em] text-on-surface/50 hover:text-on-surface">
                {copied ? <Check size={11} /> : <Copy size={11} />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <p className="text-[11px] text-on-surface/50">
              Until then Primnox still works against a local model — Ollama needs
              no account and no network. Set OMNIROUTE_HOST to reach an instance
              on another machine.
            </p>
          </div>
        )}

        {/* Reachable with nothing behind it. A status code cannot tell this
            apart from healthy, and a turn sent into it fails in a way that
            reads as Primnox being broken. */}
        {empty && (
          <div className="space-y-2 px-4 py-3">
            <p className="text-[11px] leading-relaxed text-warn">
              OmniRoute is answering but has no providers configured, so it has
              nothing to route to. A message sent now fails inside the gateway,
              which looks like a Primnox error and is not one.
            </p>
            <a href={status!.dashboard} target="_blank" rel="noreferrer noopener"
              className="px-interactive inline-flex items-center gap-1.5 border border-on-surface/[0.12]
                         px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em]
                         text-on-surface/70 hover:text-on-surface">
              Connect one <ExternalLink size={10} />
            </a>
          </div>
        )}

        {running && !empty && (
          <div className="space-y-2 px-4 py-3">
            <p className="px-label">Routing channel</p>
            {/* Channels, not the model list. A named model pins the turn to one
                provider and gives up the fallback that is the reason to run a
                gateway at all — so the 290 models are one click away in
                OmniRoute's dashboard, and this offers the six that route. */}
            <div className="flex flex-wrap gap-1.5">
              {(status!.channels.length ? status!.channels : ['auto']).map(c => (
                <button key={c} onClick={() => chooseChannel(c)} disabled={choosing}
                  aria-pressed={active === c}
                  title={CHANNEL_NOTE[c] ?? ''}
                  className={`px-interactive border px-2.5 py-1 font-mono text-[10px]
                              uppercase tracking-[0.12em] transition duration-150 disabled:opacity-50
                    ${active === c
                      ? 'border-primary text-primary'
                      : 'border-on-surface/[0.12] text-on-surface/60 hover:text-on-surface'}`}>
                  {c}
                </button>
              ))}
            </div>
            {CHANNEL_NOTE[active] && (
              <p className="text-[11px] text-on-surface/50">{CHANNEL_NOTE[active]}</p>
            )}
          </div>
        )}
      </div>

      <GuideInline slug="choosing-a-provider" label="Gateway or local — which do I want?" />
    </section>
  );
}
