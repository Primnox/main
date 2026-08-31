/* Compat shim so the ported desktop components (TurnBlock, TrackRow,
   RecoveryBlock, …) run unchanged against the web runtime.

   Desktop's crs.ts is a WebSocket client + pure-fold reducer talking to a
   loopback backend. On web that job is done by CRS/1.0-W: the browser produces
   events, seals them, and folds decrypted ones through runtime/reducer.ts.
   This module only re-exposes the `Turn` shape those components read, plus a
   mapper from the web `TurnState`. */

import type { TurnState } from '../runtime/reducer';

export type TurnStatus =
  | 'queued'
  | 'building_context'
  | 'thinking'
  | 'streaming'
  | 'tool_running'
  | 'awaiting_input'
  | 'completed'
  | 'failed'
  | 'cancelled';

export const TERMINAL: TurnStatus[] = ['completed', 'failed', 'cancelled'];

export type TurnError = {
  code: string;
  message: string;
  retryable: boolean;
  attempt?: number;
};

export type ToolCall = { name: string; status: string; arguments?: unknown; summary?: string };
export type ScrubItem = { original: string; placeholder: string; label: string };
export type Execution = {
  id: string;
  runtime: string;
  status: string;
  summary: string;
  output: string[];
  changes: { created: string[]; modified: string[]; deleted: string[] } | null;
  artifacts: { asset_id: string; name: string; path: string; bytes: number }[];
};
export type PermissionRequest = {
  id: string;
  action: string;
  detail: string;
  options: { id: string; label: string }[];
  auto: boolean;
  resolved: string | null;
};
export type UserQuestion = {
  id: string;
  question: string;
  options: { id: string; label: string }[];
  answered: string | null;
};

/* Desktop-tool calls rendered by a timeline rather than generic rows. Empty on
   web (Computer Use is desktop-only), kept so TurnBlock's filter compiles. */
export const COMPUTER_TOOLS = new Set<string>();

export type Turn = {
  id: string;
  status: TurnStatus;
  userText: string;
  assistantText: string;
  thinking: string;
  partial: boolean;
  error: TurnError | null;
  plan: string | null;
  toolCalls: ToolCall[];
  executions: Execution[];
  workspaces: { id: string; title: string; kind: string; version: number }[];
  assets: { id: string; name: string; kind: string }[];
  permissions: PermissionRequest[];
  questions: UserQuestion[];
  computer: unknown[];
  privacyScrub: ScrubItem[];
  createdAt: number;
};

/** Map a web runtime turn to the shape the ported components read. Phase 1 has
    no tools / assets / canvas / thinking / privacy, so those are empty. */
export function toTurn(t: TurnState): Turn {
  return {
    id: t.id,
    status: t.status as TurnStatus,
    userText: t.userText ?? '',
    assistantText: t.assistantText,
    thinking: '',
    partial: t.cancelled,
    error: t.error ? { ...t.error } : null,
    plan: null,
    toolCalls: [],
    executions: [],
    workspaces: [],
    assets: [],
    permissions: [],
    questions: [],
    computer: [],
    privacyScrub: [],
    createdAt: t.createdAt,
  };
}
