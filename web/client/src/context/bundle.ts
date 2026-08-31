/* Context Bundle builder (CRS/ARCH §4.1, CRS/1.0-W §4.8).

   Runs in the browser. Takes already-decrypted pieces — history, retrieved
   memory, attached asset text, open workspace files — and assembles the
   plaintext prompt that goes straight to the provider. Render never sees this.

   Trimming is oldest-first on history: the system block, the retrieved
   context, and the new user message are never dropped; older turns are. */

import { ChatMessage } from '../model';

export interface TurnRecord {
  role: 'user' | 'assistant';
  text: string;
}
export interface MemoryHit {
  text: string;
}
export interface AssetText {
  name: string;
  text: string;
}
export interface WorkspaceFile {
  path: string;
  content: string;
}

export interface BundleInput {
  systemPrompt: string;
  history: TurnRecord[]; // oldest → newest, excluding the new message
  memory?: MemoryHit[];
  assets?: AssetText[];
  workspaceFiles?: WorkspaceFile[];
  userText: string;
  /** total input budget in tokens; history is trimmed to fit under it */
  budgetTokens?: number;
}

export interface Bundle {
  system: string;
  messages: ChatMessage[];
  droppedTurns: number;
  approxTokens: number;
}

const DEFAULT_BUDGET = 60_000;
const KEEP_MIN_TURNS = 2; // always keep at least this many recent history turns

const est = (s: string): number => Math.ceil(s.length / 4);

export function buildBundle(input: BundleInput): Bundle {
  const system = composeSystem(input);

  const full: ChatMessage[] = [
    ...input.history.map((t) => ({ role: t.role, content: t.text }) as ChatMessage),
    { role: 'user', content: input.userText },
  ];

  const budget = input.budgetTokens ?? DEFAULT_BUDGET;
  const fixed = est(system) + est(input.userText);

  // trim oldest history turns until under budget (or at the keep-floor)
  let start = 0;
  const historyCount = input.history.length;
  const tokensFrom = (from: number): number => {
    let t = fixed;
    for (let i = from; i < historyCount; i++) t += est(input.history[i]!.text) + 4;
    return t;
  };
  while (start < historyCount - KEEP_MIN_TURNS && tokensFrom(start) > budget) {
    start++;
  }

  const messages: ChatMessage[] = [
    ...input.history.slice(start).map((t) => ({ role: t.role, content: t.text }) as ChatMessage),
    { role: 'user', content: input.userText },
  ];

  const approxTokens =
    est(system) + messages.reduce((sum, m) => sum + est(m.content) + 4, 0);

  return { system, messages, droppedTurns: start, approxTokens };
}

function composeSystem(input: BundleInput): string {
  const parts: string[] = [input.systemPrompt.trim()];

  if (input.memory?.length) {
    parts.push(
      ['## Relevant memory', ...input.memory.map((m) => `- ${m.text}`)].join('\n'),
    );
  }

  if (input.assets?.length) {
    parts.push(
      [
        '## Attached documents',
        ...input.assets.map((a) => `### ${a.name}\n${a.text.trim()}`),
      ].join('\n\n'),
    );
  }

  if (input.workspaceFiles?.length) {
    parts.push(
      [
        '## Workspace',
        ...input.workspaceFiles.map((f) => `\`\`\`${f.path}\n${f.content}\n\`\`\``),
      ].join('\n\n'),
    );
  }

  return parts.filter(Boolean).join('\n\n');
}
