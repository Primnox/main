/**
 * Renders the structured response blocks that can accompany a reply:
 *   - `card` / `buttons` — embedded by the model itself (see
 *     backend/system_prompts.py's RESPONSE FORMATTING guidance and
 *     backend/core.py's fenced-block extraction).
 *   - `tool_call` / `tool_result` — emitted by backend/brain.py whenever the
 *     model actually runs something, so the exact code/command and its real
 *     output are visible in the transcript rather than a transient "using:
 *     run shell" toast that disappears and isn't saved with the message.
 *
 * Styling mirrors existing precedents rather than inventing new visual
 * language: the pill-button row from DynamicIsland's Proactive Alert
 * (suggestions -> sendMessage), and the title/description card row from
 * CommandPalette's actionable list items.
 */

import { useState } from 'react';

export interface StructuredAction {
  label: string;
  action: string;
}

export interface CardBlock {
  type: 'card';
  title?: string;
  content?: string;
  actions?: StructuredAction[];
}

export interface ButtonsBlock {
  type: 'buttons';
  buttons?: StructuredAction[];
}

export interface ToolCallBlock {
  type: 'tool_call';
  name?: string;
  args?: Record<string, unknown>;
}

export interface ToolResultBlock {
  type: 'tool_result';
  name?: string;
  output?: string;
  truncated?: boolean;
}

export type StructuredBlockData =
  | CardBlock
  | ButtonsBlock
  | ToolCallBlock
  | ToolResultBlock;

/** Tools whose single most useful argument IS the thing that ran — show it
 *  as a code block rather than a JSON dump of `{"code": "..."}`. */
const CODE_ARG_BY_TOOL: Record<string, string> = {
  run_python: 'code',
  run_shell: 'code',
};

const prettyToolName = (name?: string) => (name || 'tool').replace(/_/g, ' ');

const CodeSurface = ({ text }: { text: string }) => (
  <pre className="px-3 py-2 text-[11px] leading-[1.5] font-mono text-on-surface/80 bg-on-surface/[0.04] rounded-lg overflow-x-auto whitespace-pre-wrap break-words">
    {text}
  </pre>
);

const ToolCall = ({ block }: { block: ToolCallBlock }) => {
  const [open, setOpen] = useState(true);
  const args = block.args || {};
  const codeKey = CODE_ARG_BY_TOOL[block.name || ''];
  const code = codeKey ? (args[codeKey] as string | undefined) : undefined;
  const rest = codeKey
    ? Object.fromEntries(Object.entries(args).filter(([k]) => k !== codeKey))
    : args;
  const hasRest = Object.keys(rest).length > 0;

  return (
    <div className="rounded-xl border border-on-surface/10 bg-on-surface/[0.03] overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-on-surface/[0.03] transition-colors"
      >
        <span className="text-[10px] text-on-surface/40">{open ? '▾' : '▸'}</span>
        <span className="text-[11px] font-medium text-primary/80">
          ran {prettyToolName(block.name)}
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-1.5">
          {code !== undefined && <CodeSurface text={String(code)} />}
          {hasRest && <CodeSurface text={JSON.stringify(rest, null, 2)} />}
          {code === undefined && !hasRest && (
            <div className="text-[11px] text-on-surface/40 px-1">no arguments</div>
          )}
        </div>
      )}
    </div>
  );
};

const ToolResult = ({ block }: { block: ToolResultBlock }) => {
  const [open, setOpen] = useState(false);
  const output = (block.output || '').trim();
  if (!output) return null;

  return (
    <div className="rounded-xl border border-on-surface/10 bg-on-surface/[0.03] overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-on-surface/[0.03] transition-colors"
      >
        <span className="text-[10px] text-on-surface/40">{open ? '▾' : '▸'}</span>
        <span className="text-[11px] font-medium text-on-surface/60">
          output{block.truncated ? ' (truncated)' : ''}
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3">
          <CodeSurface text={output} />
        </div>
      )}
    </div>
  );
};

const PillButton = ({ label, onClick }: { label: string; onClick: () => void }) => (
  <button
    onClick={onClick}
    className="px-3 py-1.5 rounded-full bg-on-surface/5 border border-on-surface/10 text-[11px] font-medium text-on-surface/70 hover:bg-primary/20 hover:text-primary hover:border-primary/30 transition-all"
  >
    {label}
  </button>
);

export const StructuredBlock = ({
  blocks,
  onAction,
}: {
  blocks?: StructuredBlockData[] | null;
  onAction: (action: string) => void;
}) => {
  if (!blocks || !blocks.length) return null;

  return (
    <div className="space-y-2 mb-2">
      {blocks.map((block, i) => {
        if (block.type === 'card') {
          return (
            <div key={i} className="rounded-xl border border-on-surface/10 bg-on-surface/[0.03] overflow-hidden">
              <div className="px-4 py-3">
                {block.title && (
                  <div className="text-sm font-medium text-on-surface/90 mb-1">{block.title}</div>
                )}
                {block.content && (
                  <div className="text-[12px] text-on-surface/60 leading-5">{block.content}</div>
                )}
              </div>
              {!!block.actions?.length && (
                <div className="flex flex-wrap gap-1.5 px-4 pb-3">
                  {block.actions.map((a, j) => (
                    <PillButton key={j} label={a.label} onClick={() => onAction(a.action)} />
                  ))}
                </div>
              )}
            </div>
          );
        }
        if (block.type === 'buttons') {
          return (
            <div key={i} className="flex flex-wrap gap-1.5">
              {(block.buttons || []).map((b, j) => (
                <PillButton key={j} label={b.label} onClick={() => onAction(b.action)} />
              ))}
            </div>
          );
        }
        if (block.type === 'tool_call') return <ToolCall key={i} block={block} />;
        if (block.type === 'tool_result') return <ToolResult key={i} block={block} />;
        return null;
      })}
    </div>
  );
};
