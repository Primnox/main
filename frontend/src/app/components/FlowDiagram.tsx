/**
 * Privacy data-flow diagrams.
 *
 * Colour here is meaning, not decoration — which is why this is the one place
 * that keeps a multi-colour palette instead of collapsing to a single token:
 *
 *   neutral  you / an unremarkable hop
 *   safe     stays on this machine
 *   shield   Primnox is actively scrubbing or restoring names
 *   warn     data is leaving as-is
 *
 * Those four tones are defined in styles/tailwind.css and are built from the
 * theme's own tokens. The previous version used slate/emerald/pink/blue/amber
 * literals, so every node stayed dark on the four light themes.
 */

type Tone = 'neutral' | 'safe' | 'shield' | 'warn';

export const FlowNode = ({ label, sub, tone = 'neutral' }: {
  label: string; sub?: string; tone?: Tone;
}) => (
  <div className={`px-node px-tone-${tone}`}>
    <span className="font-bold text-[9px] leading-tight whitespace-nowrap">{label}</span>
    {sub && <span className="text-[7px] opacity-60 leading-tight mt-0.5 whitespace-nowrap">{sub}</span>}
  </div>
);

export const FlowArrow = ({ tone = 'neutral' }: { tone?: Tone }) => (
  <span className={`text-sm leading-none px-ink-${tone}`}>→</span>
);

const Caption = ({ tone, children }: { tone: Tone; children: React.ReactNode }) => (
  <span className={`text-[8px] font-mono tracking-widest uppercase px-ink-${tone}`}>{children}</span>
);

const Rail = ({ children }: { children: React.ReactNode }) => (
  <div className="flex flex-col items-center gap-1.5 py-1.5">{children}</div>
);

/** Local / hybrid: the prompt never leaves the device. */
export const FlowLocal = () => (
  <Rail>
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <FlowNode label="You" />
      <FlowArrow tone="safe" />
      <FlowNode label="Primnox" sub="brain.py" tone="safe" />
      <FlowArrow tone="safe" />
      <FlowNode label="Local Model" sub="on-device" tone="safe" />
      <FlowArrow tone="safe" />
      <FlowNode label="Response" sub="raw" tone="safe" />
    </div>
    <Caption tone="safe">nothing leaves your machine</Caption>
  </Rail>
);

/** Cloud + Mirror: names are stripped before the hop out and restored after.
 *  The cloud node is neutral rather than alarming — that is the whole point of
 *  the mirror: by the time data reaches it, it carries no real identifiers. */
export const FlowCloud = () => (
  <Rail>
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <FlowNode label="You" />
      <FlowArrow />
      <FlowNode label="Privacy Mirror" sub="DeBERTa NER" tone="shield" />
      <FlowArrow tone="shield" />
      <FlowNode label="Cloud API" sub="Groq / OpenAI" />
      <FlowArrow tone="shield" />
      <FlowNode label="Rehydrate" sub="names back" tone="shield" />
      <FlowArrow />
      <FlowNode label="You" sub="real names" />
    </div>
    <Caption tone="shield">cloud only sees §NAME_1§ — not your real name</Caption>
  </Rail>
);

/** Cloud Raw: no scrubbing. The cloud hop is the thing to notice. */
export const FlowRaw = () => (
  <Rail>
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <FlowNode label="You" />
      <FlowArrow />
      <FlowNode label="Primnox" sub="brain.py" />
      <FlowArrow tone="warn" />
      <FlowNode label="Cloud API" sub="Groq / OpenAI" tone="warn" />
      <FlowArrow tone="warn" />
      <FlowNode label="You" sub="response" />
    </div>
    <Caption tone="warn">your data reaches the cloud as-is</Caption>
  </Rail>
);
