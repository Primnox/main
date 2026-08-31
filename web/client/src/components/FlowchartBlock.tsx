/* Phase 1 stub — the desktop FlowchartBlock renders mermaid fences through the
   Graphify viewer. Until that's ported, a mermaid code block renders as plain
   preformatted text rather than crashing. */
export function FlowchartBlock({ source }: { source: string }) {
  return (
    <pre className="my-3 overflow-x-auto rounded-xl border border-on-surface/10 bg-on-surface/[0.03] p-4">
      <code className="font-mono text-[0.78rem] leading-relaxed">{source}</code>
    </pre>
  );
}
