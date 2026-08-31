import { useMemo, useRef, useState } from 'react';
import {
  AlertTriangle, ArrowUp, Loader2, PanelLeftOpen, PanelRight, Paperclip, RefreshCw, Square,
} from 'lucide-react';
import type { PrimnoxClient } from '../client';
import { STATUS_COPY } from '../lib/status';
import { turnsOf } from '../runtime/reducer';
import type { TurnRecord } from '../context/bundle';
import { toTurn } from '../lib/crs';
import { Panel } from '../components/ui';
import { ContextRail } from '../components/ContextRail';
import { TrackRow } from '../components/TrackRow';
import { TurnBlock } from '../components/TurnBlock';
import { useRuntime } from './hooks';

const isDone = (s: string) => s === 'completed' || s === 'failed' || s === 'cancelled';

export function Chat({
  client,
  conversationId,
  title,
  chatsOpen,
  connected = false,
  onShowChats,
  onOpenSettings,
}: {
  client: PrimnoxClient;
  conversationId: string;
  title?: string;
  chatsOpen?: boolean;
  connected?: boolean;
  onShowChats?: () => void;
  onOpenSettings?: () => void;
}) {
  const state = useRuntime(client);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [fixId, setFixId] = useState<string | null>(null);
  const [bulkRetrying, setBulkRetrying] = useState(false);
  const [railOpen, setRailOpen] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);

  const turns = useMemo(() => turnsOf(state, conversationId), [state, conversationId]);
  const open = turns.find((t) => !isDone(t.status));

  const historyUpTo = (turnId?: string): TurnRecord[] => {
    const out: TurnRecord[] = [];
    for (const t of turns) {
      if (turnId && t.id === turnId) break;
      if (t.status !== 'completed') continue;
      if (t.userText) out.push({ role: 'user', text: t.userText });
      if (t.assistantText) out.push({ role: 'assistant', text: t.assistantText });
    }
    return out;
  };

  const send = async (text: string, history: TurnRecord[]) => {
    setSending(true);
    try {
      await client.send(conversationId, text, { history });
    } finally {
      setSending(false);
      requestAnimationFrame(() => endRef.current?.scrollIntoView({ block: 'end' }));
    }
  };

  const onSubmit = () => {
    const text = draft.trim();
    if (!text || sending || open) return;
    setDraft('');
    void send(text, historyUpTo());
  };

  const onRetry = (turnId: string) => {
    const t = turns.find((x) => x.id === turnId);
    if (t?.userText) void send(t.userText, historyUpTo(turnId));
  };

  const failedRetryable = turns.filter((t) => t.status === 'failed' && t.error?.retryable !== false);
  const retryAll = async () => {
    setBulkRetrying(true);
    try {
      for (const t of failedRetryable) {
        if (t.userText) await send(t.userText, historyUpTo(t.id));
      }
    } finally {
      setBulkRetrying(false);
    }
  };

  const fixIndex = fixId ? turns.findIndex((t) => t.id === fixId) : -1;
  const keys = client.listProviderKeys();
  const routed = keys[0];
  const rendered = useMemo(() => turns.map(toTurn), [turns]);
  const liveTurn = open ? toTurn(open) : undefined;

  return (
    <>
    <main className="relative flex-1 flex flex-col min-w-0">
      {/* The ground the glass sits on. Glass only reads as glass when there is
          something behind it worth seeing through to. Coloured from --primary /
          --accent / --green, so they follow the palette. */}
      <div className="orb orb-1" aria-hidden="true" />
      <div className="orb orb-2" aria-hidden="true" />
      <div className="orb orb-3" aria-hidden="true" />

      <header className="relative z-10 h-14 shrink-0 flex items-center justify-between gap-3 px-8 border-b border-on-surface/[0.07]">
        {/* The way back, where a way back belongs: at the edge the panel
            retracted into. The rail's Chats button also restores it, but
            nothing about an icon for the section you are already in says "this
            reveals the list" — that was reachable, not discoverable. */}
        {!chatsOpen && onShowChats && (
          <button onClick={onShowChats}
            aria-label="Show conversations" aria-expanded={false}
            title="Show conversations"
            className="px-interactive -ml-3 shrink-0 p-1.5 rounded-lg text-on-surface/50
                       hover:text-on-surface hover:bg-on-surface/[0.05]">
            <PanelLeftOpen size={16} aria-hidden="true" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <span className="px-eyebrow block">Conversation</span>
          {/* Display type is for hero moments. A chat title is a label for the
              thing you are already looking at. */}
          <h1 className="font-display font-bold text-[14px] uppercase tracking-[0.02em]
                         text-on-surface/85 truncate flex items-center gap-2 leading-tight">
            {title || 'New Chat'}
          </h1>
        </div>
        {/* Mirrors the sidebar's own show-control on the opposite edge, so both
            sides of the app behave alike. */}
        {!railOpen && (
          <button onClick={() => setRailOpen(true)}
            aria-label="Show context panel" aria-expanded={false}
            title="Show context panel"
            className="px-interactive hidden xl:block shrink-0 -mr-1 p-1.5 rounded-lg text-on-surface/50
                       hover:text-on-surface hover:bg-on-surface/[0.05]">
            <PanelRight size={16} aria-hidden="true" />
          </button>
        )}
      </header>

      <div className="relative z-10 flex-1 min-h-0 overflow-y-auto custom-scrollbar">
        <div className="mx-auto w-full max-w-[46rem] px-2 py-6 md:px-4">
          {turns.length === 0 && (
            <p className="px-label pl-[var(--dr-rail-w)] md:pl-[var(--dr-rail-w-wide)]">
              No legs plotted. Ask something.
            </p>
          )}

          {failedRetryable.length >= 2 && (
            <div className="mb-4 ml-[var(--dr-rail-w)] flex items-center gap-3 border border-error/25 bg-error/[0.06] px-4 py-3 md:ml-[var(--dr-rail-w-wide)]">
              <AlertTriangle size={15} className="shrink-0 text-error" />
              <p className="px-body flex-1 text-sm">
                {bulkRetrying
                  ? 'Retrying the failed legs…'
                  : `${failedRetryable.length} legs failed the same way.`}
              </p>
              <button
                type="button"
                onClick={() => void retryAll()}
                disabled={bulkRetrying}
                className="px-interactive flex shrink-0 items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-error hover:bg-error/[0.16] disabled:opacity-60"
              >
                {bulkRetrying ? <Loader2 size={12} className="px-spin" /> : <RefreshCw size={12} />}
                Retry all {failedRetryable.length}
              </button>
            </div>
          )}

          {turns.map((t, i) => {
            const turn = toTurn(t);
            return (
              <TrackRow
                key={t.id}
                turn={turn}
                index={i}
                isFix={i === fixIndex}
                drift={fixIndex === -1 ? i + 1 : Math.max(0, i - fixIndex)}
                onFix={(id) => setFixId((cur) => (cur === id ? null : id))}
              >
                <TurnBlock turn={turn} onRetry={onRetry} />
              </TrackRow>
            );
          })}
          <div ref={endRef} />
        </div>
      </div>

      {/* ── Composer ──────────────────────────────────────────────────────
          The ground rises behind it: transparent well above, opaque from the
          panel's lower edge down, so the glass has something to diffuse and
          nothing under it competes with the composer. Stops are in px from the
          bottom, not percentages — the textarea grows to 160px and percentage
          stops would drag the opaque band up across the panel as it grew. */}
      <div className="relative z-10 shrink-0 px-4 pb-6">
        <div aria-hidden="true"
             className="!pointer-events-none absolute inset-x-0 -top-14 bottom-0"
             style={{
               background:
                 'linear-gradient(to top,'
                 + ' var(--bg) 0px,'
                 + ' var(--bg) 54px,'
                 + ' color-mix(in srgb, var(--bg) 70%, transparent) 90px,'
                 + ' color-mix(in srgb, var(--bg) 22%, transparent) 135px,'
                 + ' transparent 190px)',
             }} />
        {/* `relative` so the panel paints over the scrim. */}
        <div className="relative mx-auto w-full max-w-[46rem]">
          <Panel variant="glass"
            className="focus-within:border-on-surface/25 px-interactive">
            <label htmlFor="composer" className="sr-only">Message Primnox</label>
            <textarea
              id="composer"
              value={draft}
              onChange={e => {
                setDraft(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
              }}
              onKeyDown={e => {
                // isComposing: while composing Japanese, Chinese or Korean text
                // Enter confirms the candidate word, and without this guard it
                // would also fire a half-written message.
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  onSubmit();
                }
              }}
              rows={1}
              placeholder={open ? STATUS_COPY[open.status] ?? 'Working…' : 'Message Primnox…'}
              className="w-full bg-transparent text-on-surface/90 placeholder-on-surface/25 text-sm resize-none leading-6 min-h-[24px] max-h-[160px] px-4 pt-3.5 pb-1 outline-none [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            />
            <div className="flex items-center gap-1.5 px-2.5 pb-2.5">
              {/* Disabled rather than hidden, and it says why. A control that
                  quietly vanishes reads as a bug. Web has no asset store yet —
                  an upload would have nowhere to land. */}
              <button
                aria-label="Attach a file"
                disabled
                title="Attachments need an asset store, which Primnox Web does not have yet"
                className="w-8 h-8 rounded-lg flex items-center justify-center text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.06] transition duration-150 disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-on-surface/50 disabled:cursor-not-allowed">
                <Paperclip size={15} />
              </button>
              {/* A real control, not label text styled to look like one. The one
                  place to actually change the route is Settings → Provider, so
                  that is where this goes. */}
              <button
                type="button"
                onClick={onOpenSettings}
                title="Change the model or provider"
                className="px-label px-1 rounded hover:text-on-surface hover:bg-on-surface/[0.06] transition duration-150 cursor-pointer">
                {routed ? `${routed.model} · ${routed.provider}` : 'no provider — add a key'}
              </button>
              <div className="flex-1" />
              {/* Stop and Send coexist. Turns are independent objects, so a new
                  message while one is still running is legitimate. */}
              {open && (
                <button onClick={() => client.cancel(open.id)}
                  aria-label="Stop generating"
                  className="w-8 h-8 rounded-lg flex items-center justify-center bg-on-surface/[0.09] hover:bg-on-surface/[0.14] transition duration-150">
                  <Square size={13} className="fill-current" />
                </button>
              )}
              <button onClick={onSubmit} disabled={!draft.trim() || sending || !!open}
                aria-label="Send message"
                className="w-8 h-8 rounded-lg flex items-center justify-center transition duration-150
                  disabled:bg-on-surface/5 disabled:text-on-surface/50 disabled:cursor-not-allowed
                  enabled:bg-primary enabled:text-surface enabled:hover:opacity-80 enabled:active:scale-95">
                <ArrowUp size={16} strokeWidth={2.5} />
              </button>
            </div>
          </Panel>
          <p className="px-label mt-2.5 text-center normal-case tracking-[0.1em]">
            Enter to send · Shift+Enter for new line
          </p>
        </div>
      </div>
    </main>

    {/* Inline from 1280px up, where there is room for a third column. Below
        that the transcript needs the width more than the diagnostics do. */}
    {railOpen && (
      <div className="hidden xl:block shrink-0">
        <ContextRail
          turns={rendered}
          cursor={state.cursor}
          connected={connected}
          synced={connected}
          liveTurn={liveTurn}
          model={routed ? { provider: routed.provider, model: routed.model } : null}
          onClose={() => setRailOpen(false)}
        />
      </div>
    )}
    </>
  );
}
