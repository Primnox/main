import { CopyButton } from '../components/CopyButton';
import { FlowchartBlock } from '../components/FlowchartBlock';

/* Headings, emphasis, quotes, tables and rules were missing from this map.
 *
 * That is not a cosmetic gap: Tailwind's preflight resets h1-h6 to `font-size:
 * inherit; font-weight: inherit`, so an unmapped heading renders as ordinary
 * body text. A model writing `# Title` produced a line indistinguishable from
 * a paragraph, everywhere markdown is rendered - the reply body included.
 *
 * Sized by weight and spacing rather than by raw scale, per the world: there
 * is no display type on this surface, and a heading in a reply that shouts is
 * worse than one that simply reads first. More space above than below, so a
 * heading binds to the text it introduces. */
export const MD: any = {
  h1: ({ children }: any) => <h1 className="mb-2 mt-5 first:mt-0 text-[15px] font-semibold tracking-tight text-on-surface">{children}</h1>,
  h2: ({ children }: any) => <h2 className="mb-2 mt-5 first:mt-0 text-[14px] font-semibold tracking-tight text-on-surface">{children}</h2>,
  h3: ({ children }: any) => <h3 className="mb-1.5 mt-4 first:mt-0 text-[13px] font-semibold text-on-surface/95">{children}</h3>,
  h4: ({ children }: any) => <h4 className="mb-1.5 mt-4 first:mt-0 text-[13px] font-medium text-on-surface/90">{children}</h4>,
  h5: ({ children }: any) => <h5 className="mb-1 mt-3 first:mt-0 text-[12px] font-medium text-on-surface/85">{children}</h5>,
  h6: ({ children }: any) => <h6 className="mb-1 mt-3 first:mt-0 text-[12px] font-medium text-on-surface/75">{children}</h6>,
  strong: ({ children }: any) => <strong className="font-semibold text-on-surface">{children}</strong>,
  em: ({ children }: any) => <em className="italic">{children}</em>,
  /* 1px, not a slab. A thick coloured left border on a quote is the
     category's decoration reflex; a hairline is the world's. */
  blockquote: ({ children }: any) => (
    <blockquote className="my-3 border-l border-dr-rule-firm pl-3 text-on-surface/70">{children}</blockquote>
  ),
  hr: () => <hr className="my-4 border-0 border-t border-dr-rule" />,
  /* Tables scroll inside their own container rather than pushing the reply
     sideways - the same rule the code block follows. */
  table: ({ children }: any) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-[12px]">{children}</table>
    </div>
  ),
  th: ({ children }: any) => (
    <th className="border-b border-dr-rule-firm px-2 py-1.5 text-left font-medium text-on-surface">{children}</th>
  ),
  td: ({ children }: any) => (
    <td className="border-b border-dr-rule px-2 py-1.5 align-top text-on-surface/85">{children}</td>
  ),
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
      /* Inline code has to WRAP.
       *
       * A model asked for "a prompt" answers with the prompt in single
       * backticks, which lands here rather than in the fenced branch above.
       * Without a wrapping rule this element inherits `white-space: pre` and
       * lays the whole sentence out on one line: measured at 1975px inside a
       * 1032px column, so the reply ran off the edge and the text was simply
       * unreadable. The fenced branch escapes this because it owns an
       * `overflow-x-auto` scroller; inline code has no scroller and must not
       * grow one, so it wraps instead.
       *
       * `pre-wrap` keeps meaningful internal spacing, and `anywhere` breaks
       * the unbroken tokens that actually justify inline code in the first
       * place - a long path, a URL, a hash - which `break-word` alone leaves
       * overflowing. */
      <code className="bg-on-surface/10 text-primary/90 px-1.5 py-0.5 rounded-md text-[0.82em] font-mono
                       whitespace-pre-wrap [overflow-wrap:anywhere]">{children}</code>
    ),
  a: ({ href, children }: any) => <a href={href} className="text-primary underline underline-offset-2">{children}</a>,
};

