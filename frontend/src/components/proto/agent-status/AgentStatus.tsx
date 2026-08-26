import { useState, useEffect, useRef } from 'react';
import { ChevronRight, Loader2, AlertTriangle, CheckCircle2, Clock, FileText, Cpu, ShieldAlert, ShieldCheck, Terminal, Package, Download } from 'lucide-react';
import { Collapsible } from '@base-ui-components/react/collapsible';
import './AgentStatus.css';

/* Level 1: Glance — Status word + elapsed time, minimal cognitive load
 * Level 2: Expand — Progress steps, recent files, critical warning
 * Level 3: Deep Inspect — Complete diagnostics with tabs
 *
 * The hierarchy respects operation duration:
 * - Quick ops (< 2s): Level 1 is sufficient
 * - Slow ops (2-10s): Level 2 auto-expands
 * - Deep debugging (> 10s or user clicks): Level 3 opens
 *
 * Each level earned through progression, never showing irrelevant noise.
 */

export interface ProgressStep {
  label: string;
  completed: boolean;
  duration?: number;
}

export interface AgentStatusProps {
  status: 'idle' | 'queued' | 'building_context' | 'thinking' | 'streaming' | 'completed' | 'failed';
  elapsed: number; // seconds
  progress?: ProgressStep[];
  recentFiles?: { name: string; bytes?: number; url?: string }[];
  warning?: {
    type: 'sandbox' | 'privacy' | 'circuit_breaker' | 'provider';
    severity: 'info' | 'warning' | 'error';
    message: string;
  };
  diagnostics?: {
    sandbox: 'appcontainer' | 'unsandboxed' | null;
    scrubbing: boolean;
    successRate?: number;
    latency_ms?: number;
    turnsToday?: number;
    failedTurns?: number;
    benchedProviders?: number;
    cursor?: number;
    connected?: boolean;
    synced?: boolean;
    resyncs?: number;
    thinking?: string;
  };
  onDeepInspect?: () => void;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = (seconds % 60).toFixed(0);
  return `${minutes}m ${secs}s`;
}

function getStatusCopy(status: string): string {
  const map: Record<string, string> = {
    idle: 'Idle',
    queued: 'Queued',
    building_context: 'Building context',
    thinking: 'Thinking',
    streaming: 'Streaming',
    completed: 'Completed',
    failed: 'Failed',
  };
  return map[status] || status;
}

function getStatusIcon(status: string, live: boolean) {
  if (status === 'completed') return <CheckCircle2 size={13} className="text-success shrink-0" />;
  if (status === 'failed') return <AlertTriangle size={13} className="text-error shrink-0" />;
  if (live) return <Loader2 size={13} className="text-on-surface/50 shrink-0 px-spin" />;
  return <Clock size={13} className="text-on-surface/50 shrink-0" />;
}

/* Level 1: Glance view — always visible */
function Level1Glance({ status, elapsed, live, onExpand }: {
  status: string;
  elapsed: number;
  live: boolean;
  onExpand: () => void;
}) {
  return (
    <div
      onClick={onExpand}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onExpand();
        }
      }}
      className="cursor-pointer p-3 rounded-lg border border-on-surface/[0.07] hover:bg-on-surface/[0.02] transition duration-150 group">
      <div className="flex items-center gap-2.5">
        {getStatusIcon(status, live)}
        <span className="px-label flex-1" aria-live="polite">
          {getStatusCopy(status)}
        </span>
        {elapsed > 0 && (
          <span className="tabular-nums text-[11px] text-on-surface/50" aria-hidden="true">
            {formatElapsed(elapsed)}
          </span>
        )}
        <ChevronRight size={13} className="shrink-0 text-on-surface/30 group-hover:text-on-surface/50 transition duration-150" />
      </div>
    </div>
  );
}

