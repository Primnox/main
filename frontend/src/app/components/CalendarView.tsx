import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  ChevronLeft, ChevronRight, Calendar, Clock, MapPin,
  Plus, X, Edit2, Trash2, AlignLeft, Zap, Check,
} from 'lucide-react';

// ── Types ────────────────────────────────────────────────────────────────────

interface CalEvent {
  id: string;
  title: string;
  start_dt: string;
  end_dt: string;
  all_day: boolean;
  color: string;
  location: string;
  description: string;
  recurrence: string;
  calendar: string;
}

interface Task {
  id: number;
  text: string;
  priority: string;
  due_date: string | null;
  completed: boolean;
}

interface EventWithLayout extends CalEvent {
  col: number;
  cols: number;
}

// ── Constants ────────────────────────────────────────────────────────────────

const PX_PER_MIN  = 1.2;
const HOURS       = Array.from({ length: 24 }, (_, i) => i);
const DAY_NAMES   = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = ['January','February','March','April','May','June',
                     'July','August','September','October','November','December'];
const EVENT_COLORS = ['#6366f1','#22c55e','#f59e0b','#ef4444','#06b6d4','#ec4899','#8b5cf6','#f97316'];
const CAL_NAMES   = ['Personal', 'Work', 'College', 'Health'];
const API         = 'http://localhost:8000';

// ── Helpers ──────────────────────────────────────────────────────────────────

function getWeekStart(d: Date): Date {
  const dow  = d.getDay();
  const diff = dow === 0 ? -6 : 1 - dow;
  const s    = new Date(d);
  s.setDate(d.getDate() + diff);
  s.setHours(0, 0, 0, 0);
  return s;
}

function getWeekDays(ws: Date): Date[] {
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(ws);
    d.setDate(ws.getDate() + i);
    return d;
  });
}

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() &&
         a.getMonth()    === b.getMonth()    &&
         a.getDate()     === b.getDate();
}

