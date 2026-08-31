import { useMemo, useRef, useState } from 'react';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import type { PrimnoxClient } from '../client';
import { STATUS_COPY } from '../lib/status';
import { turnsOf } from '../runtime/reducer';
import type { TurnRecord } from '../context/bundle';
import { toTurn } from '../lib/crs';
import { TrackRow } from '../components/TrackRow';
import { TurnBlock } from '../components/TurnBlock';
import { useRuntime } from './hooks';

const isDone = (s: string) => s === 'completed' || s === 'failed' || s === 'cancelled';

export function Chat({ client, conversationId }: { client: PrimnoxClient; conversationId: string }) {
  const state = useRuntime(client);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [fixId, setFixId] = useState<string | null>(null);
  const [bulkRetrying, setBulkRetrying] = useState(false);
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

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[var(--dr-plate-measure,72ch)] px-2 py-6 md:px-4">
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

      <div className="flex gap-2 border-t border-dr-rule bg-[var(--bg)] px-5 py-3">
        <textarea
          className="flex-1 resize-y border border-dr-rule-firm bg-[var(--bg)] px-2.5 py-2 font-mono text-[13px] text-on-surface outline-none focus-visible:border-primary"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder={open ? STATUS_COPY[open.status] ?? 'Working…' : 'Message'}
          rows={2}
        />
        <button className="px-btn self-stretch" disabled={!draft.trim() || sending || !!open} onClick={onSubmit}>
          Send
        </button>
      </div>
    </div>
  );
}
