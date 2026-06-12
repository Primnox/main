import { useState, useEffect, useCallback, memo } from 'react';
import { Database, MessageSquare, FileText, CheckCircle, Terminal, Brain, FileEdit, Video, Monitor, Zap, RefreshCw, AlertTriangle, Bell, Shield, ListTodo, Plus, Clock, Trash2, Activity, Radio } from 'lucide-react';

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
      const res = await fetch('http://localhost:8000/api/dashboard', {
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
      await fetch('http://localhost:8000/api/daily_brief', { method: 'POST' });
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
      await fetch(`http://localhost:8000/tasks/${id}/complete`, { method: 'POST' });
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
      const res = await fetch('http://localhost:8000/api/reminders', {
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
      const res = await fetch('http://localhost:8000/tasks', {
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
  const _urgent = pendingTasks.find((t: any) => t.priority === 'urgent');
  const _rem    = dash?.reminders?.[0];
  const focus =
    _urgent ? `Urgent — ${clip(_urgent.text)}` :
    _rem    ? `Soon — ${clip(_rem.message)}` :
    pendingTasks[0] ? `Up next — ${clip(pendingTasks[0].text)}` : '';

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-7 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]">

        {/* ── API Key Banner ── */}
        {dash && !dash.has_api_key && (
          <div className="flex items-center justify-between gap-4 px-5 py-3 bg-amber-500/10 border border-amber-500/20 rounded-xl">
            <div className="flex items-center gap-3">
              <AlertTriangle size={13} className="text-amber-400 shrink-0" />
              <p className="text-xs text-amber-300/80 font-light">No API key — Primnox can't think or transcribe.</p>
            </div>
            <button onClick={() => onNavigate('island_settings')}
              className="shrink-0 px-3 py-1.5 bg-amber-500/20 border border-amber-500/30 text-amber-300 rounded-lg font-mono text-[10px] uppercase tracking-widest hover:bg-amber-500/30 transition-all">
              Add Key →
            </button>
          </div>
        )}

        {/* ── Hero ── */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-2xl font-bold text-white tracking-tight leading-tight">
              {greeting}{dash?.user_name ? <span className="text-white/50">, {dash.user_name}</span> : ''}
            </h2>
            <p className="text-sm text-white/40 mt-1 font-light truncate">
              {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
              {focus && <span className="text-white/25"> · </span>}
              {focus && <span className="text-primary/80">{focus}</span>}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button onClick={fetchDash}
              className="p-2 rounded-lg text-white/30 hover:text-white/70 hover:bg-white/5 transition-all" title="Refresh">
              <RefreshCw size={13} />
            </button>
            <button onClick={triggerBrief} disabled={briefStatus === 'generating'}
              className="flex items-center gap-2 px-4 py-2 bg-primary/10 border border-primary/20 text-primary rounded-xl font-mono text-[10px] uppercase tracking-widest hover:bg-primary hover:text-black transition-all disabled:opacity-40">
              <Zap size={11} />
              {briefStatus === 'generating' ? 'Generating...' : briefStatus === 'done' ? 'Requested ✓' : 'Daily Brief'}
            </button>
          </div>
        </div>

        {/* ── Stat Row ── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Tasks',    value: pendingTasks.length,         icon: ListTodo, sub: `${doneTasks.length} done`, tint: 'text-violet-300 bg-violet-500/10 border-violet-500/20' },
            { label: 'Notes',    value: dash?.notes_count ?? '—',    icon: FileEdit, sub: 'in workspace',            tint: 'text-sky-300 bg-sky-500/10 border-sky-500/20' },
            { label: 'Memories', value: dash?.memories_count ?? '—', icon: Brain,    sub: 'stored',                  tint: 'text-primary bg-primary/10 border-primary/20' },
            { label: 'Skills',   value: dash?.skills_count ?? '—',   icon: Zap,      sub: 'loaded',                  tint: 'text-amber-300 bg-amber-500/10 border-amber-500/20' },
          ].map(({ label, value, icon: Icon, sub, tint }) => (
            <div key={label} className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl p-4 flex flex-col gap-3 hover:border-white/15 hover:-translate-y-0.5 transition-all duration-200">
              <div className="flex items-center justify-between">
                <div className={`w-7 h-7 rounded-lg border flex items-center justify-center ${tint}`}>
                  <Icon size={13} />
                </div>
                <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.3em]">{label}</span>
              </div>
              <div>
                <p className="text-2xl font-bold text-white tracking-tight leading-none">{value}</p>
                <p className="text-[10px] text-white/35 font-mono mt-1.5">{sub}</p>
              </div>
            </div>
          ))}
        </div>

        {/* ── Main grid: feed left + panels right ── */}
        <div className="grid grid-cols-12 gap-5">

          {/* ── Activity feed (left 7) ── */}
          <div className="col-span-12 lg:col-span-7 flex flex-col gap-5">

            {/* Feed */}
            <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl overflow-hidden flex flex-col">
              <div className="px-5 py-3.5 border-b border-white/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Activity size={12} className="text-primary/60" />
                  <span className="font-mono text-[10px] text-white/40 uppercase tracking-[0.3em]">Activity_Feed</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                  <span className="font-mono text-[9px] text-white/20">{feed.length} events</span>
                </div>
              </div>
              <div className="px-5 py-3 max-h-64 overflow-y-auto custom-scrollbar">
                {feed.length === 0 ? (
                  <div className="py-10 text-center">
                    <Radio size={18} className="text-white/10 mx-auto mb-3" />
                    <p className="font-mono text-[10px] text-white/15 uppercase tracking-widest">primnox is listening</p>
                  </div>
                ) : (
                  [...feed].reverse().map((e, i) => <FeedRow key={i} event={e} />)
                )}
              </div>
            </div>

            {/* Current focus + quick-nav in a row */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl p-5">
                <div className="flex items-center gap-2 mb-3">
                  <Monitor size={11} className="text-white/25" />
                  <span className="font-mono text-[9px] text-white/25 uppercase tracking-[0.3em]">Current_Focus</span>
                </div>
                {dash ? (
                  <>
                    <p className="text-sm font-semibold text-white/80 truncate">{dash.active_process || 'Unknown'}</p>
                    <p className="text-[10px] text-white/30 font-mono truncate mt-1">{dash.active_window || '—'}</p>
                  </>
                ) : (
                  <p className="text-[10px] text-white/20 font-mono">connecting...</p>
                )}
              </div>
              <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl p-5">
                <div className="flex items-center gap-2 mb-3">
                  <Shield size={11} className={dash?.last_backup ? 'text-emerald-400/50' : 'text-white/25'} />
                  <span className="font-mono text-[9px] text-white/25 uppercase tracking-[0.3em]">Last_Backup</span>
                </div>
                {dash?.last_backup ? (
                  <>
                    <p className="text-sm font-semibold text-white/80">{dash.last_backup.size_kb} KB</p>
                    <p className="text-[10px] text-white/30 font-mono truncate mt-1">
                      {dash.last_backup.filename.replace('backup_', '').replace('.zip', '')}
                    </p>
                  </>
                ) : (
                  <p className="text-[10px] text-white/20 font-mono">no backup yet</p>
                )}
              </div>
            </div>

            {/* Quick nav */}
            <div className="grid grid-cols-4 gap-3">
              {([
                { label: 'Chat',     icon: MessageSquare, screen: 'chat_expanded_sidebar' },
                { label: 'Notes',    icon: FileText,      screen: 'notes_icon_sidebar'    },
                { label: 'Archive',  icon: Database,      screen: 'archive'               },
                { label: 'Meetings', icon: Video,         screen: 'logs'                  },
              ] as { label: string; icon: any; screen: ScreenId }[]).map(({ label, icon: Icon, screen }) => (
                <button key={screen} onClick={() => onNavigate(screen)}
                  className="flex flex-col items-center gap-2 py-3 bg-zinc-900/30 border border-white/[0.05] rounded-xl hover:border-primary/25 hover:bg-primary/5 transition-all group">
                  <Icon size={14} className="text-white/25 group-hover:text-primary transition-colors" />
                  <span className="font-mono text-[9px] text-white/30 group-hover:text-white/70 uppercase tracking-widest transition-colors">{label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* ── Right column (5) ── */}
          <div className="col-span-12 lg:col-span-5 flex flex-col gap-4">

            {/* Tasks */}
            <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl overflow-hidden">
              <div className="px-5 py-3.5 border-b border-white/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ListTodo size={11} className="text-violet-400/60" />
                  <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.3em]">Tasks</span>
                </div>
                <span className="font-mono text-[9px] text-white/20">{pendingTasks.length} open</span>
              </div>

              {/* Add task inline */}
              <div className="px-5 pt-3 pb-2 flex gap-2">
                <input type="text" value={newTaskText}
                  onChange={e => setNewTaskText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submitTask()}
                  placeholder="Add task..."
                  className="flex-1 bg-black/40 border border-white/[0.06] rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-white/15 outline-none focus:border-violet-500/30 transition-colors" />
                <select value={newTaskPriority}
                  onChange={e => setNewTaskPriority(e.target.value as 'normal' | 'urgent' | 'low')}
                  className="bg-black/40 border border-white/[0.06] rounded-lg px-2 text-[9px] text-white/40 outline-none font-mono">
                  <option value="low">low</option>
                  <option value="normal">—</option>
                  <option value="urgent">urgent</option>
                </select>
                <button onClick={submitTask} disabled={!newTaskText.trim() || addingTask}
                  className={`p-1.5 border rounded-lg disabled:opacity-30 transition-all ${
                    taskFeedback === 'ok'  ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400' :
                    taskFeedback === 'err' ? 'bg-red-500/15 border-red-500/30 text-red-400' :
                    'bg-violet-500/10 border-violet-500/20 text-violet-300/70 hover:bg-violet-500/20'
                  }`}>
                  {taskFeedback === 'ok' ? '✓' : taskFeedback === 'err' ? '✗' : <Plus size={12} />}
                </button>
              </div>

              {pendingTasks.length === 0 ? (
                <p className="px-5 py-3 font-mono text-[10px] text-white/20">all clear</p>
              ) : (
                <div className="divide-y divide-white/[0.03] max-h-44 overflow-y-auto custom-scrollbar">
                  {pendingTasks.slice(0, 6).map((t: any) => (
                    <div key={t.id} className="px-5 py-2.5 flex items-center gap-3 group">
                      <button onClick={() => completeTask(t.id)}
                        className="shrink-0 w-4 h-4 rounded border border-white/10 group-hover:border-violet-400/40 flex items-center justify-center hover:bg-violet-500/10 transition-all">
                        <CheckCircle size={9} className="text-white/0 group-hover:text-violet-400/60 transition-colors" />
                      </button>
                      <p className="text-xs text-white/55 font-light truncate flex-1">{t.text}</p>
                      {t.priority === 'urgent' && (
                        <span className="shrink-0 font-mono text-[8px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400">!</span>
                      )}
                      <button onClick={async () => { await fetch(`http://localhost:8000/tasks/${t.id}`, { method: 'DELETE' }); onTaskCompleted?.(); }}
                        className="shrink-0 opacity-0 group-hover:opacity-100 text-white/20 hover:text-red-400 transition-all">
                        <Trash2 size={10} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Reminders */}
            <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl overflow-hidden">
              <div className="px-5 py-3.5 border-b border-white/[0.05] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bell size={11} className="text-amber-400/60" />
                  <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.3em]">Reminders</span>
                </div>
                <span className="font-mono text-[9px] text-white/20">{dash?.reminders_count ?? 0} pending</span>
              </div>

              {/* Add reminder inline */}
              <div className="px-5 pt-3 pb-2 flex gap-2">
                <input type="text" value={reminderMsg}
                  onChange={e => setReminderMsg(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submitReminder()}
                  placeholder="Remind me to..."
                  className="flex-1 bg-black/40 border border-white/[0.06] rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-white/15 outline-none focus:border-amber-500/30 transition-colors" />
                <input type="number" value={reminderMins} onChange={e => setReminderMins(e.target.value)} min="1"
                  className="w-14 bg-black/40 border border-white/[0.06] rounded-lg px-2 py-1.5 text-xs text-white/60 outline-none font-mono text-center" />
                <button onClick={submitReminder} disabled={!reminderMsg.trim() || addingReminder}
                  className={`p-1.5 border rounded-lg disabled:opacity-30 transition-all ${
                    reminderFeedback === 'ok'  ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400' :
                    reminderFeedback === 'err' ? 'bg-red-500/15 border-red-500/30 text-red-400' :
                    'bg-amber-500/10 border-amber-500/20 text-amber-300/70 hover:bg-amber-500/20'
                  }`}>
                  {reminderFeedback === 'ok' ? '✓' : reminderFeedback === 'err' ? '✗' : <Plus size={12} />}
                </button>
              </div>

              {dash?.reminders && dash.reminders.length > 0 ? (
                <div className="divide-y divide-white/[0.03]">
                  {dash.reminders.slice(0, 4).map((r: any) => {
                    const mins = Math.ceil(r.seconds_remaining / 60);
                    return (
                      <div key={r.id} className="px-5 py-2.5 flex items-center gap-3 group">
                        <Clock size={10} className="text-amber-400/40 shrink-0" />
                        <p className="text-xs text-white/55 font-light truncate flex-1">{r.message}</p>
                        <span className="shrink-0 font-mono text-[9px] text-amber-400/60 bg-amber-500/10 px-2 py-0.5 rounded-full">
                          {mins < 1 ? '<1m' : `${mins}m`}
                        </span>
                        <button onClick={async () => { await fetch(`http://localhost:8000/api/reminders/${r.id}`, { method: 'DELETE' }); fetchDash(); }}
                          className="shrink-0 opacity-0 group-hover:opacity-100 text-white/20 hover:text-red-400 transition-all">×</button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="px-5 py-3 font-mono text-[10px] text-white/20">none set</p>
              )}
            </div>

            {/* Recent Meetings */}
            <div className="bg-zinc-900/40 border border-white/[0.06] rounded-2xl overflow-hidden">
              <div className="px-5 py-3.5 border-b border-white/[0.05] flex items-center gap-2">
                <Video size={11} className="text-white/25" />
                <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.3em]">Recent_Meetings</span>
              </div>
              <div className="divide-y divide-white/[0.03]">
                {meetings.length === 0 ? (
                  <p className="px-5 py-4 font-mono text-[10px] text-white/20">no meetings recorded</p>
                ) : (
                  meetings.slice(0, 3).map((m: any) => (
                    <div key={m.name} className="px-5 py-3 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs text-white/60 font-mono truncate">{m.name}</p>
                        {m.summary_preview && (
                          <p className="text-[10px] text-white/25 mt-0.5 line-clamp-1 font-light">{m.summary_preview}</p>
                        )}
                      </div>
                      <span className={`shrink-0 text-[8px] font-mono px-2 py-0.5 rounded-full ${
                        m.has_summary ? 'bg-emerald-500/10 text-emerald-400' : 'bg-white/5 text-white/20'
                      }`}>{m.has_summary ? 'summary' : 'raw'}</span>
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