function fmtTime(d: Date): string {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function durationLabel(start: Date, end: Date): string {
  const mins = Math.round((end.getTime() - start.getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60), m = mins % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

function toLocalISO(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`;
}

function computeLayout(evs: CalEvent[]): EventWithLayout[] {
  const sorted: EventWithLayout[] = [...evs]
    .sort((a, b) => new Date(a.start_dt).getTime() - new Date(b.start_dt).getTime())
    .map(ev => ({ ...ev, col: 0, cols: 1 }));

  for (let i = 0; i < sorted.length; i++) {
    const aS = new Date(sorted[i].start_dt).getTime();
    const aE = new Date(sorted[i].end_dt).getTime();
    const used = new Set<number>();
    for (let j = 0; j < i; j++) {
      const bS = new Date(sorted[j].start_dt).getTime();
      const bE = new Date(sorted[j].end_dt).getTime();
      if (bS < aE && bE > aS) used.add(sorted[j].col);
    }
    let col = 0;
    while (used.has(col)) col++;
    sorted[i].col = col;
    const overlapping = sorted.filter(b => {
      const bS = new Date(b.start_dt).getTime();
      const bE = new Date(b.end_dt).getTime();
      return bS < aE && bE > aS;
    });
    const maxCols = Math.max(...overlapping.map(b => b.col)) + 1;
    for (const b of overlapping) b.cols = Math.max(b.cols, maxCols);
  }
  return sorted;
}

// ── Mini calendar ────────────────────────────────────────────────────────────

function MiniMonth({
  year, month, selected, today, dotDays, onSelect, onPrev, onNext,
}: {
  year: number; month: number; selected: Date; today: Date;
  dotDays: Set<string>;
  onSelect: (d: Date) => void; onPrev: () => void; onNext: () => void;
}) {
  const startOffset = (() => { const f = new Date(year, month, 1).getDay(); return f === 0 ? 6 : f - 1; })();
  const daysInMo    = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(startOffset).fill(null),
    ...Array.from({ length: daysInMo }, (_, i) => i + 1),
  ];

  return (
    <div className="select-none">
      <div className="flex items-center justify-between mb-3">
        <button onClick={onPrev} className="p-1 rounded hover:bg-white/5 text-white/30 hover:text-white/70 transition-colors">
          <ChevronLeft size={12} />
        </button>
        <span className="font-mono text-[10px] font-bold text-white/50 uppercase tracking-widest">
          {MONTH_NAMES[month].slice(0, 3)} {year}
        </span>
        <button onClick={onNext} className="p-1 rounded hover:bg-white/5 text-white/30 hover:text-white/70 transition-colors">
          <ChevronRight size={12} />
        </button>
      </div>
      <div className="grid grid-cols-7 mb-1">
        {['M','T','W','T','F','S','S'].map((d, i) => (
          <div key={i} className="text-center font-mono text-[9px] text-white/20 pb-1">{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-px">
        {cells.map((day, i) => {
          if (!day) return <div key={`e-${i}`} />;
          const date    = new Date(year, month, day);
          const isToday = isSameDay(date, today);
          const isSel   = isSameDay(date, selected);
          const k       = `${year}-${String(month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
          return (
            <button
              key={day}
              onClick={() => onSelect(date)}
              className={`relative flex flex-col items-center justify-center h-7 rounded text-[10px] font-mono font-bold transition-all
                ${isSel   ? 'bg-primary text-black'
                : isToday ? 'text-primary ring-1 ring-primary/30 bg-primary/5'
                :           'text-white/40 hover:text-white hover:bg-white/5'}`}
            >
              {day}
              {dotDays.has(k) && !isSel && (
                <span className="absolute bottom-0.5 w-1 h-1 rounded-full bg-primary/60" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Event form ───────────────────────────────────────────────────────────────

function EventForm({
  draft, onSave, onCancel, isCreating,
}: {
  draft: Partial<CalEvent>;
  onSave: (d: Partial<CalEvent>) => void;
  onCancel: () => void;
  isCreating: boolean;
}) {
  const [form, setForm] = useState({
    title:       draft.title       || '',
    start_dt:    draft.start_dt    || toLocalISO(new Date()),
    end_dt:      draft.end_dt      || toLocalISO(new Date(Date.now() + 3_600_000)),
    all_day:     draft.all_day     || false,
    color:       draft.color       || '#6366f1',
    location:    draft.location    || '',
    description: draft.description || '',
    calendar:    draft.calendar    || 'Personal',
  });

  const set = <K extends keyof typeof form>(k: K, v: typeof form[K]) =>
    setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="space-y-3">
      <input
        autoFocus
        type="text"
        placeholder="Event title"
        value={form.title}
        onChange={e => set('title', e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && form.title.trim()) onSave(form); }}
        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20 outline-none focus:border-primary/50"
      />

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="font-mono text-[9px] text-white/30 uppercase tracking-widest block mb-1">Start</label>
          <input
            type="datetime-local"
            value={form.start_dt.slice(0, 16)}
            onChange={e => set('start_dt', e.target.value + ':00')}
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-[11px] text-white/70 outline-none focus:border-primary/50"
          />
        </div>
        <div>
          <label className="font-mono text-[9px] text-white/30 uppercase tracking-widest block mb-1">End</label>
          <input
            type="datetime-local"
            value={form.end_dt.slice(0, 16)}
            onChange={e => set('end_dt', e.target.value + ':00')}
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-[11px] text-white/70 outline-none focus:border-primary/50"
          />
        </div>
      </div>

      <div>
        <label className="font-mono text-[9px] text-white/30 uppercase tracking-widest block mb-1.5">Color</label>
        <div className="flex gap-2">
          {EVENT_COLORS.map(c => (
            <button
              key={c}
              onClick={() => set('color', c)}
              className={`w-5 h-5 rounded-full transition-transform ${form.color === c ? 'ring-2 ring-white/60 scale-110' : 'hover:scale-105'}`}
              style={{ background: c }}
            />
          ))}
        </div>
      </div>

      <input
        type="text"
        placeholder="Location (optional)"
        value={form.location}
        onChange={e => set('location', e.target.value)}
        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white/70 placeholder-white/20 outline-none focus:border-primary/50"
      />

      <textarea
        placeholder="Notes (optional)"
        value={form.description}
        onChange={e => set('description', e.target.value)}
        rows={2}
        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white/70 placeholder-white/20 outline-none focus:border-primary/50 resize-none"
      />

      <div>
        <label className="font-mono text-[9px] text-white/30 uppercase tracking-widest block mb-1">Calendar</label>
        <select
          value={form.calendar}
          onChange={e => set('calendar', e.target.value)}
          className="w-full bg-[#111] border border-white/10 rounded px-2 py-1.5 text-[11px] text-white/70 outline-none focus:border-primary/50"
        >
          {CAL_NAMES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => form.title.trim() && new Date(form.start_dt) < new Date(form.end_dt) && onSave(form)}
          disabled={!form.title.trim() || new Date(form.start_dt) >= new Date(form.end_dt)}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 bg-primary text-black text-xs font-bold rounded-lg hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          <Check size={12} />
          {isCreating ? 'Create Event' : 'Save Changes'}
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 bg-white/5 text-white/40 text-xs font-mono rounded-lg hover:bg-white/10 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Event detail panel ───────────────────────────────────────────────────────

function EventDetailPanel({
  event, onEdit, onDelete, onClose,
}: {
  event: CalEvent;
  onEdit: () => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const start = new Date(event.start_dt);
  const end   = new Date(event.end_dt);

  return (
    <motion.div
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16 }}
      className="w-[272px] shrink-0 border-l border-white/[0.06] flex flex-col overflow-y-auto"
    >
      <div className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-3 h-3 rounded-full mt-0.5 shrink-0" style={{ background: event.color }} />
            <h3 className="text-sm font-semibold text-white leading-tight">{event.title}</h3>
          </div>
          <button onClick={onClose} className="p-1 text-white/20 hover:text-white/60 transition-colors shrink-0">
            <X size={13} />
          </button>
        </div>

        <div className="flex items-center gap-2 text-white/50">
          <Clock size={12} className="shrink-0" />
          <div className="font-mono text-[11px]">
            <div>{start.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}</div>
            <div className="text-white/30 mt-0.5">{fmtTime(start)} — {fmtTime(end)} · {durationLabel(start, end)}</div>
          </div>
        </div>

        {event.location && (
          <div className="flex items-center gap-2 text-white/40">
            <MapPin size={12} className="shrink-0" />
            <span className="text-[11px]">{event.location}</span>
          </div>
        )}

        {event.description && (
          <div className="flex items-start gap-2 text-white/40">
            <AlignLeft size={12} className="shrink-0 mt-0.5" />
            <p className="text-[11px] leading-relaxed">{event.description}</p>
          </div>
        )}

        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: `${event.color}80` }} />
          <span className="font-mono text-[9px] text-white/20 uppercase tracking-widest">{event.calendar}</span>
        </div>

        <div className="flex gap-2 pt-2 border-t border-white/[0.06]">
          <button
            onClick={onEdit}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-white/5 hover:bg-white/10 text-white/50 hover:text-white/80 text-[11px] rounded-lg transition-all"
          >
            <Edit2 size={10} /> Edit
          </button>
          <button
            onClick={onDelete}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400/70 hover:text-red-400 text-[11px] rounded-lg transition-all"
          >
            <Trash2 size={10} /> Delete
          </button>
        </div>
      </div>
    </motion.div>
  );
}

// ── Week / Day grid ──────────────────────────────────────────────────────────

function WeekGrid({
  events, tasks, weekDays, now, onEventClick, onSlotClick,
}: {
  events: CalEvent[];
  tasks: Task[];
  weekDays: Date[];
  now: Date;
  onEventClick: (ev: CalEvent) => void;
  onSlotClick: (dt: Date) => void;
}) {
  const gridRef = useRef<HTMLDivElement>(null);
  const today   = useMemo(() => { const d = new Date(); d.setHours(0,0,0,0); return d; }, []);

  useEffect(() => {
    if (gridRef.current) {
      const top = (now.getHours() * 60 + now.getMinutes()) * PX_PER_MIN - 120;
      gridRef.current.scrollTop = Math.max(0, top);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalEvent[]>();
    for (const d of weekDays)
      map.set(dayKey(d), events.filter(ev => !ev.all_day && isSameDay(new Date(ev.start_dt), d)));
    return map;
  }, [events, weekDays]);

  const allDayByDay = useMemo(() => {
    const map = new Map<string, { events: CalEvent[]; tasks: Task[] }>();
    for (const d of weekDays) {
      const k = dayKey(d);
      map.set(k, {
        events: events.filter(ev => ev.all_day && isSameDay(new Date(ev.start_dt), d)),
        tasks:  tasks.filter(t => t.due_date?.startsWith(k) && !t.completed),
      });
    }
    return map;
  }, [events, tasks, weekDays]);

  const nowMins = now.getHours() * 60 + now.getMinutes();

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Day header row */}
      <div className="flex border-b border-white/[0.05] shrink-0">
        <div className="w-12 shrink-0 border-r border-white/[0.04]" />
        {weekDays.map((d, i) => {
          const isToday = isSameDay(d, today);
          const k       = dayKey(d);
          const ad      = allDayByDay.get(k)!;
          const hasAD   = ad.events.length + ad.tasks.length > 0;
          return (
            <div key={i} className={`flex-1 border-l border-white/[0.04] flex flex-col ${isToday ? 'bg-primary/[0.02]' : ''}`}>
              <div className={`flex flex-col items-center py-2 ${isToday ? 'text-primary' : 'text-white/40'}`}>
                <span className="font-mono text-[9px] uppercase tracking-widest">{DAY_NAMES[d.getDay()]}</span>
                <span className={`font-mono text-[14px] font-bold mt-0.5 w-7 h-7 flex items-center justify-center rounded-full
                  ${isToday ? 'bg-primary text-black' : ''}`}>
                  {d.getDate()}
                </span>
              </div>
              {hasAD && (
                <div className="px-1 pb-1 space-y-0.5">
                  {ad.events.map((ev, ei) => (
                    <button
                      key={ei}
                      onClick={() => onEventClick(ev)}
                      className="w-full text-left px-1.5 py-0.5 rounded text-[9px] font-semibold text-black truncate"
                      style={{ background: ev.color }}
                    >
                      {ev.title}
                    </button>
                  ))}
                  {ad.tasks.map((t, ti) => (
                    <div key={ti} className="px-1.5 py-0.5 rounded text-[9px] text-white/50 truncate bg-white/[0.05] border border-white/[0.07]">
                      ✓ {t.text}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Scrollable time grid */}
      <div ref={gridRef} className="flex-1 overflow-y-auto">
        <div className="relative flex" style={{ height: `${24 * 60 * PX_PER_MIN}px` }}>
          {/* Time gutter */}
          <div className="w-12 shrink-0 relative border-r border-white/[0.04]">
            {HOURS.map(h => (
              <div
                key={h}
                className="absolute right-2 font-mono text-[9px] text-white/20 select-none leading-none"
                style={{ top: `${h * 60 * PX_PER_MIN - 5}px` }}
              >
                {h === 0 ? '' : `${String(h).padStart(2,'0')}:00`}
              </div>
            ))}
          </div>

          {/* Day columns */}
          {weekDays.map((d, dayIdx) => {
            const k       = dayKey(d);
            const dayEvs  = computeLayout(eventsByDay.get(k) || []);
            const isToday = isSameDay(d, today);

            return (
              <div
                key={dayIdx}
                className={`flex-1 border-l border-white/[0.04] relative ${isToday ? 'bg-primary/[0.015]' : ''}`}
              >
                {HOURS.map(h => (
                  <div key={h} className="absolute left-0 right-0 border-t border-white/[0.04]"
                    style={{ top: `${h * 60 * PX_PER_MIN}px` }} />
                ))}
                {HOURS.map(h => (
                  <div key={`hh-${h}`} className="absolute left-0 right-0 border-t border-white/[0.02]"
                    style={{ top: `${(h * 60 + 30) * PX_PER_MIN}px` }} />
                ))}

                {/* Click-to-create */}
                <div
                  className="absolute inset-0 cursor-crosshair"
                  onClick={e => {
                    const rect  = (e.currentTarget as HTMLElement).getBoundingClientRect();
                    const mins  = Math.floor((e.clientY - rect.top) / PX_PER_MIN);
                    const slotH = Math.floor(mins / 60);
                    const slotM = Math.floor((mins % 60) / 30) * 30;
                    const dt    = new Date(d);
                    dt.setHours(slotH, slotM, 0, 0);
                    onSlotClick(dt);
                  }}
                />

                {/* Events */}
                {dayEvs.map(ev => {
                  const s      = new Date(ev.start_dt);
                  const e2     = new Date(ev.end_dt);
                  const startM = s.getHours() * 60 + s.getMinutes();
                  const durM   = Math.max((e2.getTime() - s.getTime()) / 60000, 20);
                  const colW   = 100 / ev.cols;
                  const colL   = (ev.col / ev.cols) * 100;

                  return (
                    <button
                      key={ev.id}
                      onClick={e => { e.stopPropagation(); onEventClick(ev); }}
                      className="absolute rounded overflow-hidden text-left hover:brightness-110 transition-all z-10"
                      style={{
                        top:        `${startM * PX_PER_MIN}px`,
                        height:     `${Math.max(durM * PX_PER_MIN, 20)}px`,
                        left:       `${colL + 1}%`,
                        width:      `${colW - 2}%`,
                        background: `${ev.color}22`,
                        borderLeft: `2.5px solid ${ev.color}`,
                      }}
                    >
                      <div className="px-1.5 py-1 h-full overflow-hidden">
                        <p className="font-semibold text-[10px] leading-tight truncate" style={{ color: ev.color }}>
                          {ev.title}
                        </p>
                        {durM * PX_PER_MIN > 32 && (
                          <p className="font-mono text-[9px] text-white/40 truncate">{fmtTime(s)}</p>
                        )}
                      </div>
                    </button>
                  );
                })}

                {/* Current time line */}
                {isToday && (
                  <div
                    className="absolute left-0 right-0 border-t-2 border-red-400/80 pointer-events-none z-20"
                    style={{ top: `${nowMins * PX_PER_MIN}px` }}
                  >
                    <div className="absolute -left-1 -top-1.5 w-3 h-3 rounded-full bg-red-400" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Agenda view ──────────────────────────────────────────────────────────────

function AgendaView({
  events, tasks, startDate, onEventClick,
}: {
  events: CalEvent[];
  tasks: Task[];
  startDate: Date;
  onEventClick: (ev: CalEvent) => void;
}) {
  const today = useMemo(() => { const d = new Date(); d.setHours(0,0,0,0); return d; }, []);
  const days  = useMemo(() => Array.from({ length: 30 }, (_, i) => {
    const d = new Date(startDate); d.setDate(startDate.getDate() + i); return d;
  }), [startDate]);

  const daysWithItems = days.filter(d => {
    const k = dayKey(d);
    return events.some(ev => isSameDay(new Date(ev.start_dt), d)) ||
           tasks.some(t => t.due_date?.startsWith(k) && !t.completed);
  });

  if (daysWithItems.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-white/20">
        <Calendar size={28} />
        <span className="font-mono text-[10px] uppercase tracking-widest">No events in the next 30 days</span>
        <span className="font-mono text-[9px] text-white/10">Click "+ Event" to add one</span>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4">
      {daysWithItems.map(day => {
        const k        = dayKey(day);
        const isToday  = isSameDay(day, today);
        const dayEvs   = events
          .filter(ev => isSameDay(new Date(ev.start_dt), day))
          .sort((a, b) => new Date(a.start_dt).getTime() - new Date(b.start_dt).getTime());
        const dayTasks = tasks.filter(t => t.due_date?.startsWith(k) && !t.completed);

        return (
          <div key={k} className="flex gap-4 mb-4">
            <div className={`w-14 shrink-0 pt-2 text-right ${isToday ? 'text-primary' : 'text-white/30'}`}>
              <div className="font-mono text-[9px] uppercase tracking-wider">{DAY_NAMES[day.getDay()]}</div>
              <div className="font-mono text-[18px] font-bold leading-tight">{day.getDate()}</div>
              <div className="font-mono text-[9px] text-white/20">{MONTH_NAMES[day.getMonth()].slice(0,3)}</div>
            </div>
            <div className="flex-1 space-y-1.5 pb-4 border-b border-white/[0.04]">
              {dayEvs.map(ev => {
                const s  = new Date(ev.start_dt);
                const e2 = new Date(ev.end_dt);
                return (
                  <button
                    key={ev.id}
                    onClick={() => onEventClick(ev)}
                    className="w-full text-left flex items-start gap-3 px-3 py-2.5 rounded-xl hover:bg-white/[0.03] border border-transparent hover:border-white/[0.06] group transition-all"
                  >
                    <div className="w-0.5 min-h-[36px] rounded-full self-stretch shrink-0" style={{ background: ev.color }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white/80 group-hover:text-white truncate transition-colors">{ev.title}</p>
                      <p className="font-mono text-[10px] text-white/30">{fmtTime(s)} — {fmtTime(e2)} · {durationLabel(s, e2)}</p>
                      {ev.location && <p className="font-mono text-[9px] text-white/20 truncate">{ev.location}</p>}
                    </div>
                  </button>
                );
              })}
              {dayTasks.map(t => (
                <div key={t.id} className="flex items-center gap-3 px-3 py-2 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                  <div className="w-3 h-3 rounded-full border border-white/20 shrink-0" />
                  <p className="text-[11px] text-white/50 truncate">{t.text}</p>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── AI Quick-add ─────────────────────────────────────────────────────────────

function NLQuickAdd({
  onParsed, onClose,
}: {
  onParsed: (draft: Partial<CalEvent>) => void;
  onClose: () => void;
}) {
  const [text,    setText]    = useState('');
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');

  const handleSubmit = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API}/api/events/parse-nl`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      onParsed(data.event);
    } catch (e: any) {
      setError(e.message || 'Failed to parse');
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -6, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.98 }}
      className="absolute top-full left-6 right-6 mt-2 z-50 bg-[#0d0d0d] border border-white/[0.1] rounded-2xl shadow-2xl p-4"
    >
      <div className="flex items-center gap-2 mb-3">
        <Zap size={12} className="text-primary/60" />
        <span className="font-mono text-[9px] text-white/30 uppercase tracking-widest">AI Event Parser</span>
      </div>
      <div className="flex gap-2">
        <input
          autoFocus
          type="text"
          placeholder='"DBMS exam tomorrow 2pm for 3 hours, Room 204"'
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') handleSubmit();
            if (e.key === 'Escape') onClose();
          }}
          className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/15 outline-none focus:border-primary/50"
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !text.trim()}
          className="px-4 py-2 bg-primary text-black text-xs font-bold rounded-lg hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          {loading ? '…' : 'Parse'}
        </button>
        <button onClick={onClose} className="px-3 py-2 bg-white/5 text-white/30 rounded-lg hover:bg-white/10 transition-colors">
          <X size={13} />
        </button>
      </div>
      {error && <p className="text-red-400/80 text-[11px] mt-2 font-mono">{error}</p>}
    </motion.div>
  );
}

// ── Month view ────────────────────────────────────────────────────────────────

function MonthView({
  year, month, events, tasks, today, onDayClick, onEventClick,
}: {
  year: number; month: number;
  events: CalEvent[]; tasks: Task[];
  today: Date;
  onDayClick: (d: Date) => void;
  onEventClick: (ev: CalEvent) => void;
}) {
  const firstDay = new Date(year, month, 1);
  const lastDay  = new Date(year, month + 1, 0);
  const startOffset = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1;
  const totalCells  = Math.ceil((startOffset + lastDay.getDate()) / 7) * 7;

  const cells: (Date | null)[] = Array.from({ length: totalCells }, (_, i) => {
    const dayNum = i - startOffset + 1;
    if (dayNum < 1 || dayNum > lastDay.getDate()) return null;
    return new Date(year, month, dayNum);
  });

  const evMap = new Map<string, CalEvent[]>();
  for (const ev of events) {
    const k = dayKey(new Date(ev.start_dt));
    if (!evMap.has(k)) evMap.set(k, []);
    evMap.get(k)!.push(ev);
  }

  const taskMap = new Map<string, Task[]>();
  for (const t of tasks.filter(t2 => !t2.completed && t2.due_date)) {
    const k = t.due_date!.slice(0, 10);
    if (!taskMap.has(k)) taskMap.set(k, []);
    taskMap.get(k)!.push(t);
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Day-of-week headers */}
      <div className="grid grid-cols-7 border-b border-white/[0.05] shrink-0">
        {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d => (
          <div key={d} className="py-2 text-center font-mono text-[9px] uppercase tracking-widest text-white/20">
            {d}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-7 h-full" style={{ gridAutoRows: 'minmax(90px, 1fr)' }}>
          {cells.map((date, i) => {
            if (!date) {
              return <div key={`e-${i}`} className="border-r border-b border-white/[0.04] bg-black/30" />;
            }
            const k        = dayKey(date);
            const isToday  = isSameDay(date, today);
            const dayEvs   = (evMap.get(k) || []).sort((a, b) => new Date(a.start_dt).getTime() - new Date(b.start_dt).getTime());
            const dayTasks = taskMap.get(k) || [];
            const overflow = dayEvs.length + dayTasks.length - 3;

            return (
              <div
                key={k}
                onClick={() => onDayClick(date)}
                className={`border-r border-b border-white/[0.04] p-1.5 flex flex-col gap-0.5 cursor-pointer group transition-colors
                  ${isToday ? 'bg-primary/[0.04]' : 'hover:bg-white/[0.015]'}`}
              >
                <div className={`w-6 h-6 flex items-center justify-center rounded-full text-[11px] font-mono font-bold mb-0.5 transition-colors
                  ${isToday ? 'bg-primary text-black' : 'text-white/30 group-hover:text-white/60'}`}>
                  {date.getDate()}
                </div>

                {dayEvs.slice(0, 3).map(ev => (
                  <button
                    key={ev.id}
                    onClick={e => { e.stopPropagation(); onEventClick(ev); }}
                    className="w-full text-left px-1.5 py-0.5 rounded text-[9px] truncate font-medium transition-opacity hover:opacity-80"
                    style={{ background: `${ev.color}20`, color: ev.color, borderLeft: `2px solid ${ev.color}` }}
                  >
                    {fmtTime(new Date(ev.start_dt))} {ev.title}
                  </button>
                ))}

                {dayTasks.slice(0, Math.max(0, 3 - dayEvs.length)).map(t => (
                  <div
                    key={t.id}
                    className="w-full text-left px-1.5 py-0.5 rounded text-[9px] truncate text-white/30 bg-white/[0.03] border border-white/[0.06]"
                  >
                    ✓ {t.text}
                  </div>
                ))}

                {overflow > 0 && (
                  <div className="text-[9px] font-mono text-white/25 px-1 mt-0.5">+{overflow} more</div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type ViewMode = 'week' | 'day' | 'month' | 'agenda';

export function CalendarView({ onNavigate: _onNavigate }: { onNavigate: (id: any) => void }) {
  const todayRef = useMemo(() => { const d = new Date(); d.setHours(0,0,0,0); return d; }, []);

  const [now,       setNow]       = useState(new Date());
  const [view,      setView]      = useState<ViewMode>('week');
  const [selected,  setSelected]  = useState<Date>(todayRef);
  const [weekStart, setWeekStart] = useState<Date>(() => getWeekStart(todayRef));
  const [monthYear, setMonthYear] = useState({
    year: todayRef.getFullYear(), month: todayRef.getMonth(),
  });

  const [events,  setEvents]  = useState<CalEvent[]>([]);
  const [tasks,   setTasks]   = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  const [selectedEvent,  setSelectedEvent]  = useState<CalEvent | null>(null);
  const [editingEvent,   setEditingEvent]   = useState<CalEvent | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createDraft,    setCreateDraft]    = useState<Partial<CalEvent>>({});
  const [showNL,         setShowNL]         = useState(false);

  // Add-task form state
  const [showAddTask,    setShowAddTask]    = useState(false);
  const [newTaskTitle,   setNewTaskTitle]   = useState('');
  const [newTaskDueDate, setNewTaskDueDate] = useState('');
  const [newTaskPriority,setNewTaskPriority]= useState('medium');
  const [addingTask,     setAddingTask]     = useState(false);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  const fetchEvents = useCallback(async () => {
    try {
      let s: Date, e: Date;
      if (view === 'month') {
        s = new Date(monthYear.year, monthYear.month, 1);
        e = new Date(monthYear.year, monthYear.month + 1, 0, 23, 59, 59);
      } else {
        s = new Date(weekStart); s.setDate(s.getDate() - 7);
        e = new Date(weekStart); e.setDate(e.getDate() + 14);
      }
      const res  = await fetch(`${API}/api/events?start=${s.toISOString()}&end=${e.toISOString()}`);
      if (!res.ok) throw new Error(`Events fetch failed: ${res.status}`);
      const data = await res.json();
      setEvents(data.events || []);
    } catch { setEvents([]); }
    finally  { setLoading(false); }
  }, [weekStart, view, monthYear]);

  const fetchTasks = useCallback(async () => {
    try {
      const res  = await fetch(`${API}/tasks`);
      const data = await res.json();
      setTasks(Array.isArray(data) ? data : (data.tasks || []));
    } catch { setTasks([]); }
  }, []);

  const doAddTask = async () => {
    if (!newTaskTitle.trim()) return;
    setAddingTask(true);
    try {
      const res = await fetch(`${API}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newTaskTitle.trim(),
          due_date: newTaskDueDate || null,
          priority: newTaskPriority,
          completed: false,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setNewTaskTitle('');
      setNewTaskDueDate('');
      setNewTaskPriority('medium');
      setShowAddTask(false);
      fetchTasks();
    } catch (e) {
      console.error('Failed to add task:', e);
    } finally {
      setAddingTask(false);
    }
  };

  useEffect(() => { fetchEvents(); }, [fetchEvents]);
  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  const weekDays = useMemo(() => getWeekDays(weekStart), [weekStart]);
  const dotDays  = useMemo(() => new Set(events.map(ev => dayKey(new Date(ev.start_dt)))), [events]);

  const goToday = () => {
    const t = new Date(); t.setHours(0,0,0,0);
    setSelected(t);
    setWeekStart(getWeekStart(t));
    setMonthYear({ year: t.getFullYear(), month: t.getMonth() });
  };

  const navPrev = () => {
    if (view === 'week') {
      setWeekStart(ws => { const d = new Date(ws); d.setDate(d.getDate() - 7); return d; });
    } else if (view === 'day') {
      setSelected(s => { const d = new Date(s); d.setDate(d.getDate() - 1); return d; });
    } else if (view === 'month') {
      setMonthYear(mv => {
        const m = mv.month - 1;
        return m < 0 ? { year: mv.year - 1, month: 11 } : { ...mv, month: m };
      });
    } else {
      setSelected(s => { const d = new Date(s); d.setDate(d.getDate() - 30); return d; });
    }
  };

  const navNext = () => {
    if (view === 'week') {
      setWeekStart(ws => { const d = new Date(ws); d.setDate(d.getDate() + 7); return d; });
    } else if (view === 'day') {
      setSelected(s => { const d = new Date(s); d.setDate(d.getDate() + 1); return d; });
    } else if (view === 'month') {
      setMonthYear(mv => {
        const m = mv.month + 1;
        return m > 11 ? { year: mv.year + 1, month: 0 } : { ...mv, month: m };
      });
    } else {
      setSelected(s => { const d = new Date(s); d.setDate(d.getDate() + 30); return d; });
    }
  };

  const doCreate = async (data: Partial<CalEvent>) => {
    try {
      const res = await fetch(`${API}/api/events`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(await res.text());
      const ev = await res.json();
      setEvents(evs => [...evs, ev]);
      setShowCreateForm(false);
      setCreateDraft({});
    } catch (e) { console.error(e); }
  };

  const doUpdate = async (data: Partial<CalEvent>) => {
    if (!editingEvent) return;
    try {
      const res = await fetch(`${API}/api/events/${editingEvent.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = await res.json();
      setEvents(evs => evs.map(e => e.id === updated.id ? updated : e));
      setEditingEvent(null);
      setSelectedEvent(updated);
    } catch (e) { console.error(e); }
  };

  const doDelete = async (id: string) => {
    try {
      await fetch(`${API}/api/events/${id}`, { method: 'DELETE' });
      setEvents(evs => evs.filter(e => e.id !== id));
      setSelectedEvent(null);
    } catch (e) { console.error(e); }
  };

  const handleSlotClick = (dt: Date) => {
    const end = new Date(dt.getTime() + 3_600_000);
    setCreateDraft({ start_dt: toLocalISO(dt), end_dt: toLocalISO(end) });
    setShowCreateForm(true);
    setSelectedEvent(null);
    setEditingEvent(null);
  };

  const handleEventClick = (ev: CalEvent) => {
    setSelectedEvent(ev);
    setShowCreateForm(false);
    setEditingEvent(null);
  };

  const viewLabel = view === 'week'
    ? `${weekDays[0].toLocaleDateString([],{ month:'short', day:'numeric' })} — ${weekDays[6].toLocaleDateString([],{ month:'short', day:'numeric', year:'numeric' })}`
    : view === 'day'
    ? selected.toLocaleDateString([],{ weekday:'long', month:'long', day:'numeric', year:'numeric' })
    : view === 'month'
    ? `${MONTH_NAMES[monthYear.month]} ${monthYear.year}`
    : `${MONTH_NAMES[selected.getMonth()]} ${selected.getFullYear()}`;

  return (
    <div className="h-full flex flex-col overflow-hidden bg-black text-white relative">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center justify-between px-6 pt-5 pb-3 border-b border-white/[0.05]">
        <div className="flex items-center gap-2">
          <button onClick={navPrev} className="p-1.5 rounded-lg hover:bg-white/5 text-white/30 hover:text-white/70 transition-colors">
            <ChevronLeft size={14} />
          </button>
          <span className="font-mono text-sm font-bold text-white/70 min-w-[220px] select-none">{viewLabel}</span>
          <button onClick={navNext} className="p-1.5 rounded-lg hover:bg-white/5 text-white/30 hover:text-white/70 transition-colors">
            <ChevronRight size={14} />
          </button>
          <button
            onClick={goToday}
            className="font-mono text-[10px] text-primary/70 hover:text-primary uppercase tracking-widest px-3 py-1.5 rounded-lg hover:bg-primary/10 transition-all ml-1"
          >
            Today
          </button>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-white/[0.07] overflow-hidden">
            {(['week', 'day', 'month', 'agenda'] as ViewMode[]).map(v => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors
                  ${view === v ? 'bg-white/10 text-white/80' : 'text-white/25 hover:text-white/60 hover:bg-white/5'}`}
              >
                {v}
              </button>
            ))}
          </div>

          <button
            onClick={() => setShowNL(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all font-mono text-[10px] uppercase tracking-widest
              ${showNL
                ? 'bg-primary/15 border-primary/40 text-primary'
                : 'border-white/[0.07] text-white/25 hover:text-white/60 hover:bg-white/5'}`}
          >
            <Zap size={11} /> AI
          </button>

          <button
            onClick={() => {
              const s = new Date(), e2 = new Date(s.getTime() + 3_600_000);
              setCreateDraft({ start_dt: toLocalISO(s), end_dt: toLocalISO(e2) });
              setShowCreateForm(true);
              setSelectedEvent(null);
              setEditingEvent(null);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-black text-xs font-bold rounded-lg hover:opacity-90 transition-opacity"
          >
            <Plus size={12} /> Event
          </button>
        </div>
      </div>

      <AnimatePresence>
        {showNL && (
          <NLQuickAdd
            onParsed={draft => {
              setCreateDraft(draft);
              setShowNL(false);
              setShowCreateForm(true);
              setSelectedEvent(null);
            }}
            onClose={() => setShowNL(false)}
          />
        )}
      </AnimatePresence>

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">

        {/* Left sidebar */}
        <div className="w-[212px] shrink-0 border-r border-white/[0.05] flex flex-col overflow-y-auto p-4 space-y-5">
          <MiniMonth
            year={monthYear.year}
            month={monthYear.month}
            selected={selected}
            today={todayRef}
            dotDays={dotDays}
            onSelect={d => {
              setSelected(d);
              setWeekStart(getWeekStart(d));
              const y = d.getFullYear(), m = d.getMonth();
              setMonthYear(mv => (mv.year === y && mv.month === m) ? mv : { year: y, month: m });
            }}
            onPrev={() => setMonthYear(mv => {
              const m = mv.month - 1;
              return m < 0 ? { year: mv.year - 1, month: 11 } : { ...mv, month: m };
            })}
            onNext={() => setMonthYear(mv => {
              const m = mv.month + 1;
              return m > 11 ? { year: mv.year + 1, month: 0 } : { ...mv, month: m };
            })}
          />

          <div>
            {/* Header row */}
            <div className="flex items-center justify-between mb-2">
              <span className="text-[9px] font-mono uppercase tracking-widest text-white/30">Pending Tasks</span>
              <button
                onClick={() => setShowAddTask(t => !t)}
                className="text-[9px] font-mono uppercase tracking-widest text-emerald-400/70 hover:text-emerald-400 transition-colors flex items-center gap-1"
              >
                <Plus size={9} /> Task
              </button>
            </div>

            {/* Inline add task form */}
            {showAddTask && (
              <div className="mb-3 p-2 rounded-lg bg-white/5 border border-white/10 space-y-2">
                <input
                  autoFocus
                  value={newTaskTitle}
                  onChange={e => setNewTaskTitle(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && doAddTask()}
                  placeholder="Task title..."
                  className="w-full bg-transparent text-xs text-white placeholder:text-white/30 outline-none border-b border-white/10 pb-1"
                />
                <input
                  type="date"
                  value={newTaskDueDate}
                  onChange={e => setNewTaskDueDate(e.target.value)}
                  className="w-full bg-transparent text-[10px] text-white/50 outline-none"
                />
                <div className="flex gap-1">
                  {['low','medium','high'].map(p => (
                    <button key={p} onClick={() => setNewTaskPriority(p)}
                      className={`px-2 py-0.5 text-[9px] font-mono uppercase rounded transition-colors ${
                        newTaskPriority === p ? 'bg-emerald-500/20 text-emerald-400' : 'text-white/30 hover:text-white/60'
                      }`}>{p}</button>
                  ))}
                  <button onClick={doAddTask} disabled={addingTask || !newTaskTitle.trim()}
                    className="ml-auto px-2 py-0.5 text-[9px] font-mono uppercase bg-emerald-500/20 text-emerald-400 rounded hover:bg-emerald-500/30 transition-colors disabled:opacity-40">
                    {addingTask ? '...' : 'Add'}
                  </button>
                </div>
              </div>
            )}

            {tasks.filter(t => !t.completed).length > 0 && (
              <div className="space-y-1.5">
                {tasks.filter(t => !t.completed).slice(0, 7).map(t => (
                  <div key={t.id} className="flex items-start gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-primary/40 mt-1 shrink-0" />
                    <span className="text-[10px] text-white/40 leading-snug line-clamp-2">{t.text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {showCreateForm && !selectedEvent && !editingEvent && (
            <div className="border-t border-white/[0.06] pt-4">
              <p className="font-mono text-[9px] text-white/30 uppercase tracking-widest mb-3">New Event</p>
              <EventForm
                draft={createDraft}
                onSave={doCreate}
                onCancel={() => { setShowCreateForm(false); setCreateDraft({}); }}
                isCreating={true}
              />
            </div>
          )}
        </div>

        {/* Center grid */}
        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <span className="font-mono text-[10px] text-white/20 uppercase tracking-widest">Loading…</span>
          </div>
        ) : view === 'week' ? (
          <WeekGrid
            events={events} tasks={tasks} weekDays={weekDays} now={now}
            onEventClick={handleEventClick} onSlotClick={handleSlotClick}
          />
        ) : view === 'day' ? (
          <WeekGrid
            events={events} tasks={tasks} weekDays={[selected]} now={now}
            onEventClick={handleEventClick} onSlotClick={handleSlotClick}
          />
        ) : view === 'month' ? (
          <MonthView
            year={monthYear.year} month={monthYear.month}
            events={events} tasks={tasks} today={todayRef}
            onDayClick={d => {
              setSelected(d);
              setWeekStart(getWeekStart(d));
              setView('week');
            }}
            onEventClick={handleEventClick}
          />
        ) : (
          <AgendaView
            events={events} tasks={tasks} startDate={selected}
            onEventClick={handleEventClick}
          />
        )}

        {/* Right panel */}
        <AnimatePresence mode="wait">
          {editingEvent ? (
            <motion.div
              key="edit-panel"
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 16 }}
              className="w-[272px] shrink-0 border-l border-white/[0.06] p-5 overflow-y-auto"
            >
              <div className="flex items-center justify-between mb-4">
                <p className="font-mono text-[9px] text-white/30 uppercase tracking-widest">Edit Event</p>
                <button onClick={() => setEditingEvent(null)} className="text-white/20 hover:text-white/60 transition-colors">
                  <X size={13} />
                </button>
              </div>
              <EventForm
                draft={editingEvent}
                onSave={doUpdate}
                onCancel={() => setEditingEvent(null)}
                isCreating={false}
              />
            </motion.div>
          ) : selectedEvent ? (
            <EventDetailPanel
              key={selectedEvent.id}
              event={selectedEvent}
              onEdit={() => { setEditingEvent(selectedEvent); setSelectedEvent(null); }}
              onDelete={() => doDelete(selectedEvent.id)}
              onClose={() => setSelectedEvent(null)}
            />
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}