/* Level 2: Expanded view — progress steps, files, warnings */
function Level2Expanded({ status, elapsed, progress, recentFiles, warning }: {
  status: string;
  elapsed: number;
  progress?: ProgressStep[];
  recentFiles?: { name: string; bytes?: number; url?: string }[];
  warning?: AgentStatusProps['warning'];
}) {
  return (
    <div className="space-y-3 mt-2">
      {/* Progress steps */}
      {progress && progress.length > 0 && (
        <div className="bg-on-surface/[0.02] rounded-lg p-3 border border-on-surface/[0.05]">
          <p className="px-label mb-2">Progress</p>
          <ol className="space-y-1.5">
            {progress.map((step, i) => (
              <li key={i} className="flex items-center gap-2.5 text-[11px]">
                {step.completed ? (
                  <CheckCircle2 size={12} className="text-success shrink-0" />
                ) : (
                  <div className="w-3 h-3 rounded-full border border-on-surface/30 flex items-center justify-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-on-surface/50" />
                  </div>
                )}
                <span className={step.completed ? 'text-on-surface/55' : 'text-on-surface/75'}>
                  {step.label}
                </span>
                {step.duration != null && (
                  <span className="text-on-surface/40 ml-auto">
                    {step.duration.toFixed(1)}s
                  </span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Recent files */}
      {recentFiles && recentFiles.length > 0 && (
        <div className="bg-on-surface/[0.02] rounded-lg p-3 border border-on-surface/[0.05]">
          <p className="px-label mb-2">Generated Files</p>
          <ul className="space-y-1">
            {recentFiles.map((file, i) => (
              <li key={i} className="flex items-center gap-2 text-[11px]">
                <FileText size={12} className="text-on-surface/50 shrink-0" />
                <span className="flex-1 text-on-surface/70 truncate">{file.name}</span>
                {file.bytes != null && (
                  <span className="text-on-surface/50 tabular-nums shrink-0">
                    {file.bytes < 1024 ? `${file.bytes}B` : `${(file.bytes / 1024).toFixed(0)}K`}
                  </span>
                )}
                {file.url && (
                  <a href={file.url} download className="text-on-surface/30 hover:text-on-surface/60 transition">
                    <Download size={11} />
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Critical warning */}
      {warning && (
        <div className={`rounded-lg p-3 border flex gap-2.5 ${
          warning.severity === 'error' ? 'bg-error/[0.06] border-error/25' :
          warning.severity === 'warning' ? 'bg-warn/[0.06] border-warn/25' :
          'bg-info/[0.06] border-info/25'
        }`}>
          <AlertTriangle size={13} className={`shrink-0 mt-0.5 ${
            warning.severity === 'error' ? 'text-error' :
            warning.severity === 'warning' ? 'text-warn' :
            'text-info'
          }`} />
          <p className={`text-[12px] leading-4 ${
            warning.severity === 'error' ? 'text-error/85' :
            warning.severity === 'warning' ? 'text-warn/85' :
            'text-info/85'
          }`}>
            {warning.message}
          </p>
        </div>
      )}
    </div>
  );
}

/* Level 3: Deep inspect — comprehensive diagnostics with tabs */
function Level3DeepInspect({ diagnostics, status }: {
  diagnostics?: AgentStatusProps['diagnostics'];
  status: string;
}) {
  const [tab, setTab] = useState<'progress' | 'security' | 'stream' | 'telemetry' | 'reasoning'>('progress');

  if (!diagnostics) return null;

  const tabs = [
    { id: 'progress' as const, label: 'Progress' },
    { id: 'security' as const, label: 'Security & Privacy' },
    { id: 'stream' as const, label: 'Stream' },
    { id: 'telemetry' as const, label: 'Telemetry' },
    ...(diagnostics.thinking ? [{ id: 'reasoning' as const, label: 'Reasoning' }] : []),
  ];

  return (
    <div className="mt-4 border border-on-surface/[0.07] rounded-lg overflow-hidden">
      {/* Tab bar */}
      <div className="flex border-b border-on-surface/[0.07] bg-on-surface/[0.02] overflow-x-auto">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-[12px] font-medium whitespace-nowrap border-b-2 transition duration-150 ${
              tab === t.id
                ? 'border-primary text-primary'
                : 'border-transparent text-on-surface/50 hover:text-on-surface'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-4 space-y-3">
        {tab === 'progress' && (
          <div className="space-y-3 text-[12px]">
            <div className="flex justify-between">
              <span className="text-on-surface/50">Status</span>
              <span className="text-on-surface">{getStatusCopy(status)}</span>
            </div>
            {status === 'failed' && (
              <div className="p-2 bg-error/[0.06] border border-error/25 rounded flex gap-2 text-error">
                <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                <span>Operation failed. Check stream diagnostics.</span>
              </div>
            )}
          </div>
        )}

        {tab === 'security' && (
          <div className="space-y-3 text-[12px]">
            <div className="flex items-center justify-between">
              <span className="text-on-surface/50 flex items-center gap-2">
                {diagnostics.sandbox ? <ShieldCheck size={12} className="text-success" /> : <ShieldAlert size={12} className="text-error" />}
                Sandbox
              </span>
              <span className={diagnostics.sandbox ? 'text-success' : 'text-error'}>
                {diagnostics.sandbox === 'appcontainer' ? 'AppContainer (protected)' :
                 diagnostics.sandbox === 'unsandboxed' ? 'NONE — code unisolated' :
                 'Not available'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-on-surface/50 flex items-center gap-2">
                {diagnostics.scrubbing ? <ShieldCheck size={12} className="text-success" /> : <AlertTriangle size={12} className="text-warn" />}
                Data Scrubbing
              </span>
              <span className={diagnostics.scrubbing ? 'text-success' : 'text-warn'}>
                {diagnostics.scrubbing ? 'Enabled' : 'Disabled'}
              </span>
            </div>
          </div>
        )}

        {tab === 'stream' && (
          <div className="space-y-3 text-[12px] font-mono">
            <div className="flex justify-between">
              <span className="text-on-surface/50">Cursor</span>
              <span className="tabular-nums text-on-surface">{diagnostics.cursor ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-on-surface/50">Socket</span>
              <span className={diagnostics.connected ? 'text-success' : 'text-on-surface/60'}>
                {diagnostics.connected ? 'open' : 'closed'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-on-surface/50">Synced</span>
              <span className={diagnostics.synced ? 'text-success' : 'text-warn'}>
                {diagnostics.synced ? 'yes' : 'no'}
              </span>
            </div>
            {diagnostics.resyncs != null && diagnostics.resyncs > 0 && (
              <div className="flex justify-between">
                <span className="text-on-surface/50">Resyncs</span>
                <span className="text-on-surface">{diagnostics.resyncs}</span>
              </div>
            )}
          </div>
        )}

        {tab === 'telemetry' && (
          <div className="space-y-3 text-[12px]">
            {diagnostics.latency_ms != null && (
              <div className="flex justify-between">
                <span className="text-on-surface/50">First token latency</span>
                <span className="font-mono text-on-surface">{diagnostics.latency_ms}ms</span>
              </div>
            )}
            {diagnostics.successRate != null && (
              <div className="flex justify-between">
                <span className="text-on-surface/50">Success rate</span>
                <span className="font-mono text-on-surface">
                  {(diagnostics.successRate * 100).toFixed(1)}%
                </span>
              </div>
            )}
            {diagnostics.turnsToday != null && (
              <div className="flex justify-between">
                <span className="text-on-surface/50">Turns today</span>
                <span className="font-mono text-on-surface">{diagnostics.turnsToday}</span>
              </div>
            )}
            {diagnostics.failedTurns != null && (
              <div className="flex justify-between">
                <span className="text-on-surface/50">Failed</span>
                <span className="font-mono text-on-surface">{diagnostics.failedTurns}</span>
              </div>
            )}
            {diagnostics.benchedProviders != null && diagnostics.benchedProviders > 0 && (
              <div className="flex justify-between p-2 bg-warn/[0.06] border border-warn/25 rounded">
                <span className="text-on-surface/50">Benched providers</span>
                <span className="font-mono text-warn">{diagnostics.benchedProviders}</span>
              </div>
            )}
          </div>
        )}

        {tab === 'reasoning' && diagnostics.thinking && (
          <div className="bg-on-surface/[0.02] rounded p-3 border border-on-surface/[0.05]">
            <p className="text-[11px] leading-5 text-on-surface/60 whitespace-pre-wrap font-mono">
              {diagnostics.thinking}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/* Main AgentStatus component with all 3 levels */
export function AgentStatus(props: AgentStatusProps) {
  const [expanded, setExpanded] = useState(false);
  const [showDeepInspect, setShowDeepInspect] = useState(false);
  const timerRef = useRef<NodeJS.Timeout>();

  const live = !['idle', 'completed', 'failed'].includes(props.status);

  // Auto-expand Level 2 after 2 seconds for live operations
  useEffect(() => {
    if (!live || expanded) return;
    if (props.elapsed < 2) return;

    timerRef.current = setTimeout(() => {
      setExpanded(true);
    }, 2000);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [live, expanded, props.elapsed]);

  return (
    <div className="agent-status space-y-2">
      {/* Level 1: Glance */}
      <Level1Glance
        status={props.status}
        elapsed={props.elapsed}
        live={live}
        onExpand={() => setExpanded(!expanded)}
      />

      {/* Level 2: Expanded (collapsible) */}
      {expanded && (
        <Level2Expanded
          status={props.status}
          elapsed={props.elapsed}
          progress={props.progress}
          recentFiles={props.recentFiles}
          warning={props.warning}
        />
      )}

      {/* Level 3: Deep Inspect (button to toggle) */}
      {expanded && props.diagnostics && (
        <>
          <button
            onClick={() => setShowDeepInspect(!showDeepInspect)}
            className="text-[11px] text-primary hover:text-primary/80 transition duration-150 px-3 py-1.5 -ml-3">
            {showDeepInspect ? 'Hide' : 'Show'} full diagnostics
          </button>
          {showDeepInspect && (
            <Level3DeepInspect
              diagnostics={props.diagnostics}
              status={props.status}
            />
          )}
        </>
      )}
    </div>
  );
}
