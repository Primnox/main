import { ExternalLink, CheckCircle2, AlertCircle, HelpCircle } from 'lucide-react';

interface Citation {
  id: string;
  source: string;
  origin: string;
  confidence: number;
  ref?: {
    url?: string;
    url_domain?: string;
    file?: string;
    line?: number;
    tool?: string;
    timestamp?: string;
  };
  title?: string;
  snippet?: string;
  type: 'direct' | 'synthesized' | 'inferred';
  reliability: 'verified' | 'trusted' | 'unverified';
  retrieved_at?: string;
  expires_at?: string;
}

/**
 * SourcePanel: Expandable list of all sources used in research results
 *
 * Shows:
 * - Source URL/file with domain/path preview
 * - Title and snippet
 * - Reliability indicator (verified ✓, trusted ◆, unverified ○)
 * - Retrieved timestamp with refresh button if stale
 * - Direct vs. synthesized vs. inferred indicators
 */
export function SourcePanel({
  citations,
  onRefresh,
}: {
  citations: Citation[];
  onRefresh?: (citationId: string) => void;
}) {
  const getReliabilityIcon = (reliability: string) => {
    switch (reliability) {
      case 'verified':
        return (
          <div className="flex items-center gap-1.5">
            <CheckCircle2 size={13} className="text-success" />
            <span className="text-xs text-success">Verified</span>
          </div>
        );
      case 'trusted':
        return (
          <div className="flex items-center gap-1.5">
            <CheckCircle2 size={13} className="text-primary" />
            <span className="text-xs text-primary">Trusted</span>
          </div>
        );
      default:
        return (
          <div className="flex items-center gap-1.5">
            <AlertCircle size={13} className="text-warn/60" />
            <span className="text-xs text-warn/60">Unverified</span>
          </div>
        );
    }
  };

  const getSourceIcon = (source: string) => {
    switch (source) {
      case 'web':
        return <ExternalLink size={12} className="text-on-surface/60" />;
      case 'code':
        return <span className="text-[10px] font-bold text-on-surface/60">&lt;/&gt;</span>;
      case 'tool':
        return <span className="text-[10px] font-bold text-on-surface/60">⚙</span>;
      case 'execution':
        return <span className="text-[10px] font-bold text-on-surface/60">▶</span>;
      default:
        return <HelpCircle size={12} className="text-on-surface/60" />;
    }
  };

  const getSourceDisplay = (citation: Citation) => {
    if (citation.ref?.url) {
      const url = new URL(citation.ref.url);
      return {
        primary: url.hostname || citation.ref.url,
        secondary: url.pathname.slice(0, 60),
      };
    }
    if (citation.ref?.file) {
      return {
        primary: citation.ref.file.split('/').pop() || citation.ref.file,
        secondary: citation.ref.file,
      };
    }
    if (citation.ref?.tool) {
      return {
        primary: citation.ref.tool,
        secondary: `Tool execution`,
      };
    }
    return {
      primary: 'Unknown source',
      secondary: '',
    };
  };

  const getAgeString = (timestamp: string | undefined) => {
    if (!timestamp) return null;
    const retrieved = new Date(timestamp);
    const now = new Date();
    const minutes = Math.floor((now.getTime() - retrieved.getTime()) / 60000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(retrieved).toLocaleDateString();
  };

  const isStale = (citation: Citation) => {
    if (!citation.expires_at) return false;
    return new Date(citation.expires_at) < new Date();
  };

  return (
    <div className="space-y-2">
      {citations.map((citation) => {
        const display = getSourceDisplay(citation);
        const stale = isStale(citation);
        const age = getAgeString(citation.retrieved_at);

        return (
          <div
            key={citation.id}
            className="group p-3.5 rounded-lg border border-on-surface/[0.07] hover:border-on-surface/[0.16] hover:bg-on-surface/[0.02] transition duration-150"
          >
            {/* Source Header */}
            <div className="flex items-start gap-2 mb-2">
              <div className="mt-0.5">
                {getSourceIcon(citation.source)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start gap-2 mb-0.5">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-xs text-on-surface truncate">
                      {display.primary}
                    </p>
                    {display.secondary && (
                      <p className="text-[11px] text-on-surface/50 truncate">
                        {display.secondary}
                      </p>
                    )}
                  </div>
                  <div>
                    {getReliabilityIcon(citation.reliability)}
                  </div>
                </div>
              </div>
            </div>

            {/* Title and Snippet */}
            {citation.title && (
              <p className="text-xs text-on-surface/70 mb-2 line-clamp-1">
                {citation.title}
              </p>
            )}
            {citation.snippet && (
              <p className="text-xs text-on-surface/50 mb-2 line-clamp-2">
                &quot;{citation.snippet}&quot;
              </p>
            )}

            {/* Metadata Row */}
            <div className="flex items-center justify-between text-[10px] text-on-surface/50 pt-2 border-t border-on-surface/[0.07]">
              <div className="flex items-center gap-2">
                {age && (
                  <span>Retrieved {age}</span>
                )}
                <span className="inline-block w-1 h-1 rounded-full bg-on-surface/30" />
                <span>
                  {citation.type === 'direct' && 'Direct'}
                  {citation.type === 'synthesized' && 'Synthesized'}
                  {citation.type === 'inferred' && 'Inferred'}
                </span>
              </div>
              {stale && onRefresh && (
                <button
                  onClick={() => onRefresh(citation.id)}
                  className="px-2 py-0.5 text-[10px] rounded bg-warn/20 text-warn opacity-0 group-hover:opacity-100 transition duration-150 hover:bg-warn/30"
                >
                  Refresh
                </button>
              )}
            </div>

            {/* External Link */}
            {citation.ref?.url && (
              <a
                href={citation.ref.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mt-2 text-[11px] text-primary hover:text-primary/80 opacity-0 group-hover:opacity-100 transition duration-150"
              >
                Open source ↗
              </a>
            )}
          </div>
        );
      })}
    </div>
  );
}
