import { useState } from 'react';

interface Citation {
  id: string;
  title?: string;
  snippet?: string;
  reliability: 'verified' | 'trusted' | 'unverified';
  ref?: {
    url?: string;
  };
}

/**
 * CitationInline: Numbered citation marker that appears in text
 *
 * Renders as [1], [2], etc. Clicking shows a preview tooltip.
 * Selecting the citation highlights it and can scroll to full details.
 */
export function CitationInline({
  number,
  citationId,
  citation,
  selected = false,
  onClick,
}: {
  number: number;
  citationId: string;
  citation: Citation | undefined;
  selected?: boolean;
  onClick?: () => void;
}) {
  const [showPreview, setShowPreview] = useState(false);

  if (!citation) {
    return (
      <button
        onClick={onClick}
        className="inline text-on-surface/30 cursor-not-allowed ml-1"
        disabled
      >
        [{number}]
      </button>
    );
  }

  return (
    <div className="inline-block relative">
      <button
        onClick={onClick}
        onMouseEnter={() => setShowPreview(true)}
        onMouseLeave={() => setShowPreview(false)}
        className={`inline font-medium ml-1 px-1.5 py-0.5 rounded text-xs transition duration-150 ${
          selected
            ? 'bg-on-surface text-surface'
            : 'text-on-surface/60 hover:bg-on-surface/10 hover:text-on-surface'
        }`}
      >
        [{number}]
      </button>

      {/* Preview Tooltip */}
      {showPreview && (
        <div className="absolute z-50 bottom-full left-0 mb-2 w-56 p-2.5 rounded-lg bg-surface border border-on-surface/20 shadow-lg">
          {citation.title && (
            <p className="text-xs font-medium text-on-surface mb-1 line-clamp-2">
              {citation.title}
            </p>
          )}
          {citation.snippet && (
            <p className="text-xs text-on-surface/70 line-clamp-3 mb-2">
              {citation.snippet}
            </p>
          )}
          {citation.ref?.url && (
            <a
              href={citation.ref.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary/80 hover:text-primary break-all underline"
            >
              {new URL(citation.ref.url).hostname}
            </a>
          )}
          <div className="mt-2 text-[10px] text-on-surface/50">
            {citation.reliability === 'verified' && '✓ Verified'}
            {citation.reliability === 'trusted' && '◆ Trusted source'}
            {citation.reliability === 'unverified' && '○ Unverified'}
          </div>
        </div>
      )}
    </div>
  );
}
