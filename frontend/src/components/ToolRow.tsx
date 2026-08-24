import { AlertTriangle, Check, Loader2 } from 'lucide-react';
import { type ToolCall } from '../lib/crs';

export function ToolRow({ call }: { call: ToolCall }) {
  return (
    <div className="mb-2 flex items-center gap-2.5 text-[11px]">
      {call.status === 'running'
        ? <Loader2 size={11} className="px-spin text-on-surface/50 shrink-0" />
        : call.status === 'error'
          ? <AlertTriangle size={11} className="text-error shrink-0" />
          : <Check size={11} className="text-primary shrink-0" />}
      <span className="font-mono text-on-surface/70">{call.name}</span>
      {call.summary && <span className="text-on-surface/50 truncate">{call.summary}</span>}
    </div>
  );
}

/* ── Built-in viewers ──────────────────────────────────────────────────────
   Everything Primnox can produce, readable without leaving the app and
   without downloading it first.

   Read-only by construction, not by discipline: this renders text nodes and
   nothing else. There is no input, no contenteditable, and no endpoint behind
   it that writes — the server's preview layer only reads. PDFs and images go
   straight to the browser, which already knows them; Word, Excel, PowerPoint
   and SQLite are parsed server-side by the same libraries that wrote them,
   which is why this file needs no new dependency to read any of them. */
