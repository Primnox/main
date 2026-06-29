/**
 * MeetingsView — browse and manually manage meeting recordings.
 *
 * Data flow: GET /api/meetings → list of folders with metadata.
 * User can preview the summary and delete individual folders.
 * No auto-deletion happens here; it's all manual review.
 */

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Mic,
  Trash2,
  RefreshCw,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  FileAudio,
  AlertCircle,
  Inbox,
  HardDrive,
} from 'lucide-react';
import { type ScreenId } from '../App';

// ── Types ──────────────────────────────────────────────────────────────────────

interface Meeting {
  name: string;
  date: string;           // ISO-8601
  size_mb: number;
  file_count: number;
  media_files: string[];
  summary: string;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props {
  onNavigate?: (s: ScreenId) => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return iso;
  }
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

function sizeLabel(mb: number): string {
  if (mb < 1) return `${Math.round(mb * 1024)} KB`;
  return `${mb.toFixed(1)} MB`;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function MeetingCard({
  meeting,
  onDelete,
  deleting,
}: {
  meeting: Meeting;
  onDelete: (name: string) => void;
  deleting: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      className="rounded-xl border border-white/[0.06] bg-white/[0.03] overflow-hidden"
    >
      {/* Header row */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-white/[0.04] transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Icon */}
        <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center shrink-0">
          <Mic size={14} className="text-indigo-400" />
        </div>

        {/* Name + date */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white/80 truncate">{meeting.name}</p>
          <p className="text-[11px] text-white/30 mt-0.5">
            {formatDate(meeting.date)} · {formatTime(meeting.date)}
          </p>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-[10px] font-mono text-white/25 hidden sm:block">
            {meeting.file_count} files
          </span>
          <span className="text-[10px] font-mono text-indigo-400/60 bg-indigo-500/10 px-2 py-0.5 rounded">
            {sizeLabel(meeting.size_mb)}
          </span>

          {/* Delete button */}
          {!confirmDelete ? (
            <button
              onClick={(e) => { e.stopPropagation(); setConfirmDelete(true); }}
              disabled={deleting}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white/20 hover:text-red-400 hover:bg-red-500/10 transition-all"
              title="Delete recording"
            >
              <Trash2 size={13} />
            </button>
          ) : (
            <div
              className="flex items-center gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => { onDelete(meeting.name); setConfirmDelete(false); }}
                disabled={deleting}
                className="text-[10px] px-2 py-1 rounded bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors font-mono"
              >
                {deleting ? '…' : 'Delete'}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="text-[10px] px-2 py-1 rounded bg-white/5 text-white/40 hover:bg-white/10 transition-colors font-mono"
              >
                Cancel
              </button>
            </div>
          )}

          {/* Expand chevron */}
          <div className="text-white/20">
            {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </div>
        </div>
      </div>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 border-t border-white/[0.04]">
              {/* Media files */}
              {meeting.media_files.length > 0 && (
                <div className="mt-3">
                  <p className="text-[9px] font-mono uppercase tracking-widest text-white/20 mb-2">
                    Audio / Video
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {meeting.media_files.map((f) => (
                      <div
                        key={f}
                        className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-white/[0.04] border border-white/[0.05]"
                      >
                        <FileAudio size={11} className="text-indigo-400/60" />
                        <span className="text-[10px] font-mono text-white/50">{f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Summary */}
              {meeting.summary ? (
                <div className="mt-3">
                  <p className="text-[9px] font-mono uppercase tracking-widest text-white/20 mb-2">
                    Summary Preview
                  </p>
                  <p className="text-[11px] text-white/40 leading-relaxed line-clamp-4">
                    {meeting.summary}
                  </p>
                </div>
              ) : (
                <p className="mt-3 text-[11px] text-white/20 italic">No summary file found.</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function MeetingsView({ onNavigate: _onNavigate }: Props) {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [deletingName, setDeletingName] = useState<string | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    setError('');
    try {
      const res = await fetch('http://localhost:4009/api/meetings');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { meetings: Meeting[] } = await res.json();
      setMeetings(data.meetings);
    } catch (e: any) {
      setError(e.message || 'Failed to load meetings');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (name: string) => {
    setDeletingName(name);
    try {
      const res = await fetch(`http://localhost:4009/api/meetings/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      setMeetings((prev) => prev.filter((m) => m.name !== name));
    } catch (e: any) {
      setError(`Delete failed: ${e.message}`);
    } finally {
      setDeletingName(null);
    }
  };

  // Totals
  const totalMb    = meetings.reduce((s, m) => s + m.size_mb, 0);
  const totalFiles = meetings.reduce((s, m) => s + m.file_count, 0);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* ── Header ── */}
      <div className="shrink-0 px-6 pt-6 pb-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-sm font-semibold text-white/80 tracking-wide">Meeting Recordings</h1>
            <p className="text-[11px] text-white/30 mt-0.5 font-mono uppercase tracking-widest">
              Manual Review · No Auto-Deletion
            </p>
          </div>

          <button
            onClick={() => load(true)}
            disabled={refreshing || loading}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-white/25 hover:text-white/60 hover:bg-white/5 transition-all"
            title="Refresh"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          </button>
        </div>

        {/* Stats bar */}
        {meetings.length > 0 && (
          <div className="flex items-center gap-4 mt-4">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.05]">
              <FolderOpen size={11} className="text-indigo-400/60" />
              <span className="text-[11px] font-mono text-white/40">
                {meetings.length} recording{meetings.length !== 1 ? 's' : ''}
              </span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.05]">
              <HardDrive size={11} className="text-indigo-400/60" />
              <span className="text-[11px] font-mono text-white/40">
                {sizeLabel(totalMb)} · {totalFiles} files
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ── Error banner ── */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="mx-6 mb-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs"
          >
            <AlertCircle size={13} />
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Content ── */}
      <div className="flex-1 overflow-y-auto px-6 pb-6 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/10">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-white/20 text-xs font-mono">
            Loading recordings…
          </div>
        ) : meetings.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-3 text-white/20">
            <Inbox size={28} strokeWidth={1.5} />
            <p className="text-xs font-mono">No meeting recordings found.</p>
            <p className="text-[10px] text-white/15 text-center max-w-xs">
              Recordings will appear here when Primnox captures a meeting.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <AnimatePresence mode="popLayout">
              {meetings.map((m) => (
                <MeetingCard
                  key={m.name}
                  meeting={m}
                  onDelete={handleDelete}
                  deleting={deletingName === m.name}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
