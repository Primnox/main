import { useState } from 'react';
import { ChevronDown, AlertCircle, CheckCircle2 } from 'lucide-react';

interface Execution {
  id: string;
  tool: 'fetch' | 'python_exec' | 'node_exec' | 'shell';
  status: 'success' | 'error' | 'timeout';
  input?: {
    url?: string;
    code?: string;
    command?: string;
  };
  output?: string;
  error?: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
}

/**
 * ExecutionBlock: Shows a tool execution trace
 *
 * Displays input parameters, output, error state, and timing.
 * Expandable for full details.
 */
export function ExecutionBlock({ execution }: { execution: Execution }) {
  const [expanded, setExpanded] = useState(false);

  const getToolLabel = () => {
    switch (execution.tool) {
      case 'fetch':
        return 'Web Fetch';
      case 'python_exec':
        return 'Python';
      case 'node_exec':
        return 'Node.js';
      case 'shell':
        return 'Shell';
      default:
        return 'Tool';
    }
  };

  const getStatusIcon = () => {
    if (execution.status === 'success') {
      return <CheckCircle2 size={14} className="text-success" />;
    }
    return <AlertCircle size={14} className="text-warn" />;
  };

  const getStatusColor = () => {
    if (execution.status === 'success') return 'bg-success/10 border-success/20';
    return 'bg-warn/10 border-warn/20';
  };

  const getDurationString = () => {
    if (execution.duration_ms < 1000) {
      return `${execution.duration_ms}ms`;
    }
    return `${(execution.duration_ms / 1000).toFixed(2)}s`;
  };

  return (
    <div className={`rounded-lg border ${getStatusColor()} transition duration-150`}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-3 flex items-center gap-2 hover:bg-on-surface/[0.02] transition duration-150"
      >
        <ChevronDown
          size={14}
          className={`transition duration-150 ${expanded ? 'rotate-180' : ''}`}
        />
        <div className="flex-1 flex items-center gap-2 text-left">
          {getStatusIcon()}
          <span className="font-medium text-xs uppercase tracking-wider">
            {getToolLabel()}
          </span>
          <span className="text-xs text-on-surface/50">
            {getDurationString()}
          </span>
        </div>
      </button>

      {/* Details */}
      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-on-surface/[0.07]">
          {/* Input */}
          {execution.input && (
            <div>
              <p className="text-[10px] font-medium uppercase text-on-surface/60 mb-1">
                Input
              </p>
              {execution.input.url && (
                <div className="text-xs bg-on-surface/[0.04] rounded px-2 py-1.5 font-mono text-on-surface/70 break-all">
                  {execution.input.url}
                </div>
              )}
              {execution.input.code && (
                <pre className="text-xs bg-on-surface/[0.04] rounded px-2 py-1.5 font-mono text-on-surface/70 overflow-x-auto max-h-32">
                  {execution.input.code}
                </pre>
              )}
              {execution.input.command && (
                <div className="text-xs bg-on-surface/[0.04] rounded px-2 py-1.5 font-mono text-on-surface/70">
                  {execution.input.command}
                </div>
              )}
            </div>
          )}

          {/* Output */}
          {execution.output && execution.status === 'success' && (
            <div>
              <p className="text-[10px] font-medium uppercase text-on-surface/60 mb-1">
                Output
              </p>
              <pre className="text-xs bg-on-surface/[0.04] rounded px-2 py-1.5 font-mono text-on-surface/70 overflow-x-auto max-h-32">
                {execution.output}
              </pre>
            </div>
          )}

          {/* Error */}
          {execution.error && (
            <div>
              <p className="text-[10px] font-medium uppercase text-warn mb-1">
                Error
              </p>
              <pre className="text-xs bg-warn/10 rounded px-2 py-1.5 font-mono text-warn overflow-x-auto max-h-32">
                {execution.error}
              </pre>
            </div>
          )}

          {/* Timing */}
          <div className="text-[10px] text-on-surface/50 pt-1 border-t border-on-surface/[0.07]">
            <p>
              Started: {new Date(execution.started_at).toLocaleTimeString()}
            </p>
            <p>
              Duration: {getDurationString()}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
