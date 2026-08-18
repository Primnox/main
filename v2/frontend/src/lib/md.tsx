import { CopyButton } from '../components/CopyButton';
import { FlowchartBlock } from '../components/FlowchartBlock';

export const MD: any = {
  p:  ({ children }: any) => <p className="mb-3 last:mb-0 leading-7 text-on-surface/85">{children}</p>,
  ul: ({ children }: any) => <ul className="mb-3 space-y-1 pl-5 list-disc text-on-surface/85">{children}</ul>,
  ol: ({ children }: any) => <ol className="mb-3 space-y-1 pl-5 list-decimal text-on-surface/85">{children}</ol>,
  code: ({ children, className }: any) =>
    /^language-mermaid$/.test(className || '') ? (
      // A diagram, not a code block. Mermaid renders a fixed picture; the same
      // nodes through Graphify's viewer get neighbour highlighting, search and
      // communities — the same reading experience as the knowledge graph, so a
      // diagram in a reply and the codebase behind it are read the same way.
      <FlowchartBlock source={String(children)} />
    ) : className ? (
      // `group` + the button pinned to the corner: the block is the thing you
      // came to copy, and hunting for a control elsewhere to do it is the part
      // that made people select it by hand.
      <div className="group/code relative my-3">
        <pre className="p-4 pr-14 rounded-xl border border-on-surface/10 bg-on-surface/[0.03] overflow-x-auto">
          <code className="font-mono text-[0.78rem] leading-relaxed">{children}</code>
        </pre>
        <div className="absolute top-2 right-2 opacity-0 group-hover/code:opacity-100
                        focus-within:opacity-100 transition-opacity duration-150">
          {/* `focus-within` as well as hover, so it is reachable by keyboard —
              hover-only would make the copy button unusable without a pointer,
              which is the same defect the chips had. */}
          <CopyButton text={String(children)} label="Copy"
            className="bg-surface/80 backdrop-blur-sm" />
        </div>
      </div>
    ) : (
      <code className="bg-on-surface/10 text-primary/90 px-1.5 py-0.5 rounded-md text-[0.82em] font-mono">{children}</code>
    ),
  a: ({ href, children }: any) => <a href={href} className="text-primary underline underline-offset-2">{children}</a>,
};

