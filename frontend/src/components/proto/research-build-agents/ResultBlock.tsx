import { Code, MessageCircle, TrendingUp } from 'lucide-react';
import { CitationInline } from './CitationInline';

interface Result {
  id: string;
  content: string;
  type: 'synthesis' | 'code_example' | 'analysis';
  citations: string[];
  confidence: number;
  language?: string;
}

interface Citation {
  id: string;
  title?: string;
  reliability: 'verified' | 'trusted' | 'unverified';
  retrieved_at?: string;
}

export function ResultBlock({
  result,
  citations,
  onCitationClick,
  selectedCitation,
}: {
  result: Result;
  citations: Record<string, Citation>;
  onCitationClick: (id: string) => void;
  selectedCitation: string | null;
}) {
  

  const getIcon = () => {
    switch (result.type) {
      case 'code_example':
        return <Code size={14} />;
      case 'analysis':
        return <TrendingUp size={14} />;
      default:
        return <MessageCircle size={14} />;
    }
  };

  const getLabel = () => {
    switch (result.type) {
      case 'code_example':
        return 'Code example';
      case 'analysis':
        return 'Analysis';
      default:
        return 'Synthesis';
    }
  };

  // Build content with citation markers
  const renderContent = () => {
    if (result.type === 'code_example') {
      return (
        <div className="space-y-2">
          <pre className="bg-on-surface/[0.04] rounded p-3 text-[11px] overflow-x-auto text-on-surface/80 font-mono">
            {result.content}
          </pre>
          <p className="text-xs text-on-surface/50">
            Language: {result.language || 'text'}
          </p>
        </div>
      );
    }

    // For synthesis and analysis, inject citation markers
    // In a real implementation, this would parse markdown or structured content
    return (
      <p className="text-sm leading-relaxed text-on-surface/90">
        {result.content}
        {result.citations.map((citId, idx) => (
          <CitationInline
            key={citId}
            number={idx + 1}
            citationId={citId}
            citation={citations[citId]}
            selected={selectedCitation === citId}
            onClick={() => onCitationClick(citId)}
          />
        ))}
      </p>
    );
  };

  return (
    <div className={`px-4 py-4 rounded-lg border transition duration-150 ${
      selectedCitation && result.citations.includes(selectedCitation)
        ? 'border-on-surface/[0.25] bg-on-surface/[0.03]'
        : 'border-on-surface/[0.07] hover:border-on-surface/[0.16]'
    }`}>
      {/* Header */}
      <div className="flex items-start gap-2 mb-3">
        <div className="text-on-surface/60 mt-1">
          {getIcon()}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium uppercase tracking-wider text-on-surface/60">
              {getLabel()}
            </span>
            <span className="text-xs px-2 py-0.5 rounded bg-on-surface/[0.08] text-on-surface/60">
              {Math.round(result.confidence * 100)}% confident
            </span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mb-3">
        {renderContent()}
      </div>

      {/* Citation Summary */}
      {result.citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-3 border-t border-on-surface/[0.07]">
          {result.citations.map((citId, idx) => {
            const citation = citations[citId];
            if (!citation) return null;

            const reliability = {
              verified: '✓',
              trusted: '◆',
              unverified: '○',
            }[citation.reliability];

            return (
              <button
                key={citId}
                onClick={() => onCitationClick(citId)}
                className={`text-[11px] px-2 py-1 rounded transition duration-150 ${
                  selectedCitation === citId
                    ? 'bg-on-surface text-surface'
                    : 'bg-on-surface/[0.06] hover:bg-on-surface/[0.12] text-on-surface/70'
                }`}
                title={citation.title}
              >
                <span className="font-medium">[{idx + 1}]</span>
                <span className="ml-1">{reliability}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
