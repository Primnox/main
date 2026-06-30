export const FlowNode = ({ label, sub, c }: { label: string; sub?: string; c: string }) => (
  <div className={`flex flex-col items-center px-2 py-1 rounded-md border text-center shrink-0 ${c}`}>
    <span className="font-bold text-[9px] leading-tight whitespace-nowrap">{label}</span>
    {sub && <span className="text-[7px] opacity-50 leading-tight mt-0.5 whitespace-nowrap">{sub}</span>}
  </div>
);

export const FlowArrow = ({ c }: { c: string }) => (
  <span className={`text-sm leading-none ${c}`}>→</span>
);

export const FlowLocal = ({ light = false }: { light?: boolean }) => (
  <div className="flex flex-col items-center gap-1.5 py-1.5">
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <FlowNode label="You" c="border-slate-700 bg-slate-900 text-slate-300" />
      <FlowArrow c={light ? 'text-emerald-700' : 'text-emerald-800'} />
      <FlowNode label="Primnox" sub="brain.py" c="border-emerald-800 bg-emerald-950 text-emerald-300" />
      <FlowArrow c={light ? 'text-emerald-700' : 'text-emerald-800'} />
      <FlowNode label="Local Model" sub="on-device" c="border-emerald-600 bg-emerald-950 text-emerald-300" />
      <FlowArrow c={light ? 'text-emerald-700' : 'text-emerald-800'} />
      <FlowNode label="Response" sub="raw" c="border-emerald-800 bg-emerald-950 text-emerald-300" />
    </div>
    <span className={`text-[8px] ${light ? 'text-emerald-600' : 'text-emerald-700'} font-mono tracking-widest uppercase`}>
      nothing leaves your machine
    </span>
  </div>
);

export const FlowCloud = ({ light = false }: { light?: boolean }) => (
  <div className="flex flex-col items-center gap-1.5 py-1.5">
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <FlowNode label="You" c="border-slate-700 bg-slate-900 text-slate-300" />
      <FlowArrow c="text-slate-600" />
      <FlowNode label="Privacy Mirror" sub="DeBERTa NER" c="border-pink-800 bg-pink-950 text-pink-300" />
      <FlowArrow c={light ? 'text-blue-700' : 'text-blue-800'} />
      <FlowNode label="Cloud API" sub="Groq / OpenAI" c="border-blue-800 bg-blue-950 text-blue-300" />
      <FlowArrow c={light ? 'text-pink-700' : 'text-pink-800'} />
      <FlowNode label="Rehydrate" sub={light ? 'names restored' : 'names back'} c="border-pink-800 bg-pink-950 text-pink-300" />
      <FlowArrow c="text-slate-600" />
      <FlowNode label="You" sub="real names" c="border-slate-700 bg-slate-900 text-slate-300" />
    </div>
    <span className={`text-[8px] ${light ? 'text-pink-700' : 'text-pink-800'} font-mono tracking-widest uppercase`}>
      cloud only {light ? 'ever ' : ''}sees §NAME_1§ — not your real name
    </span>
  </div>
);

export const FlowRaw = () => (
  <div className="flex flex-col items-center gap-1.5 py-1.5">
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <FlowNode label="You" c="border-slate-700 bg-slate-900 text-slate-300" />
      <FlowArrow c="text-slate-700" />
      <FlowNode label="Primnox" sub="brain.py" c="border-slate-700 bg-slate-900 text-slate-400" />
      <FlowArrow c="text-slate-600" />
      <FlowNode label="Cloud API" sub="Groq / OpenAI" c="border-slate-600 bg-slate-900 text-slate-300" />
      <FlowArrow c="text-slate-700" />
      <FlowNode label="You" sub="response" c="border-slate-700 bg-slate-900 text-slate-300" />
    </div>
    <span className="text-[8px] text-amber-700 font-mono tracking-widest uppercase">
      your data reaches the cloud as-is
    </span>
  </div>
);
