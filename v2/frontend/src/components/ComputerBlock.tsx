import { useEffect, useState } from 'react';
import {
  AlertTriangle, Check, ChevronRight, Eye, Keyboard, Loader2,
  MousePointerClick, Monitor, ScrollText, Type, Undo2,
} from 'lucide-react';
import { type ComputerAction, type ComputerSession } from '../lib/crs';

/* The live record of what the agent did to an application Primnox does not
   own. It renders expanded while a session is open and collapses once it
   ends, which is the opposite of ExecutionBlock — and deliberate. A sandbox
   execution is worth reviewing after the fact; a click in the user's mail
   client is worth seeing AS it happens, because that is the only moment
   anyone can intervene. Nothing in this list can be undone afterwards. */

const ICONS: Record<ComputerAction['kind'], typeof Eye> = {
  read: Eye,
  capture: Monitor,
  click: MousePointerClick,
  type: Type,
  scroll: ScrollText,
  keys: Keyboard,
  undo: Undo2,
};

function Remaining({ session }: { session: ComputerSession }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (session.endedAt) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [session.endedAt]);

  if (session.endedAt || !session.ttlS) return null;
  const left = Math.max(0, session.ttlS - Math.floor((now - session.startedAt) / 1000));
  /* Shown because the grant really does expire, and a user watching an agent
     work in their editor should be able to see that the authority is running
     out rather than discovering it when an action fails. */
  return (
    <span className={`shrink-0 tabular-nums text-[11px] ${left <= 30 ? 'text-error/80' : 'text-on-surface/40'}`}>
      {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}
    </span>
  );
}

function Action({ action }: { action: ComputerAction }) {
  const Icon = ICONS[action.kind] ?? MousePointerClick;
  return (
    <li className="flex items-start gap-2.5 px-3.5 py-1.5">
      <Icon size={11} className="mt-[3px] shrink-0 text-on-surface/40" />
      <span className="flex-1 text-[11px] leading-relaxed text-on-surface/75">
        {action.description}
        {action.status === 'failed' && action.detail && (
          <span className="block text-error/80">{action.detail}</span>
        )}
      </span>
      {action.status === 'running'
        ? <Loader2 size={11} className="px-spin mt-[3px] shrink-0 text-on-surface/50" />
        : action.status === 'failed'
          ? <AlertTriangle size={11} className="mt-[3px] shrink-0 text-error" />
          : <Check size={11} className="mt-[3px] shrink-0 text-primary" />}
    </li>
  );
}

export function ComputerBlock({ session }: { session: ComputerSession }) {
  const live = !session.endedAt;
  const [open, setOpen] = useState(live);

  /* Collapse when the session ends, but only if the user has not taken over
     the disclosure themselves — reaching in to open a panel and having it
     shut a second later is the kind of small betrayal that makes an interface
     feel like it is fighting you. */
  const [touched, setTouched] = useState(false);
  useEffect(() => {
    if (!live && !touched) setOpen(false);
  }, [live, touched]);

  const failed = session.actions.filter(a => a.status === 'failed').length;
  const done = session.actions.filter(a => a.status !== 'running').length;

  return (
    <div className={`mb-3 rounded-xl border overflow-hidden transition-colors duration-300
      ${live ? 'border-primary/30 bg-primary/[0.03]' : 'border-on-surface/[0.09]'}`}>
      <button
        onClick={() => { setTouched(true); setOpen(o => !o); }}
        aria-expanded={open}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-on-surface/[0.03] transition-colors duration-200">
        <Monitor size={12} className={`shrink-0 ${live ? 'text-primary' : 'text-on-surface/50'}`} />
        <span className="px-label">
          {session.scope === 'read' ? 'Reading' : 'Controlling'}
        </span>
        <span className="text-[11px] text-on-surface/70 truncate flex-1">{session.label}</span>

        {live && (
          /* The one piece of state a user must never have to hunt for: that
             something is happening in another application right now. */
          <span className="shrink-0 inline-flex items-center gap-1.5 text-[11px] text-primary">
            <span className="size-1.5 rounded-full bg-primary animate-pulse" />
            live
          </span>
        )}
        <Remaining session={session} />
        {!live && (
          <span className="shrink-0 text-[11px] text-on-surface/40">
            {done} action{done === 1 ? '' : 's'}
          </span>
        )}
        {failed > 0 && <AlertTriangle size={11} className="shrink-0 text-error" />}
        <ChevronRight size={12}
          className={`shrink-0 text-on-surface/50 transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
      </button>

      {open && (
        <div className="border-t border-on-surface/[0.07]">
          {/* Said plainly, and only while it is true. The whole premise of
              this feature is that the user keeps working while it runs, and
              they can only rely on that if they are told.

              The second sentence exists because the first one creates a
              problem: an agent that disturbs nothing also SHOWS nothing, and
              a user told only that their desktop is safe has no way to tell
              work from a hang. Naming the marker to look for turns this from
              a reassurance into an instruction. */}
          {live && (
            <p className="px-3.5 pt-2.5 text-[11px] text-on-surface/45">
              Running in the background — your mouse and keyboard are untouched.
              Primnox's pointer shows where it is working.
            </p>
          )}
          {session.actions.length === 0 ? (
            <p className="px-3.5 py-3 text-[11px] text-on-surface/50">Nothing done yet.</p>
          ) : (
            <ul className="py-1.5">
              {session.actions.map(a => <Action key={a.id} action={a} />)}
            </ul>
          )}
          {!live && session.endReason && session.endReason !== 'finished' && (
            <p className="px-3.5 py-2 border-t border-on-surface/[0.07] text-[11px] text-on-surface/50">
              Session {session.endReason}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
