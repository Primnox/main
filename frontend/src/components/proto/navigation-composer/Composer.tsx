/**
 * Extracted Composer Component
 *
 * Bottom-floating glass composer with text input, attachments, and controls.
 * DO-NOT-CHANGE: Layout overlays transcript (not in-flow), gradient scrim heights are px-based
 *
 * Props architecture allows decoupling from App.tsx state management.
 */

import { useRef, useEffect } from 'react';
import { AlertTriangle, ArrowUp, FileText, Loader2, Paperclip, Square, X } from 'lucide-react';
import { Panel } from '../../ui';

export type AttachmentStatus = 'ingesting' | 'failed' | 'ready';

export interface Attachment {
  id: string;
  name: string;
  status: AttachmentStatus;
}

export interface ModelInfo {
  model: string;
  local: boolean;
}

export interface ComposerProps {
  // Text input state
  draft: string;
  onDraftChange: (text: string) => void;

  // Attachments
  attachments: Attachment[];
  onRemoveAttachment: (id: string) => void;
  onAttachClick: () => void;
  attachmentDisabled?: boolean;
  attachmentDisabledReason?: string;

  // Send/Stop
  onSend: () => void | Promise<void>;
  onStop?: (turnId: string) => void | Promise<void>;
  sendDisabled?: boolean;
  liveTurnId?: string;

  // Conversation state
  conversationGone?: boolean;
  conversationIncognito?: boolean;

  // Model/Status info
  modelInfo?: ModelInfo;
  connectionStatus?: 'connected' | 'connecting' | 'offline';

  // IME composition guard
  isComposing?: boolean;
}

/**
 * Glass composer overlay for chat messages.
 *
 * Sits at the foot of the transcript and allows conversation to scroll behind it.
 * Backdrop-filter diffuses what's behind; gradient scrim ends the transcript visually.
 *
 * DO-NOT-CHANGE:
 * - absolute positioning (overlays, not in-flow)
 * - max-width 46rem (narrower than transcript's 72rem for focus)
 * - gradient stops in px, not % (typography-dependent)
 * - textarea max-height 160px (auto-grows up to this)
 * - Enter sends, Shift+Enter newlines (with isComposing guard for IME)
 */
export function Composer({
  draft,
  onDraftChange,
  attachments,
  onRemoveAttachment,
  onAttachClick,
  attachmentDisabled = false,
  attachmentDisabledReason,
  onSend,
  onStop,
  sendDisabled = false,
  liveTurnId,
  conversationGone = false,
  conversationIncognito = false,
  modelInfo,
  connectionStatus = 'connected',
  isComposing = false,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-height textarea on input
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
  }, [draft]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends (unless composing IME text like Japanese/Chinese)
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      onSend();
    }
  };

  // Model/status label text
  let statusLabel = 'connecting…';
  if (conversationIncognito) {
    statusLabel = 'incognito · no history, no files, no code';
  } else if (modelInfo) {
    statusLabel = `${modelInfo.model} · ${modelInfo.local ? 'local' : 'cloud'}`;
  } else if (connectionStatus === 'offline') {
    statusLabel = 'offline';
  }

  // Placeholder text
  const placeholderText = conversationGone
    ? 'This conversation has ended — start a new one'
    : 'Message Primnox…';

  return (
    // Container: absolute overlay at bottom, full width
    <div className="absolute inset-x-0 bottom-0 z-10 px-8 pb-6 pt-2 pointer-events-none [&_*]:pointer-events-auto">
      {/* Scrim: gradient background
          Transparent at top (lets transcript show), opaque at bottom (ground for glass)
          Stops are in px because textarea grows to 160px; percentages would drag the
          opaque band up. Opaque plateau runs to 54px (pb-6:24 + hint:15 + mt:10). */}
      <div
        aria-hidden="true"
        className="!pointer-events-none absolute inset-x-0 -top-14 bottom-0"
        style={{
          background:
            'linear-gradient(to top,' +
            ' var(--bg) 0px,' +
            ' var(--bg) 54px,' +
            ' color-mix(in srgb, var(--bg) 70%, transparent) 90px,' +
            ' color-mix(in srgb, var(--bg) 22%, transparent) 135px,' +
            ' transparent 190px)',
        }}
      />

      {/* Relative wrapper so panel paints over the scrim */}
      <div className="relative mx-auto w-full max-w-[46rem]">
        {/* Glass panel: composer sits at foot of transcript, conversation scrolls behind */}
        <Panel
          variant="glass"
          className="focus-within:border-on-surface/25 px-interactive"
        >
          {/* Attachment chips */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5 px-3.5 pt-3">
              {attachments.map((a) => (
                <span
                  key={a.id}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-on-surface/[0.12] text-[11px] text-on-surface/65"
                >
                  <FileText size={11} className="opacity-60" />
                  {a.name}
                  {a.status === 'ingesting' && (
                    <Loader2 size={9} className="animate-spin opacity-60" />
                  )}
                  {a.status === 'failed' && (
                    <AlertTriangle size={9} className="text-error" />
                  )}
                  <button
                    onClick={() => onRemoveAttachment(a.id)}
                    aria-label={`Remove ${a.name}`}
                    className="opacity-40 hover:opacity-100 transition-opacity"
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Text input */}
          <label htmlFor="composer" className="sr-only">
            Message Primnox
          </label>
          <textarea
            ref={textareaRef}
            id="composer"
            value={draft}
            disabled={conversationGone}
            onChange={(e) => {
              onDraftChange(e.target.value);
              e.target.style.height = 'auto';
              e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
            }}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder={placeholderText}
            className="w-full bg-transparent text-on-surface/90 placeholder-on-surface/25 text-sm resize-none leading-6 min-h-[24px] max-h-[160px] px-4 pt-3.5 pb-1 outline-none [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          />

          {/* Control row */}
          <div className="flex items-center gap-1.5 px-2.5 pb-2.5">
            {/* File attachment button */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                /* Handled via onAttachClick callback */
              }}
            />
            <button
              onClick={onAttachClick}
              aria-label="Attach a file"
              disabled={attachmentDisabled}
              title={attachmentDisabledReason}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.06] transition duration-150 disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-on-surface/50 disabled:cursor-not-allowed"
            >
              <Paperclip size={15} />
            </button>

            {/* Model/Status label */}
            <span className="px-label px-1 text-[12px] text-on-surface/65">
              {statusLabel}
            </span>

            {/* Spacer */}
            <div className="flex-1" />

            {/* Stop button (if live turn) */}
            {liveTurnId && onStop && (
              <button
                onClick={() => onStop(liveTurnId)}
                aria-label="Stop generating"
                className="w-8 h-8 rounded-lg flex items-center justify-center bg-on-surface/[0.09] hover:bg-on-surface/[0.14] transition duration-150"
              >
                <Square size={13} className="fill-current" />
              </button>
            )}

            {/* Send button */}
            <button
              onClick={onSend}
              disabled={sendDisabled || conversationGone}
              aria-label="Send message"
              className="w-8 h-8 rounded-lg flex items-center justify-center transition duration-150
                disabled:bg-on-surface/5 disabled:text-on-surface/50 disabled:cursor-not-allowed
                enabled:bg-primary enabled:text-surface enabled:hover:opacity-80 enabled:active:scale-95"
            >
              <ArrowUp size={16} strokeWidth={2.5} />
            </button>
          </div>
        </Panel>

        {/* Keyboard hint */}
        <p className="px-label mt-2.5 text-center normal-case tracking-[0.1em] text-[11px] text-on-surface/55">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
