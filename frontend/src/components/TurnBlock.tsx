import { useContext } from 'react';
import { motion } from 'motion/react';
import { AlertTriangle, Ban, Loader2, RotateCw, Terminal } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { COMPUTER_TOOLS, TERMINAL, api, type Turn } from '../lib/crs';
import { CanvasContext, ViewerContext } from '../lib/contexts';
import { MD } from '../lib/md';
import { STATUS_COPY } from '../lib/status';
import { Attachment } from './Attachment';
import { Canvas } from './Canvas';
import { CopyButton } from './CopyButton';
import { QuestionBlock } from './QuestionBlock';
import { formatElapsed, useElapsed } from '../lib/useElapsed';
import { ExecutionBlock } from './ExecutionBlock';
import { PermissionBlock } from './PermissionBlock';
import { PlanBlock } from './PlanBlock';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolRow } from './ToolRow';

/* What a turn says about itself while it is still running.
 *
 * The spinner alone could not do this job. It is a CSS animation, so it turns
 * at the same rate whether tokens are arriving, the provider has hung, or the
 * socket has dropped — "working" and "wedged" rendered identically, and on a
 * local 7B that partially offloads to CPU the honest answer is often "working,
 * slowly". The elapsed count can only advance if the turn is genuinely still
 * open, so it is the part that carries information.
 *
 * `aria-live="polite"` with the seconds deliberately OUTSIDE it: announcing a
 * new number every second would make a screen reader unusable. The status word
 * is what gets announced, when it changes.
 */
function LiveStatus({ turn }: { turn: Turn }) {
  const seconds = useElapsed(turn.createdAt, true);
  return (
    <p className="px-label mb-2 flex items-center gap-1.5">
      <Loader2 size={10} className="px-spin" aria-hidden="true" />
      <span aria-live="polite">{STATUS_COPY[turn.status] ?? turn.status}</span>
      {seconds > 0 && (
        <span className="tabular-nums text-on-surface/50" aria-hidden="true">
          · {formatElapsed(seconds)}
        </span>
      )}
    </p>
  );
}

export function TurnBlock({ turn }: { turn: Turn }) {
  const live = !TERMINAL.includes(turn.status);
  const openAsset = useContext(ViewerContext);
  const openCanvas = useContext(CanvasContext);
  /* The entrance uses the full transform string, not Motion's `y` shorthand.
     The shorthand is not hardware-accelerated: it runs on the main thread,
     and this is the one entrance that fires on every single turn, while
     tokens are still streaming into the element above it. `translate3d`
     keeps it on the compositor. ease-out because it is an entrance - the
     first frame is the one being watched. */
  return (
    <motion.div
      initial={{ opacity: 0, transform: 'translate3d(0, 8px, 0)' }}
      animate={{ opacity: 1, transform: 'translate3d(0, 0, 0)' }}
      transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
      className="mb-8">

      <div className="flex justify-end mb-4">
        <div className="max-w-[80%] bg-on-surface/[0.07] border border-on-surface/[0.08] rounded-2xl rounded-br-sm px-4 py-2.5">
          <p className="text-sm leading-6 whitespace-pre-wrap">{turn.userText}</p>
        </div>
      </div>

      <div className="flex gap-3">
        <div className="w-6 shrink-0 mt-0.5">
          <div className="w-6 h-6 rounded-full bg-primary/15 border border-primary/25 flex items-center justify-center">
            <Terminal size={11} className="text-primary/70" />
          </div>
        </div>

        <div className="flex-1 min-w-0">
          {live && <LiveStatus turn={turn} />}

          {turn.thinking && <ThinkingBlock thinking={turn.thinking} live={live} />}
          {turn.plan && <PlanBlock plan={turn.plan} />}
          {turn.permissions.map(p => <PermissionBlock key={p.id} p={p} />)}
          {turn.questions.map(q => <QuestionBlock key={q.id} q={q} />)}
          {/* Computer Use is not in this build. The desktop-tool filter below
              stays: `crs.ts` still parses `computer.*` events into
              `turn.computer`, so if the subsystem returns, restoring the one
              line that renders it is the whole change. Filtering an empty set
              costs nothing. */}
          {turn.toolCalls
            .filter(c => !COMPUTER_TOOLS.has(c.name))
            .map((c, i) => <ToolRow key={`${c.name}-${i}`} call={c} />)}
          {turn.executions.map(x => <ExecutionBlock key={x.id} execution={x} />)}

          {/* Files read the same way documents do: press the name, the file
              opens where it is. They were chips that threw a full-screen
              modal, so looking at an attachment meant covering the
              conversation it belonged to. The modal is still one press away
              for a deck or a PDF worth working through. */}
          {turn.assets.map(a => (
            <Attachment key={a.id} asset={a}
              onExpand={() => openAsset({ id: a.id, name: a.name })} />
          ))}

          {/* A document the model authored, rendered here, in the turn that
              produced it. This was a <span>: the UI announced a workspace
              existed and gave you no way to read it, which is the same as not
              shipping the feature. Then it was a chip that opened a side
              panel, which put the artifact somewhere other than where it was
              made. A document is part of what the turn said, so it reads
              inline; the expand control is there for when the wider measure
              is genuinely wanted. */}
          {turn.workspaces.map(w => (
            <Canvas key={w.id} id={w.id} variant="inline"
              title={w.title} version={w.version}
              onExpand={() => openCanvas(w.id)} />
          ))}

          {turn.assistantText && (
            /* The model's reply is reading, not telemetry — the one place
               besides the guides that steps out of the terminal face. */
            <div className="px-prose group/reply text-sm leading-6">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{turn.assistantText}</ReactMarkdown>
              {/* Only once the reply is finished. A copy button on a streaming
                  answer hands over half a sentence, and the button appearing
                  mid-stream reads as the reply having ended. */}
              {!live && (
                <div className="mt-1.5 -ml-2 opacity-0 group-hover/reply:opacity-100
                                focus-within:opacity-100 transition-opacity duration-150">
                  <CopyButton text={turn.assistantText} label="Copy reply" />
                </div>
              )}
            </div>
          )}

          {turn.status === 'cancelled' && (
            <p className="px-label mt-2 flex items-center gap-1.5">
              <Ban size={10} /> Stopped{turn.assistantText ? ' — partial reply kept' : ''}
            </p>
          )}

          {/* A failure renders as a failure, with an honest retry affordance —
              never as an assistant message pretending to be a reply. */}
          {turn.error && (
            <div className="mt-2 flex items-start gap-2.5 rounded-xl border border-error/25 bg-error/[0.06] px-3.5 py-3">
              <AlertTriangle size={14} className="text-error shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-[13px] text-on-surface/85">{turn.error.message}</p>
                <p className="px-label mt-1">{turn.error.code}</p>
              </div>
              {turn.error.retryable && (
                <button onClick={() => api.retry(turn.id)}
                  aria-label="Retry this message"
                  className="ml-auto shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-on-surface/15 hover:bg-on-surface/[0.06] transition duration-150 px-label">
                  <RotateCw size={10} /> Retry
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/** Bucket conversations by day, newest bucket first, preserving list order. */
