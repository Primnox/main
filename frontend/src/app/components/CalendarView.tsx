import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  ChevronLeft, ChevronRight, Calendar, Clock, MapPin,
  RefreshCw, CalendarDays, Settings, AlertCircle,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface CalEvent {
  title:       string;
  start:       string;   // ISO
  end:         string;
  location?:   string;
  description?:string;
  calendar?:   string;
  color?:      string;
  url?:        string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const parseDate  = (s: string) => new Date(s);
const isSameDay  = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth()    === b.getMonth()    &&
  a.getDate()     === b.getDate();
const fmtTime    = (d: Date) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const fmtFullDay = (d: Date) => d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
const dayNames   = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const monthNames = ['January','February','March','April','May','June',
                    'July','August','September','October','November','December'];

function durationLabel(start: Date, end: Date): string {
  const mins = Math.round((end.getTime() - start.getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60), m = mins % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

function minutesUntil(start: Date): number {
  return Math.round((start.getTime() - Date.now()) / 60000);
}

// ─── Mini-calendar ────────────────────────────────────────────────────────────

function MiniMonth({
  year, month, selected, today, dotDays, onSelect, onPrev, onNext,
}: {
  year: number; month: number; selected: Date; today: Date;
  dotDays: Set<string>;
  onSelect: (d: Date) => void; onPrev: () => void; onNext: () => void;
}) {
  const firstDay  = new Date(year, month, 1).getDay();
  const daysInMo  = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMo; d++) cells.push(d);

  return (
    <div className="select-none">
      <div className="flex items-center justify-between mb-4">
        <button onClick={onPrev} className="p-1.5 rounded-lg hover:bg-white/5 text-white/30 hover:text-white/70 transition-colors">
          <ChevronLeft size={14} />
        </button>
        <span className="font-mono text-[11px] font-bold text-white/60 uppercase tracking-widest">
          {monthNames[month]} {year}
        </span>
        <button onClick={onNext} className="p-1.5 rounded-lg hover:bg-white/5 text-white/30 hover:text-white/70 transition-colors">
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-px mb-2">
        {dayNames.map(d => (
          <div key={d} className="text-center font-mono text-[9px] text-white/20 uppercase tracking-wider pb-1">
            {d[0]}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-px">
        {cells.map((day, i) => {
          if (!day) return <div key={`e-${i}`} />;
          const date    = new Date(year, month, day);
          const isToday = isSameDay(date, today);
          const isSel   = isSameDay(date, selected);
          const hasDot  = dotDays.has(`${year}-${String(month + 1).padStart(2,'0')}-${String(day).padStart(2,'0')}`);
          return (
            <button
              key={day}
              onClick={() => onSelect(date)}
              className={`relative flex flex-col items-center justify-center h-8 w-full rounded-lg text-[11px] font-mono font-bold transition-all duration-150 active:scale-90
                ${isSel   ? 'bg-primary text-black shadow-lg shadow-primary/30'
                : isToday ? 'text-primary ring-1 ring-primary/30 bg-primary/5'
                :           'text-white/40 hover:text-white hover:bg-white/5'}`}
            >
              {day}
              {hasDot && !isSel && (
                <span className="absolute bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-primary/60" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Event card ───────────────────────────────────────────────────────────────

function EventCard({ ev, now }: { ev: CalEvent; now: Date }) {
  const start   = parseDate(ev.start);
  const end     = parseDate(ev.end);
  const isNow   = now >= start && now < end;
  const mins    = minutesUntil(start);
  const color   = ev.color || '#6366f1';
  const dur     = durationLabel(start, end);

  let badge: string | null = null;
  let badgeClass = '';
  if (isNow) { badge = 'Now'; badgeClass = 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'; }
  else if (mins > 0 && mins <= 15) { badge = `in ${mins}m`; badgeClass = 'bg-amber-500/20 text-amber-400 border-amber-500/30'; }
  else if (mins > 0 && mins <= 60) { badge = `in ${mins}m`; badgeClass = 'bg-white/5 text-white/30 border-white/10'; }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative flex gap-4 px-5 py-4 rounded-2xl border transition-all
        ${isNow
          ? 'bg-white/[0.03] border-white/10 shadow-lg'
          : 'bg-white/[0.015] border-white/[0.06] hover:bg-white/[0.03] hover:border-white/10'}`}
    >
      {/* Left accent */}
      <div className="shrink-0 flex flex-col items-center gap-1 pt-0.5">
        <div className="w-0.5 h-full min-h-[48px] rounded-full" style={{ background: isNow ? color : `${color}60` }} />
      </div>

      {/* Time column */}
      <div className="shrink-0 w-[80px]">
        <p className="font-mono text-[11px] font-bold text-white/60">{fmtTime(start)}</p>
        <p className="font-mono text-[10px] text-white/20">{fmtTime(end)}</p>
        <p className="font-mono text-[9px] text-white/15 mt-1">{dur}</p>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2 mb-1">
          <p className={`text-sm font-semibold leading-tight ${isNow ? 'text-white' : 'text-white/80'}`}>
            {ev.title}
          </p>
          {badge && (
            <span className={`shrink-0 font-mono text-[9px] px-2 py-0.5 rounded border ${badgeClass}`}>
              {badge}
            </span>
          )}
        </div>
        {ev.location && (
          <div className="flex items-center gap-1.5 mt-1">
            <MapPin size={9} className="text-white/20 shrink-0" />
            <span className="font-mono text-[10px] text-white/30 truncate">{ev.location}</span>
          </div>
        )}
        {ev.calendar && (
          <div className="flex items-center gap-1.5 mt-0.5">
            <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: `${color}80` }} />
            <span className="font-mono text-[9px] text-white/20 uppercase tracking-wider">{ev.calendar}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ─── Week strip ───────────────────────────────────────────────────────────────

function WeekStrip({
  baseDate, selected, today, dotDays, onSelect,
}: {
  baseDate: Date; selected: Date; today: Date;
  dotDays: Set<string>; onSelect: (d: Date) => void;
}) {
  const monday = new Date(baseDate);
  const dow = monday.getDay();
  monday.setDate(monday.getDate() - (dow === 0 ? 6 : dow - 1));

  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });

  return (
    <div className="flex gap-1.5">
      {days.map((d, i) => {
        const isSel   = isSameDay(d, selected);
        const isToday = isSameDay(d, today);
        const key     = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
        const hasDot  = dotDays.has(key);
        return (
          <button
            key={i}
            onClick={() => onSelect(d)}
            className={`flex-1 flex flex-col items-center py-2.5 rounded-xl transition-all duration-150 active:scale-95
              ${isSel   ? 'bg-primary text-black shadow-lg shadow-primary/20'
              : isToday ? 'bg-primary/10 text-primary ring-1 ring-primary/20'
              :           'text-white/30 hover:text-white/60 hover:bg-white/5'}`}
          >
            <span className="font-mono text-[9px] uppercase tracking-widest mb-1">
              {dayNames[(d.getDay())]}
            </span>
            <span className={`font-mono text-[13px] font-bold ${isSel ? 'text-black' : ''}`}>
              {d.getDate()}
            </span>
            {hasDot && !isSel && (
              <span className="mt-1 w-1 h-1 rounded-full bg-primary/60" />
            )}
          </button>
        );
      })}
    </div>
  );
}

// ─── Main View ────────────────────────────────────────────────────────────────

export function CalendarView({ onNavigate }: { onNavigate: (id: any) => void }) {
  const today             = new Date();
  const [selected,    setSelected]    = useState<Date>(today);
  const [monthYear,   setMonthYear]   = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [events,      setEvents]      = useState<CalEvent[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState<string | null>(null);
  const [refreshing,  setRefreshing]  = useState(false);
  const [now,         setNow]         = useState(new Date());

  // Tick clock every minute
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  const fetchEvents = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const res = await fetch('http://localhost:8000/api/calendar/events?days=30');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setEvents(data.events || []);
    } catch (e: any) {
      setError(e.message || 'Failed to load events');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  // Days that have at least one event (for dots)
  const dotDays = new Set<string>(
    events.map(ev => {
      const d = parseDate(ev.start);
      return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    })
  );

  // Events for the selected day, sorted by start
  const dayEvents = events
    .filter(ev => isSameDay(parseDate(ev.start), selected))
    .sort((a, b) => parseDate(a.start).getTime() - parseDate(b.start).getTime());

  // Upcoming events across all days (next 7 days, not today)
  const upcomingEvents = events
    .filter(ev => {
      const s = parseDate(ev.start);
      return s > new Date(selected.getFullYear(), selected.getMonth(), selected.getDate() + 1);
    })
    .slice(0, 5);

  const isToday = isSameDay(selected, today);

  return (
    <div className="h-full flex flex-col overflow-hidden bg-black text-white">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-8 pt-6 pb-4 border-b border-white/[0.05] shrink-0">
        <div className="flex items-center gap-3">
          <CalendarDays size={16} className="text-primary/60" />
          <div>
            <h1 className="font-bold text-lg leading-none">
              {isToday ? 'Today' : fmtFullDay(selected)}
            </h1>
            <p className="font-mono text-[10px] text-white/20 uppercase tracking-widest mt-0.5">
              {isToday ? fmtFullDay(today) : `${dayEvents.length} event${dayEvents.length !== 1 ? 's' : ''}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isToday || (
            <button
              onClick={() => setSelected(today)}
              className="font-mono text-[10px] text-primary/70 hover:text-primary uppercase tracking-widest px-3 py-1.5 rounded-lg hover:bg-primary/10 transition-all"
            >
              Today
            </button>
          )}
          <button
            onClick={() => fetchEvents(true)}
            disabled={refreshing}
            className="p-2 rounded-lg hover:bg-white/5 text-white/20 hover:text-white/60 transition-all"
          >
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => onNavigate('island_settings')}
            className="p-2 rounded-lg hover:bg-white/5 text-white/20 hover:text-white/60 transition-all"
            title="Calendar settings"
          >
            <Settings size={13} />
          </button>
        </div>
      </div>

      {/* ── Body ──────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">

        {/* Left: mini month + upcoming ───────────────────────────────── */}
        <div className="w-[240px] shrink-0 border-r border-white/[0.05] flex flex-col overflow-y-auto p-5 space-y-6">
          <MiniMonth
            year={monthYear.year}
            month={monthYear.month}
            selected={selected}
            today={today}
            dotDays={dotDays}
            onSelect={d => { setSelected(d); setMonthYear({ year: d.getFullYear(), month: d.getMonth() }); }}
            onPrev={() => setMonthYear(mv => {
              const m = mv.month - 1;
              return m < 0 ? { year: mv.year - 1, month: 11 } : { ...mv, month: m };
            })}
            onNext={() => setMonthYear(mv => {
              const m = mv.month + 1;
              return m > 11 ? { year: mv.year + 1, month: 0 } : { ...mv, month: m };
            })}
          />

          {/* Calendar legend */}
          {events.length > 0 && (() => {
            const cals = [...new Set(events.map(e => e.calendar).filter(Boolean))];
            if (!cals.length) return null;
            return (
              <div className="space-y-2">
                <p className="font-mono text-[9px] text-white/20 uppercase tracking-widest">Calendars</p>
                {cals.map(cal => {
                  const color = events.find(e => e.calendar === cal)?.color || '#6366f1';
                  return (
                    <div key={cal} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                      <span className="font-mono text-[10px] text-white/40 truncate">{cal}</span>
                    </div>
                  );
                })}
              </div>
            );
          })()}

          {/* Upcoming events mini-list */}
          {upcomingEvents.length > 0 && (
            <div className="space-y-2">
              <p className="font-mono text-[9px] text-white/20 uppercase tracking-widest">Upcoming</p>
              {upcomingEvents.map((ev, i) => {
                const s = parseDate(ev.start);
                return (
                  <button
                    key={i}
                    onClick={() => setSelected(s)}
                    className="w-full text-left group"
                  >
                    <div className="flex items-start gap-2 py-1.5 px-2 rounded-lg hover:bg-white/5 transition-colors">
                      <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ background: ev.color || '#6366f1' }} />
                      <div className="min-w-0">
                        <p className="text-[11px] text-white/60 group-hover:text-white/80 truncate transition-colors leading-tight">{ev.title}</p>
                        <p className="font-mono text-[9px] text-white/20">
                          {s.toLocaleDateString([], { month: 'short', day: 'numeric' })} · {fmtTime(s)}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Right: week strip + day agenda ────────────────────────────── */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Week strip */}
          <div className="px-6 pt-4 pb-3 border-b border-white/[0.04] shrink-0">
            <WeekStrip
              baseDate={selected}
              selected={selected}
              today={today}
              dotDays={dotDays}
              onSelect={setSelected}
            />
          </div>

          {/* Day agenda */}
          <div className="flex-1 overflow-y-auto px-6 py-5">
            <AnimatePresence mode="wait">
              {loading ? (
                <motion.div
                  key="loading"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center justify-center h-48 gap-3"
                >
                  <RefreshCw size={18} className="text-white/20 animate-spin" />
                  <span className="font-mono text-[10px] text-white/20 uppercase tracking-widest">Loading events…</span>
                </motion.div>

              ) : error ? (
                <motion.div
                  key="error"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center justify-center h-48 gap-4"
                >
                  <AlertCircle size={22} className="text-red-400/50" />
                  <div className="text-center">
                    <p className="text-sm text-white/40">{error}</p>
                    <p className="font-mono text-[10px] text-white/20 mt-1">
                      Make sure the backend is running and a calendar is connected.
                    </p>
                  </div>
                  <button
                    onClick={() => fetchEvents()}
                    className="font-mono text-[10px] text-primary/70 hover:text-primary uppercase tracking-widest px-4 py-2 rounded-lg border border-primary/20 hover:border-primary/40 transition-all"
                  >
                    Retry
                  </button>
                </motion.div>

              ) : events.length === 0 ? (
                <motion.div
                  key="empty"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center justify-center h-56 gap-4"
                >
                  <Calendar size={28} className="text-white/10" />
                  <div className="text-center space-y-1">
                    <p className="text-sm text-white/30 font-medium">No calendar connected</p>
                    <p className="font-mono text-[10px] text-white/15">
                      Add an iCal URL in Configure → Calendar to see your events here.
                    </p>
                  </div>
                  <button
                    onClick={() => onNavigate('island_settings')}
                    className="flex items-center gap-2 font-mono text-[10px] text-primary/70 hover:text-primary uppercase tracking-widest px-4 py-2 rounded-lg border border-primary/20 hover:border-primary/40 transition-all"
                  >
                    <Settings size={12} /> Open Settings
                  </button>
                </motion.div>

              ) : dayEvents.length === 0 ? (
                <motion.div
                  key={`empty-day-${selected.toDateString()}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center justify-center h-48 gap-3"
                >
                  <Clock size={20} className="text-white/10" />
                  <p className="font-mono text-[10px] text-white/20 uppercase tracking-widest">
                    Nothing scheduled
                  </p>
                </motion.div>

              ) : (
                <motion.div
                  key={selected.toDateString()}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="space-y-3"
                >
                  {dayEvents.map((ev, i) => (
                    <EventCard key={i} ev={ev} now={now} />
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}
