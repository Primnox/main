import { useState, useEffect, useCallback, memo } from 'react';
import { Database, MessageSquare, FileText, CheckCircle, Terminal, Brain, FileEdit, Video, Monitor, Zap, RefreshCw, AlertTriangle, Bell, Shield, ListTodo, Plus, Clock, Trash2, Activity, Radio, Cpu, CalendarDays, MapPin } from 'lucide-react';

type ScreenId =
  | 'summaries_expanded'
  | 'notes_icon_sidebar'
  | 'summaries_sidebar_hidden'
  | 'summaries_empty_state'
  | 'island_settings'
  | 'summaries_icon_sidebar'
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
    <div className="flex items-center gap-3 py-2.5 border-b border-white/[0.03] last:border-0 group">
      <div className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center ${
        isAmbient ? 'bg-primary/10' : 'bg-white/[0.04]'
      }`}>
        {isAmbient
          ? <Radio size={9} className="text-primary/70" />
          : <Monitor size={9} className="text-white/20" />
        }
      </div>
      <p className="flex-1 text-[11px] text-white/55 leading-snug line-clamp-1 font-light group-hover:text-white/80 transition-colors">
        {content}
      </p>
      <span className="shrink-0 font-mono text-[9px] text-white/15">{time}</span>
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
      const res = await fetch('http://localhost:4009/api/dashboard', {
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

  // Exponential backoff: 30s → 60s → 120s → capped at 120s
  useEffect(() => {
    fetchDash();
    const delay = Math.min(120_000, 30_000 * Math.pow(2, Math.min(dashFailCount, 2)));
    const id = setInterval(fetchDash, delay);
    return () => clearInterval(id);
  }, [fetchDash, dashFailCount]);

  const triggerBrief = async () => {
    setBriefStatus('generating');
    try {
      await fetch('http://localhost:4009/api/daily_brief', { method: 'POST' });
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
      await fetch(`http://localhost:4009/tasks/${id}/complete`, { method: 'POST' });
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
      const res = await fetch('http://localhost:4009/api/reminders', {
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
      const res = await fetch('http://localhost:4009/tasks', {
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
          <div className="flex items-center justify-between gap-4 px-4 py-2.5 bg-amber-500/8 border border-amber-500/20 rounded-xl">
            <div className="flex items-center gap-2.5">
              <AlertTriangle size={12} className="text-amber-400 shrink-0" />
              <p className="text-xs text-amber-300/70 font-light">No API key configured — Primnox can't think.</p>
            </div>
            <button onClick={() => onNavigate('island_settings')}
              className="shrink-0 px-3 py-1 bg-amber-500/15 border border-amber-500/25 text-amber-300 rounded-lg font-mono text-[9px] uppercase tracking-widest hover:bg-amber-500/25 transition-all">
              Fix →
            </button>
          </div>
        )}

        {/* ── Hero ── */}
        <div className="relative overflow-hidden rounded-2xl border border-white/[0.07] bg-gradient-to-br from-zinc-900/80 via-zinc-900/60 to-primary/[0.04] p-5">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(99,102,241,0.08),transparent_60%)] pointer-events-none" />
          <div className="relative flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)] animate-pulse" />
                <span className="font-mono text-[9px] text-white/25 uppercase tracking-[0.4em]">
                  {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })}
                </span>
                {/* PII shield badge */}
                {dash?.pii_model_status === 'ready' && (
                  <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-emerald-500/8 border border-emerald-500/15">
                    <Shield size={7} className="text-emerald-400/60" />
                    <span className="font-mono text-[7px] text-emerald-400/50 uppercase tracking-widest">shield on</span>
                  </span>
                )}
                {dash?.pii_model_status === 'loading' && (
                  <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-500/8 border border-amber-500/15">
                    <Shield size={7} className="text-amber-400/50" />
                    <span className="font-mono text-[7px] text-amber-400/40 uppercase tracking-widest">shield loading</span>
                  </span>
                )}
              </div>
              <h2 className="text-3xl font-bold text-white tracking-tight leading-tight">
                {greeting}
                {dash?.user_name ? (
                  <span className="text-primary/70">{' '}{dash.user_name.replace(/_/g, ' ').split(' ')[0]}</span>
                ) : null}
              </h2>
              {focus && (
                <p className="text-sm text-white/35 mt-1.5 font-light truncate">
                  <span className="text-primary/60">→</span> {focus}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0 pt-0.5">
              <button onClick={fetchDash}
                className="p-1.5 rounded-lg text-white/20 hover:text-white/60 hover:bg-white/5 transition-all" title="Refresh">
                <RefreshCw size={12} />
              </button>
              <button onClick={triggerBrief} disabled={briefStatus === 'generating'}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 border border-primary/20 text-primary rounded-xl font-mono text-[9px] uppercase tracking-widest hover:bg-primary hover:text-black transition-all disabled:opacity-40 active:scale-95">
                <Zap size={10} />
                {briefStatus === 'generating' ? 'Thinking...' : briefStatus === 'done' ? 'Sent ✓' : 'Brief'}
              </button>
            </div>
          </div>

          {/* Task progress strip */}
          {totalTasks > 0 && (
            <div className="relative mt-4 pt-3 border-t border-white/[0.05]">
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-mono text-[9px] text-white/20 uppercase tracking-[0.3em]">Task_Progress</span>
                <span className="font-mono text-[9px] text-white/30">{doneTasks.length}/{totalTasks} · {taskPct}%</span>
              </div>
              <div className="h-1 bg-white/[0.05] rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary/70 to-violet-400/70 rounded-full transition-all duration-700"
                  style={{ width: `${taskPct}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Stat Row ── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Tasks',    value: pendingTasks.length, icon: ListTodo, sub: `${doneTasks.length} done`,       glow: 'shadow-violet-500/10',  border: 'hover:border-violet-500/20', accent: 'text-violet-300',  bg: 'bg-violet-500/10 border-violet-500/20' },
            { label: 'Notes',    value: dash?.notes_count ?? '—', icon: FileEdit, sub: 'in workspace',             glow: 'shadow-sky-500/10',     border: 'hover:border-sky-500/20',    accent: 'text-sky-300',     bg: 'bg-sky-500/10 border-sky-500/20' },
            { label: 'Memories', value: dash?.memories_count ?? '—', icon: Brain, sub: 'stored',                  glow: 'shadow-primary/10',     border: 'hover:border-primary/20',    accent: 'text-primary',     bg: 'bg-primary/10 border-primary/20' },
            { label: 'Skills',   value: dash?.skills_count ?? '—', icon: Zap,   sub: 'loaded',                    glow: 'shadow-amber-500/10',   border: 'hover:border-amber-500/20',  accent: 'text-amber-300',   bg: 'bg-amber-500/10 border-amber-500/20' },
          ].map(({ label, value, icon: Icon, sub, glow, border, accent, bg }) => (
            <div key={label} className={`relative bg-zinc-900/50 border border-white/[0.06] rounded-2xl p-4 flex flex-col gap-2.5 hover:-translate-y-0.5 transition-all duration-200 shadow-lg ${glow} ${border} overflow-hidden group`}>
              <div className="absolute inset-0 bg-gradient-to-br from-white/[0.02] to-transparent pointer-events-none" />
              <div className="flex items-center justify-between">
                <div className={`w-7 h-7 rounded-lg border flex items-center justify-center ${bg}`}>
                  <Icon size={13} className={accent} />
                </div>
                <span className="font-mono text-[8px] text-white/20 uppercase tracking-[0.35em]">{label}</span>
              </div>
              <div>
                <p className={`text-2xl font-black tracking-tight leading-none ${accent}`}>{value}</p>
                <p className="text-[9px] text-white/25 font-mono mt-1">{sub}</p>
              </div>
            </div>
          ))}
        </div>

        {/* ── Main grid ── */}
        <div className="grid grid-cols-12 gap-4">

          {/* ── Left col (7) ── */}
          <div className="col-span-12 lg:col-span-7 flex flex-col gap-4">

            {/* Activity Feed */}
            <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity size={11} className="text-primary/50" />
                  <span className="font-mono text-[9px] text-white/35 uppercase tracking-[0.35em]">Activity_Feed</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-1 h-1 rounded-full bg-primary/60 animate-pulse" />
                  <span className="font-mono text-[8px] text-white/15">{feed.length}</span>
                </div>
              </div>
              <div className="px-4 py-2 max-h-52 overflow-y-auto custom-scrollbar">
                {feed.length === 0 ? (
                  <div className="py-8 text-center">
                    <Radio size={16} className="text-white/8 mx-auto mb-2" />
                    <p className="font-mono text-[9px] text-white/12 uppercase tracking-widest">listening...</p>
                  </div>
                ) : (
                  [...feed].reverse().map((e, i) => <FeedRow key={i} event={e} />)
                )}
              </div>
            </div>

            {/* Context row: focus + backup */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-zinc-900/40 border border-white/[0.06] rounded-xl p-4 group hover:border-white/10 transition-all">
                <div className="flex items-center gap-1.5 mb-2">
                  <Cpu size={10} className="text-white/20" />
                  <span className="font-mono text-[8px] text-white/20 uppercase tracking-[0.35em]">In_Focus</span>
                </div>
                {dash ? (
                  <>
                    <p className="text-sm font-semibold text-white/75 truncate leading-tight">{dash.active_process || '—'}</p>
                    <p className="text-[9px] text-white/25 font-mono truncate mt-0.5">{dash.active_window || '—'}</p>
                  </>
                ) : (
                  <p className="text-[9px] text-white/15 font-mono">syncing...</p>
                )}
              </div>
              <div className="bg-zinc-900/40 border border-white/[0.06] rounded-xl p-4 hover:border-white/10 transition-all">
                <div className="flex items-center gap-1.5 mb-2">
                  <Shield size={10} className={dash?.last_backup ? 'text-emerald-400/40' : 'text-white/20'} />
                  <span className="font-mono text-[8px] text-white/20 uppercase tracking-[0.35em]">Backup</span>
                </div>
                {dash?.last_backup ? (
                  <>
                    <p className="text-sm font-semibold text-emerald-400/70">{dash.last_backup.size_kb} KB</p>
                    <p className="text-[9px] text-white/25 font-mono truncate mt-0.5">
                      {dash.last_backup.filename.replace('backup_', '').replace('.zip', '')}
                    </p>
                  </>
                ) : (
                  <p className="text-[9px] text-white/15 font-mono">no backup yet</p>
                )}
              </div>
            </div>

            {/* Quick nav */}
            <div className="grid grid-cols-4 gap-2">
              {([
                { label: 'Chat',     icon: MessageSquare, screen: 'chat_expanded_sidebar', color: 'hover:border-primary/30 hover:bg-primary/5 hover:text-primary' },
                { label: 'Notes',    icon: FileText,      screen: 'notes_icon_sidebar',    color: 'hover:border-sky-500/30 hover:bg-sky-500/5 hover:text-sky-300' },
                { label: 'Archive',  icon: Database,      screen: 'archive',               color: 'hover:border-violet-500/30 hover:bg-violet-500/5 hover:text-violet-300' },
                { label: 'Meetings', icon: Video,         screen: 'logs',                  color: 'hover:border-emerald-500/30 hover:bg-emerald-500/5 hover:text-emerald-300' },
              ] as { label: string; icon: any; screen: ScreenId; color: string }[]).map(({ label, icon: Icon, screen, color }) => (
                <button key={screen} onClick={() => onNavigate(screen)}
                  className={`flex flex-col items-center gap-1.5 py-3 bg-zinc-900/30 border border-white/[0.05] rounded-xl transition-all duration-150 group ${color}`}>
                  <Icon size={13} className="text-white/20 group-hover:text-inherit transition-colors" />
                  <span className="font-mono text-[8px] text-white/25 group-hover:text-inherit uppercase tracking-widest transition-colors">{label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* ── Right col (5) ── */}
          <div className="col-span-12 lg:col-span-5 flex flex-col gap-4">

            {/* Today's Events */}
            <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CalendarDays size={11} className="text-sky-400/50" />
                  <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.35em]">Today</span>
                </div>
                <span className="font-mono text-[8px] text-white/15">
                  {(dash?.today_events ?? []).length} events
                </span>
              </div>
              {(dash?.today_events ?? []).length === 0 ? (
                <p className="px-4 py-3 font-mono text-[9px] text-white/15">nothing scheduled ·</p>
              ) : (
                <div className="divide-y divide-white/[0.03] max-h-44 overflow-y-auto custom-scrollbar">
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
                          <p className="text-xs text-white/65 font-light truncate">{ev.title}</p>
                          {ev.location && (
                            <p className="text-[9px] text-white/20 font-mono flex items-center gap-1 mt-0.5 truncate">
                              <MapPin size={7} /> {ev.location}
                            </p>
                          )}
                        </div>
                        <span className="shrink-0 font-mono text-[8px] text-white/25 whitespace-nowrap">{timeStr}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Tasks */}
            <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ListTodo size={11} className="text-violet-400/50" />
                  <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.35em]">Tasks</span>
                </div>
                <span className="font-mono text-[8px] text-white/15">{pendingTasks.length} open</span>
              </div>

              <div className="px-4 pt-3 pb-2 flex gap-2">
                <input type="text" value={newTaskText}
                  onChange={e => setNewTaskText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submitTask()}
                  placeholder="Add task..."
                  className="flex-1 bg-black/40 border border-white/[0.05] rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-white/12 outline-none focus:border-violet-500/25 transition-colors" />
                <select value={newTaskPriority}
                  onChange={e => setNewTaskPriority(e.target.value as 'normal' | 'urgent' | 'low')}
                  className="bg-black/40 border border-white/[0.05] rounded-lg px-2 text-[9px] text-white/35 outline-none font-mono">
                  <option value="low">low</option>
                  <option value="normal">—</option>
                  <option value="urgent">!</option>
                </select>
                <button onClick={submitTask} disabled={!newTaskText.trim() || addingTask}
                  className={`p-1.5 border rounded-lg disabled:opacity-25 transition-all active:scale-95 ${
                    taskFeedback === 'ok'  ? 'bg-emerald-500/15 border-emerald-500/25 text-emerald-400' :
                    taskFeedback === 'err' ? 'bg-red-500/15 border-red-500/25 text-red-400' :
                    'bg-violet-500/8 border-violet-500/15 text-violet-300/60 hover:bg-violet-500/15'
                  }`}>
                  {taskFeedback === 'ok' ? '✓' : taskFeedback === 'err' ? '✗' : <Plus size={11} />}
                </button>
              </div>

              {pendingTasks.length === 0 ? (
                <p className="px-4 py-3 font-mono text-[9px] text-white/15">all clear ✓</p>
              ) : (
                <div className="divide-y divide-white/[0.03] max-h-40 overflow-y-auto custom-scrollbar">
                  {pendingTasks.slice(0, 6).map((t: any) => (
                    <div key={t.id} className="px-4 py-2 flex items-center gap-2.5 group">
                      <button onClick={() => completeTask(t.id)}
                        className="shrink-0 w-3.5 h-3.5 rounded border border-white/10 group-hover:border-violet-400/35 flex items-center justify-center hover:bg-violet-500/10 transition-all">
                        <CheckCircle size={8} className="text-transparent group-hover:text-violet-400/50 transition-colors" />
                      </button>
                      <p className={`text-xs font-light truncate flex-1 ${
                        t.priority === 'urgent' ? 'text-red-300/70' : 'text-white/50'
                      }`}>{t.text}</p>
                      {t.priority === 'urgent' && (
                        <span className="shrink-0 font-mono text-[7px] px-1 py-0.5 rounded bg-red-500/10 text-red-400/70">urgent</span>
                      )}
                      <button onClick={async () => { await fetch(`http://localhost:4009/tasks/${t.id}`, { method: 'DELETE' }); onTaskCompleted?.(); }}
                        className="shrink-0 opacity-0 group-hover:opacity-100 text-white/15 hover:text-red-400 transition-all">
                        <Trash2 size={9} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Reminders */}
            <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bell size={11} className="text-amber-400/50" />
                  <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.35em]">Reminders</span>
                </div>
                <span className="font-mono text-[8px] text-white/15">{dash?.reminders_count ?? 0} set</span>
              </div>

              <div className="px-4 pt-3 pb-2 flex gap-2">
                <input type="text" value={reminderMsg}
                  onChange={e => setReminderMsg(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submitReminder()}
                  placeholder="Remind me to..."
                  className="flex-1 bg-black/40 border border-white/[0.05] rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-white/12 outline-none focus:border-amber-500/25 transition-colors" />
                <input type="number" value={reminderMins} onChange={e => setReminderMins(e.target.value)} min="1"
                  className="w-12 bg-black/40 border border-white/[0.05] rounded-lg px-2 py-1.5 text-xs text-white/50 outline-none font-mono text-center" />
                <button onClick={submitReminder} disabled={!reminderMsg.trim() || addingReminder}
                  className={`p-1.5 border rounded-lg disabled:opacity-25 transition-all active:scale-95 ${
                    reminderFeedback === 'ok'  ? 'bg-emerald-500/15 border-emerald-500/25 text-emerald-400' :
                    reminderFeedback === 'err' ? 'bg-red-500/15 border-red-500/25 text-red-400' :
                    'bg-amber-500/8 border-amber-500/15 text-amber-300/60 hover:bg-amber-500/15'
                  }`}>
                  {reminderFeedback === 'ok' ? '✓' : reminderFeedback === 'err' ? '✗' : <Plus size={11} />}
                </button>
              </div>

              {dash?.reminders && dash.reminders.length > 0 ? (
                <div className="divide-y divide-white/[0.03]">
                  {dash.reminders.slice(0, 3).map((r: any) => {
                    const mins = Math.ceil(r.seconds_remaining / 60);
                    return (
                      <div key={r.id} className="px-4 py-2 flex items-center gap-2.5 group">
                        <Clock size={9} className="text-amber-400/35 shrink-0" />
                        <p className="text-xs text-white/50 font-light truncate flex-1">{r.message}</p>
                        <span className="shrink-0 font-mono text-[8px] text-amber-400/50 bg-amber-500/8 px-1.5 py-0.5 rounded-full whitespace-nowrap">
                          {mins < 1 ? '<1m' : `${mins}m`}
                        </span>
                        <button onClick={async () => { await fetch(`http://localhost:4009/api/reminders/${r.id}`, { method: 'DELETE' }); fetchDash(); }}
                          className="shrink-0 opacity-0 group-hover:opacity-100 text-white/15 hover:text-red-400 transition-all text-xs">×</button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="px-4 py-3 font-mono text-[9px] text-white/15">none set</p>
              )}
            </div>

            {/* Recent Meetings */}
            <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.05] flex items-center gap-2">
                <Video size={11} className="text-white/20" />
                <span className="font-mono text-[9px] text-white/25 uppercase tracking-[0.35em]">Meetings</span>
              </div>
              <div className="divide-y divide-white/[0.03]">
                {meetings.length === 0 ? (
                  <p className="px-4 py-3 font-mono text-[9px] text-white/15">no recordings yet</p>
                ) : (
                  meetings.slice(0, 3).map((m: any) => (
                    <div key={m.name} className="px-4 py-2.5 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs text-white/55 font-mono truncate">{m.name}</p>
                        {m.summary_preview && (
                          <p className="text-[9px] text-white/20 mt-0.5 line-clamp-1 font-light">{m.summary_preview}</p>
                        )}
                      </div>
                      <span className={`shrink-0 text-[7px] font-mono px-1.5 py-0.5 rounded-full ${
                        m.has_summary ? 'bg-emerald-500/10 text-emerald-400/70' : 'bg-white/5 text-white/15'
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

export const SummariesSidebarHidden = ({ onNavigate }: { onNavigate: (id: ScreenId) => void }) => (
  <div className="h-full flex flex-col p-8 md:p-12 lg:p-20 animate-in fade-in zoom-in-95 duration-1000 ease-[cubic-bezier(0.16,1,0.3,1)]">
      <div className="mb-16">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-1.5 h-4 bg-primary shadow-[0_0_10px_rgba(79,70,229,0.5)]" />
          <span className="font-mono text-primary lowercase text-xs tracking-[0.4em] font-bold italic opacity-60">session_active // synthesis_buffer</span>
        </div>
        <h1 className="font-bold lowercase italic tracking-wide text-4xl text-white hover:text-primary transition-all duration-700 cursor-default">
          Primary_Interface_X
        </h1>
      </div>

      <div className="glass-panel relative overflow-hidden shadow-[0_64px_256px_rgba(0,0,0,0.8)] border-white/5 group rounded-3xl bg-zinc-900/40 backdrop-blur-3xl">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/[0.03] to-transparent pointer-events-none" />
        <div className="border-b border-white/5 px-12 py-8 flex justify-between items-center bg-white/[0.01]">
          <div className="flex items-center gap-12">
            <div className="flex items-center gap-4">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.5)] animate-pulse" />
              <span className="font-mono text-[10px] text-white/80 uppercase tracking-[0.3em] font-bold">STATE: STEADY</span>
            </div>
            <div className="h-6 w-px bg-white/10" />
            <div className="flex items-center gap-4">
              <span className="font-mono text-[10px] text-white/20 uppercase tracking-[0.3em]">VERSION: 0.0.4-ALPHA</span>
            </div>
          </div>
        </div>

        <div className="p-12 md:p-20 lg:p-24 max-w-5xl">
          <div className="mb-20">
            <span className="font-mono text-primary lowercase mb-8 block uppercase text-[11px] tracking-[0.5em] font-bold opacity-40">System_Summary</span>
            <p className="text-xl font-bold text-white leading-[1.05] tracking-tight lowercase italic font-light opacity-90 text-left">
              the sovereign neural architecture has achieved full synchronization. all local sub-systems are operating within nominal parameters. privacy filters are active and enforcing local data boundaries.
            </p>
          </div>
          <div className="flex items-center gap-8 pt-20 border-t border-white/5">
            <button onClick={() => onNavigate('summaries_expanded')} className="bg-white text-black font-mono px-12 py-5 uppercase text-[12px] font-bold tracking-[0.2em] hover:bg-primary hover:text-white shadow-2xl flex items-center gap-4 rounded-xl transition-all duration-300 ease-out active:scale-95">
              Apply_Changes
              <CheckCircle size={20} />
            </button>
            <button onClick={() => onNavigate('logs')} className="border border-white/10 text-white/40 font-mono px-12 py-5 uppercase text-[11px] tracking-[0.3em] font-bold hover:bg-white/5 rounded-xl transition-all duration-300 ease-out active:scale-95">
              VIEW_RAW_HEX
            </button>
          </div>
        </div>
      </div>
    </div>
);

export const SummariesEmptyState = ({ onNavigate }: { onNavigate: (id: ScreenId) => void }) => (
  <div className="p-12 lg:p-20 h-full flex flex-col justify-center items-center text-center animate-in fade-in slide-in-from-bottom-8 duration-1000">
      <div className="relative mb-12">
        <div className="w-32 h-32 rounded-full border border-white/5 flex items-center justify-center relative">
          <div className="absolute inset-0 border border-primary/20 rounded-full animate-ping [animation-duration:3s]" />
          <Database size={48} className="text-primary/40" />
        </div>
        <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 bg-black border border-white/10 px-3 py-1 rounded font-mono text-[8px] text-primary uppercase">Idle_State</div>
      </div>
      
      <h1 className="font-bold lowercase italic tracking-wide text-4xl text-white mb-4">No Active Sessions Found</h1>
      <p className="text-on-surface-variant max-w-sm leading-relaxed mb-12 opacity-60 lowercase">The neural nexus is currently in stasis. Initialize a new analysis task to begin data orchestration.</p>
      
      <div className="flex flex-col gap-4">
        <button 
          onClick={() => onNavigate('summaries_expanded')}
          className="bg-primary text-black font-mono px-12 py-4 uppercase text-[11px] font-bold tracking-[0.2em] hover:brightness-110 transition-all shadow-[0_0_30px_rgba(79,70,229,0.2)]"
        >
          Initialize_Analysis
        </button>
        <a 
          href="#" 
          onClick={(e) => { e.preventDefault(); onNavigate('notes_icon_sidebar'); }}
          className="text-[10px] text-white/30 hover:text-primary transition-colors font-mono uppercase tracking-widest"
        >
          historical_archive
        </a>
      </div>
    </div>
);

export const SummariesIconSidebar = ({ onNavigate, notes = [] }: { onNavigate: (id: ScreenId) => void, notes?: any[] }) => (
  <div className="flex flex-col lg:flex-row h-full">
      <aside className="w-full lg:w-80 border-r border-white/5 p-8 space-y-10 bg-surface-container-lowest overflow-y-auto custom-scrollbar">
        <div>
          <h4 className="font-mono text-white/30 uppercase mb-5 text-[9px] tracking-[0.3em]">Core_Insights</h4>
          <ul className="space-y-6">
            {notes.length === 0 ? (
              <li className="text-[11px] text-white/20 italic font-mono uppercase tracking-widest">No nodes synced...</li>
            ) : (
              notes.slice(0, 5).map((note, idx) => (
                <li key={idx} className="flex gap-4 group">
                  <span className="font-mono text-primary text-[10px] mt-1 tabular-nums">0{idx+1}</span>
                  <p className="text-[13px] text-on-surface-variant leading-relaxed opacity-80 group-hover:opacity-100 transition-opacity line-clamp-2 italic lowercase">
                    {typeof note === 'string' ? note : note.text}
                  </p>
                </li>
              ))
            )}
          </ul>
        </div>
        
        <div className="pt-10 border-t border-white/5">
           <h4 className="font-mono text-white/30 uppercase mb-5 text-[9px] tracking-[0.3em]">System_State</h4>
           <div className="space-y-4">
             <div className="flex justify-between items-center bg-black/40 p-3 border border-white/5 group hover:border-primary/30 transition-all">
                <span className="font-mono text-[10px] text-white/40">MEMORY</span>
                <span className="font-mono text-[10px] text-emerald-400 tracking-tighter uppercase">{notes.length > 0 ? 'OPTIMAL' : 'IDLE'}</span>
             </div>
           </div>
        </div>
      </aside>

      <div className="flex-1 overflow-y-auto custom-scrollbar max-w-5xl mx-auto p-10 lg:p-20 space-y-14 pb-40 animate-in fade-in slide-in-from-right-8 duration-700">
        <header className="space-y-6 text-left">
          <div className="w-fit">
            <span className="bg-primary/10 text-primary px-3 py-1 border border-primary/20 font-mono text-[10px] uppercase tracking-[0.2em] shadow-[0_0_15px_rgba(79,70,229,0.1)]">Neural Nexus Core</span>
          </div>
          <h1 className="font-bold lowercase italic tracking-wide text-3xl lg:text-4xl leading-[0.95] text-white max-w-4xl">
            {notes[0] ? (typeof notes[0] === 'string' ? notes[0] : notes[0].text) : 'Technical architecture of the decentralized neural nexus'}
          </h1>
          <div className="flex items-center gap-4 pt-4">
             <div className="flex -space-x-2">
                {[1,2,3].map(i => <div key={i} className="w-8 h-8 rounded-full border-2 border-zinc-950 bg-zinc-900 flex items-center justify-center"><Terminal size={12} className="text-primary/20" /></div>)}
             </div>
             <span className="font-mono text-[10px] text-white/20 uppercase tracking-widest italic lowercase">Authored by Primnox_Agent</span>
          </div>
        </header>

        <div className="glass-panel p-10 border-l-2 border-l-primary relative overflow-hidden group">
           <div className="absolute top-0 right-0 p-4 opacity-[0.03] pointer-events-none group-hover:opacity-[0.05] transition-opacity">
              <Database size={100} />
           </div>
           <p className="text-base text-on-surface leading-loose italic opacity-90 relative z-10 font-medium text-left lowercase">
            "{notes[1] ? (typeof notes[1] === 'string' ? notes[1] : notes[1].text) : 'the proposed framework leverages a sharded graph topology to ensure linear scalability across heterogenous nodes.'}"
          </p>
        </div>
        
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-8">
           <div className="p-6 bg-surface-container-lowest border border-white/5">
              <span className="block font-mono text-[9px] text-white/30 uppercase mb-4 tracking-widest text-center">Node_Count</span>
              <p className="text-2xl font-bold text-white tracking-tighter text-center italic">{notes.length}</p>
           </div>
           <div className="p-6 bg-surface-container-lowest border border-white/5">
              <span className="block font-mono text-[9px] text-white/30 uppercase mb-4 tracking-widest text-center">Sync_Frequency</span>
              <p className="text-2xl font-bold text-white tracking-tighter text-center italic">0.05ms</p>
           </div>
        </div>

        <div className="fixed bottom-12 left-1/2 -translate-x-1/2 z-50">
          <div className="flex gap-2 p-2 bg-black/70 backdrop-blur-3xl rounded-full border border-white/10 shadow-[0_20px_50px_rgba(0,0,0,0.5)]">
            <button className="p-4 rounded-full text-white/40 hover:text-white transition-all duration-300 ease-out active:scale-95" onClick={() => onNavigate('chat_expanded_sidebar')}><MessageSquare size={20} /></button>
            <button className="p-4 rounded-full border border-primary text-primary bg-primary/10 shadow-[0_0_20px_rgba(79,70,229,0.2)] transition-all duration-300 ease-out active:scale-95" onClick={() => onNavigate('notes_icon_sidebar')}><Database size={20} /></button>
            <button className="p-4 rounded-full text-white/40 hover:text-white transition-all duration-300 ease-out active:scale-95" onClick={() => onNavigate('summaries_expanded')}><FileText size={20} /></button>
          </div>
        </div>
      </div>
    </div>
);
