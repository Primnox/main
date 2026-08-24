import { ShieldCheck } from 'lucide-react';
import { Chip, Choice, SectionHeader } from './ui';

/* The Privacy Mirror toggle.
 *
 * Bound to the same `draft`/Save flow as every other setting on this panel —
 * it's a plain settings key (`privacy.mirror_enabled`), not a separate
 * subsystem with its own save button, so turning it off and forgetting to
 * hit Save leaves it exactly as on as it was before, same as everything
 * else here.
 *
 * `modelStatus` comes from the same `/settings` status block Provider and
 * Sandbox already read from — not a second endpoint — because it answers
 * the same kind of question those do: not just "is the setting on" but
 * "is what it depends on actually ready". A scrubber that's still loading
 * its model on a cold start still catches email/IP/card/key patterns via
 * the regex backstop; only names, addresses and the rest of the model-only
 * labels are unprotected until it finishes.
 */
export function PrivacySettings({ draft, onChange, modelStatus }: {
  draft: Record<string, string>;
  onChange: (k: string, v: string) => void;
  modelStatus?: string;
}) {
  const enabled = (draft['privacy.mirror_enabled'] ?? 'on') !== 'off';
  const statusTone = modelStatus === 'ready' ? 'success'
    : modelStatus === 'failed' ? 'error'
    : modelStatus === 'loading' ? 'warn' : 'neutral';

  return (
    <section className="space-y-4">
      <SectionHeader title="Privacy" level={3}
        note="What leaves the device when a cloud model is in use." />

      <div className="flex items-start gap-3 rounded-xl border border-on-surface/[0.10] p-4">
        <ShieldCheck size={16} className="shrink-0 mt-0.5 text-on-surface/50" aria-hidden="true" />
        <div className="min-w-0 flex-1 space-y-3">
          <Choice label="Privacy Mirror" value={enabled ? 'on' : 'off'}
            options={[{ value: 'on', label: 'on' }, { value: 'off', label: 'off' }]}
            onChange={v => onChange('privacy.mirror_enabled', v)}
            hint="On: names, emails, phone numbers, addresses, cards, keys and more are
                  replaced with placeholders before a cloud model ever sees them, and
                  swapped back before you see the reply. Off: the full message goes out
                  as typed. Local models are never scrubbed either way — nothing about
                  those requests leaves this machine." />

          {modelStatus && (
            <div className="flex items-center gap-2 pt-1 border-t border-on-surface/[0.07]">
              <span className="px-label">Detection model</span>
              <Chip tone={statusTone}>{modelStatus}</Chip>
              {modelStatus !== 'ready' && (
                <span className="text-[11px] text-on-surface/50">
                  {modelStatus === 'loading'
                    ? 'Names and addresses aren’t caught until this finishes — emails, IPs, cards and keys still are.'
                    : modelStatus === 'failed'
                      ? 'Running on pattern matching only — emails, IPs, cards and keys still are.'
                      : ''}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
