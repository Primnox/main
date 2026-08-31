/* Markdown rendering for assistant replies. Adapted from frontend/src/lib/md.tsx
   — sized by weight and spacing rather than raw scale (there is no display type
   on this surface), Tailwind's preflight resets headings to body text so each
   one is mapped explicitly. Code and tables scroll inside their own container
   so a reply never pushes the column sideways. */

import type { Components } from 'react-markdown';

export const MD: Components = {
  h1: ({ children }) => (
    <h1 className="mb-2 mt-5 first:mt-0 text-[15px] font-semibold tracking-tight text-on-surface">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-5 first:mt-0 text-[14px] font-semibold tracking-tight text-on-surface">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1.5 mt-4 first:mt-0 text-[13px] font-semibold text-on-surface/95">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-1.5 mt-4 first:mt-0 text-[13px] font-medium text-on-surface/90">{children}</h4>
  ),
  h5: ({ children }) => (
    <h5 className="mb-1 mt-3 first:mt-0 text-[12px] font-medium text-on-surface/85">{children}</h5>
  ),
  h6: ({ children }) => (
    <h6 className="mb-1 mt-3 first:mt-0 text-[12px] font-medium text-on-surface/75">{children}</h6>
  ),
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0 leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-on-surface">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">
      {children}
    </a>
  ),
  ul: ({ children }) => <ul className="my-2 list-disc pl-5 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal pl-5 space-y-1">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l border-dr-rule-firm pl-3 text-on-surface/70">{children}</blockquote>
  ),
  hr: () => <hr className="my-4 border-0 border-t border-dr-rule" />,
  code: ({ className, children }) => {
    const inline = !/\blanguage-/.test(className ?? '');
    if (inline) {
      return <code className="rounded-none bg-surface-container px-1 py-0.5 font-mono text-[12px]">{children}</code>;
    }
    return (
      <pre className="my-3 overflow-x-auto border border-dr-rule bg-surface-container p-3 font-mono text-[12px] leading-relaxed">
        <code>{children}</code>
      </pre>
    );
  },
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-[12px]">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-dr-rule-firm px-2 py-1.5 text-left font-medium text-on-surface">{children}</th>
  ),
  td: ({ children }) => <td className="border-b border-dr-rule px-2 py-1.5 align-top">{children}</td>,
};
