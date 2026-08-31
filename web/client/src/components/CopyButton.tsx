import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Copy } from 'lucide-react';

/* Copy to clipboard, with the result actually reported.
 *
 * There was no copy affordance anywhere in the app — not on a reply, not on a
 * code block — in a tool whose main output is code someone has to paste
 * somewhere else. Selecting a fenced block by hand drags the surrounding prose
 * in, and on a long block it means a scroll-drag.
 *
 * Two things this does not do:
 *
 * `navigator.clipboard` is unavailable on an insecure origin and can be denied
 * by permission, so the failure is caught and SAID rather than swallowed. A
 * copy button that silently does nothing is worse than none, because the user
 * walks away believing they have the text.
 *
 * The "Copied" state is announced through `aria-live`, because for a sighted
 * user the icon flip is the confirmation and without this there is none.
 */
export function CopyButton({ text, label = 'Copy', className = '' }: {
  text: string; label?: string; className?: string;
}) {
  const [state, setState] = useState<'idle' | 'done' | 'failed'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // A pending timeout that fires after unmount would set state on a dead
  // component; every code block in a long transcript owns one of these.
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const copy = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    try {
      await navigator.clipboard.writeText(text);
      setState('done');
    } catch {
      setState('failed');
    }
    timer.current = setTimeout(() => setState('idle'), 2000);
  }, [text]);

  return (
    <button type="button" onClick={copy}
      aria-label={state === 'failed' ? 'Copy failed' : label}
      className={`px-interactive inline-flex items-center gap-1.5 rounded-lg px-2 py-1
                  text-[11px] text-on-surface/50 hover:text-on-surface
                  hover:bg-on-surface/[0.06] ${className}`}>
      {state === 'done'
        ? <Check size={12} aria-hidden="true" className="text-primary" />
        : <Copy size={12} aria-hidden="true" />}
      <span aria-live="polite">
        {state === 'done' ? 'Copied' : state === 'failed' ? 'Blocked' : label}
      </span>
    </button>
  );
}
