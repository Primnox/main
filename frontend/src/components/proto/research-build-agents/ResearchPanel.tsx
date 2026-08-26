import { useCallback, useEffect, useState } from 'react';
import { Search, RefreshCw, X, Loader2 } from 'lucide-react';
import { ResultBlock } from './ResultBlock';
import { SourcePanel } from './SourcePanel';
import { ExecutionBlock } from './ExecutionBlock';
import sampleData from './demo.json';

interface ResearchState {
  query: string;
  searching: boolean;
  results: any[];
  citations: Record<string, any>;
  executions: any[];
  error: string | null;
  bundleId: string | null;
  createdAt: string | null;
  expiresAt: string | null;
}

/**
 * ResearchPanel: Main container for research results
 *
 * Displays research results with citations, source tracking, and tool execution
 * traces. Supports both embedded (side panel) and modal layouts.
 */
export function ResearchPanel({ embedded = true, onClose }: {
  embedded?: boolean;
  onClose?: () => void;
}) {
  const [state, setState] = useState<ResearchState>({
    query: '',
    searching: false,
    results: [],
    citations: {},
    executions: [],
    error: null,
    bundleId: null,
    createdAt: null,
    expiresAt: null,
  });

  const [expandedSources, setExpandedSources] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<string | null>(null);

  // Demo: Load sample data
  const loadSampleData = useCallback(() => {
    setState({
      query: sampleData.query,
      searching: false,
      results: sampleData.results,
      citations: sampleData.citations,
      executions: sampleData.executions || [],
      error: null,
      bundleId: sampleData.bundle_id,
      createdAt: sampleData.created_at,
      expiresAt: sampleData.expires_at,
    });
  }, []);

  // Demo: Simulate search
  const handleSearch = useCallback(async (query: string) => {
    if (!query.trim()) return;
    setState(s => ({ ...s, query, searching: true, error: null, results: [] }));

    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Load sample data instead of real API call
    loadSampleData();
  }, [loadSampleData]);

  // Handle input
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch(state.query);
  };

  // Calculate age of result
  const getResultAge = () => {
    if (!state.createdAt) return null;
    const created = new Date(state.createdAt);
    const now = new Date();
    const minutes = Math.floor((now.getTime() - created.getTime()) / 60000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  // Check if result is stale
  const isStale = state.expiresAt
    ? new Date(state.expiresAt) < new Date()
    : false;

  // Collect all citations used in results
  const usedCitationIds = new Set<string>();
  state.results.forEach(r => {
    (r.citations || []).forEach((id: string) => usedCitationIds.add(id));
  });

  return (
    <div className={embedded
      ? 'h-full w-full min-w-0 bg-surface flex flex-col'
      : 'fixed inset-0 z-50 bg-surface flex flex-col'}>

      {/* Header */}
      <header className="h-14 shrink-0 flex items-center gap-3 px-6 border-b border-on-surface/[0.07]">
        <Search size={15} className="text-on-surface/60" />
        <span className="font-display font-bold text-[13px] uppercase tracking-[0.18em]">
          Research
        </span>
        {state.bundleId && (
          <span className="px-label text-on-surface/50">
            {getResultAge()}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {onClose && (
            <button onClick={onClose} aria-label="Close research"
              className="p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05] transition duration-150">
              <X size={16} />
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="max-w-3xl mx-auto px-8 py-8 space-y-6">

          {/* Search Input */}
          <form onSubmit={handleSubmit} className="space-y-3">
            <label htmlFor="research-query" className="px-eyebrow">
              Research question
            </label>
            <div className="flex gap-2">
              <input
                id="research-query"
                type="text"
                value={state.query}
                onChange={e => setState(s => ({ ...s, query: e.target.value }))}
                placeholder="Ask me to research anything..."
                className="flex-1 px-3 py-2 rounded-lg border border-on-surface/[0.12] bg-transparent text-sm outline-none focus-visible:border-on-surface/40"
              />
              <button
                type="submit"
                disabled={state.searching || !state.query.trim()}
                className="px-4 py-2 rounded-lg bg-on-surface text-surface font-medium text-sm disabled:opacity-40 transition duration-150 flex items-center gap-2">
                {state.searching ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Searching...
                  </>
                ) : (
                  <>
                    <Search size={14} />
                    Search
                  </>
                )}
              </button>
            </div>
            <p className="text-xs text-on-surface/50">
              This is a demo. Click Search to load sample data about async/await in Python.
            </p>
          </form>

          {/* Error State */}
          {state.error && (
            <div className="p-4 rounded-lg bg-warn/10 border border-warn/20 text-sm text-warn">
              {state.error}
            </div>
          )}

          {/* Results */}
          {state.results.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="px-eyebrow">
                  Results
                </p>
                {isStale && (
                  <button className="text-xs px-2.5 py-1.5 rounded-lg border border-warn/40 text-warn hover:bg-warn/10 transition duration-150 flex items-center gap-1.5">
                    <RefreshCw size={12} />
                    Refresh sources
                  </button>
                )}
              </div>

              {state.results.map((result, idx) => (
                <ResultBlock
                  key={idx}
                  result={result}
                  citations={state.citations}
                  onCitationClick={setSelectedCitation}
                  selectedCitation={selectedCitation}
                />
              ))}
            </div>
          )}

          {/* Execution Traces */}
          {state.executions.length > 0 && (
            <div className="space-y-3">
              <p className="px-eyebrow">Tool executions</p>
              {state.executions.map((exec, idx) => (
                <ExecutionBlock key={idx} execution={exec} />
              ))}
            </div>
          )}

          {/* Source Panel */}
          {state.results.length > 0 && (
            <div className="space-y-3">
              <button
                onClick={() => setExpandedSources(!expandedSources)}
                className="w-full text-left px-eyebrow py-2 rounded hover:bg-on-surface/[0.03] transition duration-150">
                Sources ({usedCitationIds.size})
              </button>
              {expandedSources && (
                <SourcePanel
                  citations={Array.from(usedCitationIds)
                    .map(id => state.citations[id])
                    .filter(Boolean)}
                  onRefresh={() => {
                    // Demo: would re-fetch sources
                    console.log('Refreshing sources...');
                  }}
                />
              )}
            </div>
          )}

          {/* Empty State */}
          {state.results.length === 0 && !state.searching && (
            <div className="flex flex-col items-center justify-center gap-3 text-center py-12">
              <Search size={28} className="text-on-surface/30" />
              <p className="text-sm text-on-surface/60">
                Enter a research question above to get started.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
