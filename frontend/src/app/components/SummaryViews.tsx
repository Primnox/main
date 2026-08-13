import { useState, useEffect, useCallback, memo } from 'react';
import { Database, MessageSquare, FileText, CheckCircle, FileEdit, Video, Monitor, Zap, RefreshCw, AlertTriangle, Bell, Shield, ListTodo, Plus, Clock, Trash2, Activity, Radio, Cpu, CalendarDays, MapPin } from 'lucide-react';
import { API_BASE } from '../../config';

type ScreenId =
  | 'summaries_expanded'
  | 'notes_icon_sidebar'
  | 'summaries_empty_state'
  | 'island_settings'
  | 'chat_expanded_sidebar'
  | 'settings_neural'
  | 'logs'
  | 'archive';

// ── Activity Row ─────────────────────────────────────────────────────────────
const FeedRow = ({ event }: { event: string }) => {
  const isAmbient = event.includes('Ambient:');
  const parts = event.split(' - ', 2);
  const time = parts[0]?.trim() || '';
  const raw  = parts[1] || event;
  const content = isAmbient ? raw.replace('Ambient:', '').trim() : raw;

  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-on-surface/[0.03] last:border-0 group">
      <div className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center ${
        isAmbient ? 'bg-primary/10' : 'bg-on-surface/[0.04]'
      }`}>
        {isAmbient
          ? <Radio size={9} className="text-primary/70" />
          : <Monitor size={9} className="text-on-surface/48" />
        }
      </div>
      <p className="flex-1 text-[11px] text-on-surface/55 leading-snug line-clamp-1 font-light group-hover:text-on-surface/80 transition-colors">
        {content}
      </p>
      <span className="shrink-0 font-mono text-[9px] text-on-surface/42">{time}</span>
    </div>
  );
};

// ── Dashboard (SummariesExpanded) ────────────────────────────────────────────
export const SummariesExpanded = memo(({
  onNavigate,
  activity: _activity = [],
  tasks = [],
  onTaskCompleted,
}: {
  onNavigate: (id: ScreenId) => void;
  activity?: any[];
  tasks?: any[];
  onTaskCompleted?: () => void;
}) => {
  const [dash, setDash] = useState<any>(null);
  const [briefStatus, setBriefStatus] = useState<'idle' | 'generating' | 'done'>('idle');
  const [dashFailCount, setDashFailCount] = useState(0);
  // Quick-add reminder state
  const [reminderMsg, setReminderMsg] = useState('');
  const [reminderMins, setReminderMins] = useState('30');
  const [addingReminder, setAddingReminder] = useState(false);
  const [reminderFeedback, setReminderFeedback] = useState<'ok' | 'err' | null>(null);
  // Quick-add task state
  const [newTaskText, setNewTaskText] = useState('');
  const [newTaskPriority, setNewTaskPriority] = useState<'normal' | 'urgent' | 'low'>('normal');
  const [addingTask, setAddingTask] = useState(false);
  const [taskFeedback, setTaskFeedback] = useState<'ok' | 'err' | null>(null);

  const fetchDash = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/dashboard`, {
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        setDash(await res.json());
        setDashFailCount(0);
      } else {
        setDashFailCount(c => c + 1);
      }
    } catch {
      setDashFailCount(c => c + 1);
    }
  }, []);

  // Fetch once on mount. Deliberately separate from the polling effect below:
  // when the two were combined, a failed fetch incremented `dashFailCount`,
  // which re-ran the effect, which called `fetchDash()` again immediately.
  // With the backend unreachable a fetch rejects in microseconds, so that loop
  // spun at ~500 requests/second for as long as the dashboard was open —
  // measured at 5036 requests to /api/dashboard in 10s — pinning a CPU core
  // and completely defeating the backoff below, whose interval was torn down
  // and rebuilt before it could ever fire.
  useEffect(() => {
    fetchDash();
  }, [fetchDash]);

  // Exponential backoff: 30s → 60s → 120s → capped at 120s.
  // Re-arms when the failure count changes, but never fetches on re-arm.
  useEffect(() => {
    const delay = Math.min(120_000, 30_000 * Math.pow(2, Math.min(dashFailCount, 2)));
    const id = setInterval(fetchDash, delay);
    return () => clearInterval(id);
  }, [fetchDash, dashFailCount]);

  const triggerBrief = async () => {
    setBriefStatus('generating');
    try {
      await fetch(`${API_BASE}/api/daily_brief`, { method: 'POST' });
      // Brief is dispatched as a background task — generation is async.
      // Show "Requested" (not "Sent to chat ✓") so the user knows it's in progress.
      setBriefStatus('done');
      setTimeout(() => setBriefStatus('idle'), 6000);
    } catch (_) {
      setBriefStatus('idle');
    }
  };

  const completeTask = async (id: number) => {
    try {
      await fetch(`${API_BASE}/tasks/${id}/complete`, { method: 'POST' });
      onTaskCompleted?.();
    } catch (_) {}
  };

  const showFeedback = (setter: (v: 'ok' | 'err' | null) => void, result: 'ok' | 'err') => {
    setter(result);
    setTimeout(() => setter(null), 2500);
  };

  const submitReminder = async () => {
    const msg = reminderMsg.trim();
    const mins = parseInt(reminderMins, 10);
    if (!msg || isNaN(mins) || mins < 1) return;
    setAddingReminder(true);
    try {
      const res = await fetch(`${API_BASE}/api/reminders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, delay_secs: mins * 60 }),
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setReminderMsg('');
      setReminderMins('30');
      showFeedback(setReminderFeedback, 'ok');
      fetchDash();
    } catch {
      showFeedback(setReminderFeedback, 'err');
    } finally {
      setAddingReminder(false);
    }
  };

  const submitTask = async () => {
    const text = newTaskText.trim();
    if (!text) return;
    setAddingTask(true);
    try {
      const res = await fetch(`${API_BASE}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, priority: newTaskPriority }),
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setNewTaskText('');
      setNewTaskPriority('normal');
      showFeedback(setTaskFeedback, 'ok');
      onTaskCompleted?.();
    } catch {
      showFeedback(setTaskFeedback, 'err');
    } finally {
      setAddingTask(false);
    }
  };

  const feed: string[]  = dash?.feed_history ?? [];
  const meetings: any[] = dash?.meetings ?? [];
  const pendingTasks    = tasks.filter((t: any) => !t.completed && !t.is_complete);
  const doneTasks       = tasks.filter((t: any) => t.completed || t.is_complete);

  // Greeting + a single "what matters right now" focal line for the hero
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const clip = (s: string) => (s && s.length > 46 ? s.slice(0, 46) + '…' : s);
  const _urgent   = pendingTasks.find((t: any) => t.priority === 'urgent');
  const _rem      = dash?.reminders?.[0];
  const _nextEv   = (dash?.today_events ?? []).find((e: any) => {
    if (!e.start_dt || e.all_day) return false;
    return new Date(e.start_dt) >= new Date();
  });
  const focus =
    _urgent  ? `Urgent — ${clip(_urgent.text)}` :
    _rem     ? `Soon — ${clip(_rem.message)}` :
    _nextEv  ? `Next — ${clip(_nextEv.title)}` :
    pendingTasks[0] ? `Up next — ${clip(pendingTasks[0].text)}` : '';

  const totalTasks = pendingTasks.length + doneTasks.length;
  const taskPct = totalTasks > 0 ? Math.round((doneTasks.length / totalTasks) * 100) : 0;

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="max-w-5xl mx-auto px-5 py-6 space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]">

        {/* ── API Key Banner ── */}
        {dash && !dash.has_api_key && (
          <div className="flex items-center justify-between gap-4 px-4 py-2.5 bg-warn/8 border border-warn/20 rounded-xl">
            <div className="flex items-center gap-2.5">
              <AlertTriangle size={12} className="text-warn shrink-0" />
              <p className="text-xs text-warn/70 font-light">No API key configured — Primnox can't think.</p>
            </div>
            <button onClick={() => onNavigate('island_settings')}
              className="shrink-0 px-3 py-1 bg-warn/15 border border-warn/25 text-warn rounded-lg font-mono text-[9px] uppercase tracking-widest hover:bg-warn/25 transition-all">
              Fix →
            </button>
          </div>
        )}

        {/* ── Hero ──
            The site opens every section flush to a hairline rule with no card
            around it, so the rounded gradient panel and its zinc-900 (a
            hardcoded dark that ignored the theme) are gone. */}
        <div className="relative pt-2 pb-6 px-1 border-b border-on-surface/[0.09]">
          <div className="relative flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="w-1.5 h-1.5 rounded-full bg-success/25 shadow-[0_0_8px_rgba(52,211,153,0.6)] animate-pulse" />
                <span className="font-mono text-[9px] text-on-surface/52 uppercase tracking-[0.4em]">
                  {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })}
                </span>
                {/* PII shield badge */}
                {dash?.pii_model_status === 'ready' && (
                  <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-success/8 border border-success/15">
                    <Shield size={7} className="text-success/60" />
                    <span className="font-mono text-[7px] text-success/50 uppercase tracking-widest">shield on</span>
                  </span>
                )}
                {dash?.pii_model_status === 'loading' && (
                  <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-warn/8 border border-warn/15">
                    <Shield size={7} className="text-warn/50" />
                    <span className="font-mono text-[7px] text-warn/60 uppercase tracking-widest">shield loading</span>
                  </span>
                )}
              </div>
              {/* Big uppercase Syne with the name set as the italic-400
                  counterpoint — the site's hero treatment. */}
              <h2 className="px-display px-display-lg text-on-surface mt-2">
                {greeting}
                {dash?.user_name ? (
                  <i>{' '}{dash.user_name.replace(/_/g, ' ').split(' ')[0]}</i>
                ) : null}
              </h2>
              {focus && (
                <p className="px-body text-sm mt-3 truncate max-w-[52ch]">
                  <span className="text-primary">→</span> {focus}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0 pt-0.5">
              <button onClick={fetchDash}
                className="p-1.5 rounded-lg text-on-surface/48 hover:text-on-surface/60 hover:bg-on-surface/5 transition-all" title="Refresh">
                <RefreshCw size={12} />
              </button>
              <button onClick={triggerBrief} disabled={briefStatus === 'generating'}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 border border-primary/20 text-primary rounded-xl font-mono text-[9px] uppercase tracking-widest hover:bg-primary hover:text-surface transition-all disabled:opacity-40 active:scale-95">
                <Zap size={10} />
                {briefStatus === 'generating' ? 'Thinking...' : briefStatus === 'done' ? 'Sent ✓' : 'Brief'}
              </button>
            </div>
          </div>

          {/* Task progress strip */}
          {totalTasks > 0 && (
            <div className="relative mt-4 pt-3 border-t border-on-surface/[0.05]">
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-mono text-[9px] text-on-surface/48 uppercase tracking-[0.3em]">Task_Progress</span>
                <span className="font-mono text-[9px] text-on-surface/55">{doneTasks.length}/{totalTasks} · {taskPct}%</span>
              </div>
              <div className="h-1 bg-on-surface/[0.05] rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary/70 to-primary/70 rounded-full transition-all duration-700"
                  style={{ width: `${taskPct}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Stat strip ──
            Was a four-tile band (Tasks / Notes / Memories / Skills) sized like
            a hero. Memories and Skills report what Primnox knows, not anything
            the user can act on, so they earned none of that space; the two that
            do are now one hairline row and the hero belongs to the brief. */}
        <div className="flex items-center gap-6 px-4 py-2.5 border-t border-b border-on-surface/[0.09]">
          <span className="flex items-center gap-2">
            <ListTodo size={11} className="text-on-surface/52" />
            <span className="px-label">Tasks</span>
            <span className="font-mono text-[11px] text-on-surface">{pendingTasks.length}</span>
            <span className="font-mono text-[9px] text-on-surface/52">{doneTasks.length} done</span>
          </span>
          <span className="flex items-center gap-2">
            <FileEdit size={11} className="text-on-surface/52" />
            <span className="px-label">Notes</span>
            <span className="font-mono text-[11px] text-on-surface">{dash?.notes_count ?? '—'}</span>
          </span>
        </div>

        {/* ── Main grid ── */}
        <div className="grid grid-cols-12 gap-4">

          {/* ── Left col (7) ── */}
          <div className="col-span-12 lg:col-span-7 flex flex-col gap-4">

            {/* Activity Feed */}
            <div className="bg-[var(--surface)] border border-on-surface/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-on-surface/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity size={11} className="text-primary/50" />
                  <span className="font-mono text-[9px] text-on-surface/58 uppercase tracking-[0.35em]">Activity_Feed</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-1 h-1 rounded-full bg-primary/60 animate-pulse" />
                  <span className="font-mono text-[8px] text-on-surface/42">{feed.length}</span>
                </div>
              </div>
              <div className="px-4 py-2 max-h-52 overflow-y-auto custom-scrollbar">
                {feed.length === 0 ? (
                  <div className="py-8 text-center">
                    <Radio size={16} className="text-on-surface/38 mx-auto mb-2" />
                    <p className="font-mono text-[9px] text-on-surface/38 uppercase tracking-widest">listening...</p>
                  </div>
                ) : (
                  [...feed].reverse().map((e, i) => <FeedRow key={i} event={e} />)
                )}
              </div>
            </div>

            {/* Context row: focus + backup */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-[var(--surface)] border border-on-surface/[0.06] rounded-xl p-4 group hover:border-on-surface/10 transition-all">
                <div className="flex items-center gap-1.5 mb-2">
                  <Cpu size={10} className="text-on-surface/48" />
                  <span className="font-mono text-[8px] text-on-surface/48 uppercase tracking-[0.35em]">In_Focus</span>
                </div>
                {dash ? (
                  <>
                    <p className="text-sm font-semibold text-on-surface/75 truncate leading-tight">{dash.active_process || '—'}</p>
                    <p className="text-[9px] text-on-surface/52 font-mono truncate mt-0.5">{dash.active_window || '—'}</p>
                  </>
                ) : (
                  <p className="text-[9px] text-on-surface/42 font-mono">syncing...</p>
                )}
              </div>
              <div className="bg-[var(--surface)] border border-on-surface/[0.06] rounded-xl p-4 hover:border-on-surface/10 transition-all">
                <div className="flex items-center gap-1.5 mb-2">
                  <Shield size={10} className={dash?.last_backup ? 'text-success/60' : 'text-on-surface/48'} />
                  <span className="font-mono text-[8px] text-on-surface/48 uppercase tracking-[0.35em]">Backup</span>
                </div>
                {dash?.last_backup ? (
                  <>
                    <p className="text-sm font-semibold text-success/70">{dash.last_backup.size_kb} KB</p>
                    <p className="text-[9px] text-on-surface/52 font-mono truncate mt-0.5">
                      {dash.last_backup.filename.replace('backup_', '').replace('.zip', '')}
                    </p>
                  </>
                ) : (
                  <p className="text-[9px] text-on-surface/42 font-mono">no backup yet</p>
                )}
              </div>
            </div>

            {/* Quick nav */}
            <div className="grid grid-cols-4 gap-2">
              {([
                { label: 'Chat',     icon: MessageSquare, screen: 'chat_expanded_sidebar', color: 'hover:border-primary/30 hover:bg-primary/5 hover:text-primary' },
                { label: 'Notes',    icon: FileText,      screen: 'notes_icon_sidebar',    color: 'hover:border-primary/30 hover:bg-primary/5 hover:text-primary' },
                { label: 'Archive',  icon: Database,      screen: 'archive',               color: 'hover:border-primary/30 hover:bg-primary/5 hover:text-primary' },
                { label: 'Meetings', icon: Video,         screen: 'logs',                  color: 'hover:border-success/30 hover:bg-success/5 hover:text-success' },
              ] as { label: string; icon: any; screen: ScreenId; color: string }[]).map(({ label, icon: Icon, screen, color }) => (
                <button key={screen} onClick={() => onNavigate(screen)}
                  className={`flex flex-col items-center gap-1.5 py-3 bg-[var(--surface)] border border-on-surface/[0.05] rounded-xl transition-all duration-150 group ${color}`}>
                  <Icon size={13} className="text-on-surface/48 group-hover:text-inherit transition-colors" />
                  <span className="font-mono text-[8px] text-on-surface/52 group-hover:text-inherit uppercase tracking-widest transition-colors">{label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* ── Right col (5) ── */}
          <div className="col-span-12 lg:col-span-5 flex flex-col gap-4">

            {/* Today's Events */}
            <div className="bg-[var(--surface)] border border-on-surface/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-on-surface/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CalendarDays size={11} className="text-primary/50" />
                  <span className="font-mono text-[9px] text-on-surface/55 uppercase tracking-[0.35em]">Today</span>
                </div>
                <span className="font-mono text-[8px] text-on-surface/42">
                  {(dash?.today_events ?? []).length} events
                </span>
              </div>
              {(dash?.today_events ?? []).length === 0 ? (
                <p className="px-4 py-3 font-mono text-[9px] text-on-surface/42">nothing scheduled ·</p>
              ) : (
                <div className="divide-y divide-on-surface/[0.03] max-h-44 overflow-y-auto custom-scrollbar">
                  {(dash?.today_events ?? []).map((ev: any) => {
                    const start = ev.start_dt ? new Date(ev.start_dt) : null;
                    const timeStr = start && !ev.all_day
                      ? start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
                      : 'All day';
                    const dot = ev.color || '#6366f1';
                    return (
                      <div key={ev.id} className="px-4 py-2 flex items-center gap-2.5 group">
                        <span className="shrink-0 w-1.5 h-1.5 rounded-full mt-0.5" style={{ backgroundColor: dot, boxShadow: `0 0 6px ${dot}55` }} />
                        <div className="min-w-0 flex-1">
                          <p className="text-xs text-on-surface/65 font-light truncate">{ev.title}</p>
                          {ev.location && (
                            <p className="text-[9px] text-on-surface/48 font-mono flex items-center gap-1 mt-0.5 truncate">
                              <MapPin size={7} /> {ev.location}
                            </p>
                          )}
                        </div>
                        <span className="shrink-0 font-mono text-[8px] text-on-surface/52 whitespace-nowrap">{timeStr}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Tasks */}
            <div className="bg-[var(--surface)] border border-on-surface/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-on-surface/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ListTodo size={11} className="text-primary/50" />
                  <span className="font-mono text-[9px] text-on-surface/55 uppercase tracking-[0.35em]">Tasks</span>
                </div>
                <span className="font-mono text-[8px] text-on-surface/42">{pendingTasks.length} open</span>
              </div>

              <div className="px-4 pt-3 pb-2 flex gap-2">
                <input type="text" value={newTaskText}
                  onChange={e => setNewTaskText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submitTask()}
                  placeholder="Add task..."
                  className="flex-1 bg-surface/40 border border-on-surface/[0.05] rounded-lg px-3 py-1.5 text-xs text-on-surface placeholder:text-on-surface/38 outline-none focus:border-primary/25 transition-colors" />
                <select value={newTaskPriority}
                  onChange={e => setNewTaskPriority(e.target.value as 'normal' | 'urgent' | 'low')}
                  className="bg-surface/40 border border-on-surface/[0.05] rounded-lg px-2 text-[9px] text-on-surface/58 outline-none font-mono">
                  <option value="low">low</option>
                  <option value="normal">—</option>
                  <option value="urgent">!</option>
                </select>
                <button onClick={submitTask} disabled={!newTaskText.trim() || addingTask}
                  aria-label="Add task"
                  className={`p-1.5 border rounded-lg disabled:opacity-25 transition-all active:scale-95 ${
                    taskFeedback === 'ok'  ? 'bg-success/15 border-success/25 text-success' :
                    taskFeedback === 'err' ? 'bg-error/15 border-error/25 text-error' :
                    'bg-primary/8 border-primary/15 text-primary/60 hover:bg-primary/15'
                  }`}>
                  {taskFeedback === 'ok' ? '✓' : taskFeedback === 'err' ? '✗' : <Plus size={11} />}
                </button>
              </div>

              {pendingTasks.length === 0 ? (
                <p className="px-4 py-3 font-mono text-[9px] text-on-surface/42">all clear ✓</p>
              ) : (
                <div className="divide-y divide-on-surface/[0.03] max-h-40 overflow-y-auto custom-scrollbar">
                  {pendingTasks.slice(0, 6).map((t: any) => (
                    <div key={t.id} className="px-4 py-2 flex items-center gap-2.5 group">
                      <button onClick={() => completeTask(t.id)}
                        className="shrink-0 w-3.5 h-3.5 rounded border border-on-surface/10 group-hover:border-primary/35 flex items-center justify-center hover:bg-primary/10 transition-all">
                        <CheckCircle size={8} className="text-transparent group-hover:text-primary/50 transition-colors" />
                      </button>
                      <p className={`text-xs font-light truncate flex-1 ${
                        t.priority === 'urgent' ? 'text-error/70' : 'text-on-surface/50'
                      }`}>{t.text}</p>
                      {t.priority === 'urgent' && (
                        <span className="shrink-0 font-mono text-[7px] px-1 py-0.5 rounded bg-error/10 text-error/70">urgent</span>
                      )}
                      <button onClick={async () => { await fetch(`${API_BASE}/tasks/${t.id}`, { method: 'DELETE' }); onTaskCompleted?.(); }}
                        className="shrink-0 opacity-0 group-hover:opacity-100 text-on-surface/42 hover:text-error transition-all">
                        <Trash2 size={9} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Reminders */}
            <div className="bg-[var(--surface)] border border-on-surface/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-on-surface/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bell size={11} className="text-warn/50" />
                  <span className="font-mono text-[9px] text-on-surface/55 uppercase tracking-[0.35em]">Reminders</span>
                </div>
                <span className="font-mono text-[8px] text-on-surface/42">{dash?.reminders_count ?? 0} set</span>
              </div>

              <div className="px-4 pt-3 pb-2 flex gap-2">
                <input type="text" value={reminderMsg}
                  onChange={e => setReminderMsg(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submitReminder()}
                  placeholder="Remind me to..."
                  className="flex-1 bg-surface/40 border border-on-surface/[0.05] rounded-lg px-3 py-1.5 text-xs text-on-surface placeholder:text-on-surface/38 outline-none focus:border-warn/25 transition-colors" />
                <input type="number" value={reminderMins} onChange={e => setReminderMins(e.target.value)} min="1"
                  className="w-12 bg-surface/40 border border-on-surface/[0.05] rounded-lg px-2 py-1.5 text-xs text-on-surface/50 outline-none font-mono text-center" />
                <button onClick={submitReminder} disabled={!reminderMsg.trim() || addingReminder}
                  aria-label="Add reminder"
                  className={`p-1.5 border rounded-lg disabled:opacity-25 transition-all active:scale-95 ${
                    reminderFeedback === 'ok'  ? 'bg-success/15 border-success/25 text-success' :
                    reminderFeedback === 'err' ? 'bg-error/15 border-error/25 text-error' :
                    'bg-warn/8 border-warn/15 text-warn/60 hover:bg-warn/15'
                  }`}>
                  {reminderFeedback === 'ok' ? '✓' : reminderFeedback === 'err' ? '✗' : <Plus size={11} />}
                </button>
              </div>

              {dash?.reminders && dash.reminders.length > 0 ? (
                <div className="divide-y divide-on-surface/[0.03]">
                  {dash.reminders.slice(0, 3).map((r: any) => {
                    const mins = Math.ceil(r.seconds_remaining / 60);
                    return (
                      <div key={r.id} className="px-4 py-2 flex items-center gap-2.5 group">
                        <Clock size={9} className="text-warn/58 shrink-0" />
                        <p className="text-xs text-on-surface/50 font-light truncate flex-1">{r.message}</p>
                        <span className="shrink-0 font-mono text-[8px] text-warn/50 bg-warn/8 px-1.5 py-0.5 rounded-full whitespace-nowrap">
                          {mins < 1 ? '<1m' : `${mins}m`}
                        </span>
                        <button onClick={async () => { await fetch(`${API_BASE}/api/reminders/${r.id}`, { method: 'DELETE' }); fetchDash(); }}
                          className="shrink-0 opacity-0 group-hover:opacity-100 text-on-surface/42 hover:text-error transition-all text-xs">×</button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="px-4 py-3 font-mono text-[9px] text-on-surface/42">none set</p>
              )}
            </div>

            {/* Recent Meetings */}
            <div className="bg-[var(--surface)] border border-on-surface/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-on-surface/[0.05] flex items-center gap-2">
                <Video size={11} className="text-on-surface/48" />
                <span className="font-mono text-[9px] text-on-surface/52 uppercase tracking-[0.35em]">Meetings</span>
              </div>
              <div className="divide-y divide-on-surface/[0.03]">
                {meetings.length === 0 ? (
                  <p className="px-4 py-3 font-mono text-[9px] text-on-surface/42">no recordings yet</p>
                ) : (
                  meetings.slice(0, 3).map((m: any) => (
                    <div key={m.name} className="px-4 py-2.5 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs text-on-surface/55 font-mono truncate">{m.name}</p>
                        {m.summary_preview && (
                          <p className="text-[9px] text-on-surface/48 mt-0.5 line-clamp-1 font-light">{m.summary_preview}</p>
                        )}
                      </div>
                      <span className={`shrink-0 text-[7px] font-mono px-1.5 py-0.5 rounded-full ${
                        m.has_summary ? 'bg-success/10 text-success/70' : 'bg-on-surface/5 text-on-surface/42'
                      }`}>{m.has_summary ? 'ai summary' : 'raw'}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
});

export const SummariesEmptyState = ({ onNavigate }: { onNavigate: (id: ScreenId) => void }) => (
  <div className="p-12 lg:p-20 h-full flex flex-col justify-center items-center text-center animate-in fade-in slide-in-from-bottom-8 duration-1000">
      <div className="relative mb-12">
        <div className="w-32 h-32 rounded-full border border-on-surface/5 flex items-center justify-center relative">
          <div className="absolute inset-0 border border-primary/20 rounded-full animate-ping [animation-duration:3s]" />
          <Database size={48} className="text-primary/60" />
        </div>
        <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 bg-surface border border-on-surface/10 px-3 py-1 rounded font-mono text-[8px] text-primary uppercase">Idle_State</div>
      </div>
      
      <h1 className="font-bold lowercase italic tracking-wide text-4xl text-on-surface mb-4">No Active Sessions Found</h1>
      <p className="text-on-surface-variant max-w-sm leading-relaxed mb-12 opacity-60 lowercase">The neural nexus is currently in stasis. Initialize a new analysis task to begin data orchestration.</p>
      
      <div className="flex flex-col gap-4">
        <button 
          onClick={() => onNavigate('summaries_expanded')}
          className="bg-primary text-surface font-mono px-12 py-4 uppercase text-[11px] font-bold tracking-[0.2em] hover:brightness-110 transition-all shadow-[0_0_30px_rgba(79,70,229,0.2)]"
        >
          Initialize_Analysis
        </button>
        <a 
          href="#" 
          onClick={(e) => { e.preventDefault(); onNavigate('notes_icon_sidebar'); }}
          className="text-[10px] text-on-surface/55 hover:text-primary transition-colors font-mono uppercase tracking-widest"
        >
          historical_archive
        </a>
      </div>
    </div>
);
