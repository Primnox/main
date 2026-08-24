import { useCallback, useState } from 'react';
import { HelpCircle } from 'lucide-react';
import { API, type UserQuestion } from '../lib/crs';

/* A question the model asked because it did not know something.
 *
 * Deliberately not styled as a permission prompt. A permission is "something is
 * about to run, is that alright" — a safety decision where the cautious answer
 * is no. This is "I do not know which of these you meant", where there is no
 * cautious answer, only the right one. Rendering them alike would train the
 * habit of dismissing both, and the one that matters would get dismissed too.
 *
 * It carries the primary colour rather than the warning one for the same
 * reason: nothing here is dangerous, it is just unfinished.
 */
export function QuestionBlock({ q }: { q: UserQuestion }) {
  const [sending, setSending] = useState<string | null>(null);

  const answer = useCallback(async (choice: string) => {
    setSending(choice);
    try {
      await fetch(`${API}/permissions/${q.id}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ choice }),
      });
    } finally {
      // Not cleared on success: the answered branch takes over from here, and
      // clearing it would flash the buttons back before that arrives.
      setSending(s => (s === choice ? s : null));
    }
  }, [q.id]);

  const picked = q.answered
    ? q.options.find(o => o.id === q.answered)?.label ?? null
    : null;

  return (
    <div className="my-3 rounded-xl border border-primary/25 bg-primary/[0.04] p-4">
      <div className="flex items-start gap-2.5">
        <HelpCircle size={14} aria-hidden="true"
          className="mt-0.5 shrink-0 text-primary/80" />
        <div className="min-w-0 flex-1">
          <p className="px-eyebrow mb-1">Primnox is asking</p>
          <p className="text-sm leading-6 text-on-surface/90">{q.question}</p>

          {q.answered ? (
            <p className="px-label mt-2.5">
              {picked
                ? `You answered: ${picked}`
                : 'Not answered — Primnox carried on and said what it assumed.'}
            </p>
          ) : (
            <div role="group" aria-label="Answer"
              className="mt-3 flex flex-wrap gap-2">
              {q.options.map(o => (
                <button key={o.id} onClick={() => answer(o.id)}
                  disabled={sending !== null}
                  className="px-interactive rounded-lg border border-on-surface/[0.14]
                             px-3 py-1.5 text-[12px] hover:border-primary/50
                             hover:bg-primary/[0.06] disabled:opacity-40
                             disabled:pointer-events-none">
                  {o.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
