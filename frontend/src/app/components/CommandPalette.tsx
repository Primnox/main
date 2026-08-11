import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Search, MessageSquare, FileText, LayoutDashboard, Calendar,
  Network, Database, Settings, History, Globe, Mic, BookOpen,
  Plus, Sparkles, ArrowRight, Command
} from 'lucide-react';

export type ScreenId =
  | 'summaries_expanded' | 'summaries_empty_state'
  | 'notes_icon_sidebar' | 'chat_expanded_sidebar' | 'research_workspace'
  | 'calendar' | 'meetings' | 'graph_view' | 'archive' | 'knowledge'
  | 'logs' | 'island_settings' | 'settings_neural';

interface PaletteAction {
  id: string;
  label: string;
  description?: string;
  icon: React.ReactNode;
  group: string;
  keywords?: string[];
  action: () => void;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (screen: ScreenId) => void;
  onNewNote?: () => void;
  onNewChat?: () => void;
  onSendMessage?: (text: string) => void;
}

export const CommandPalette = ({ isOpen, onClose, onNavigate, onNewNote, onNewChat, onSendMessage }: Props) => {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const actions: PaletteAction[] = useMemo(() => [
    {
      id: 'nav-chat', label: 'Synapse Stream', description: 'Open chat', icon: <MessageSquare size={16} />,
      group: 'Navigate', keywords: ['chat', 'talk', 'message'],
      action: () => { onNavigate('chat_expanded_sidebar'); onClose(); }
    },
    {
      id: 'nav-notes', label: 'Neural Nodes', description: 'Open notes', icon: <FileText size={16} />,
      group: 'Navigate', keywords: ['notes', 'write', 'documents'],
      action: () => { onNavigate('notes_icon_sidebar'); onClose(); }
    },
    {
      id: 'nav-dashboard', label: 'Dashboard', description: 'Open dashboard', icon: <LayoutDashboard size={16} />,
      group: 'Navigate', keywords: ['home', 'summary', 'overview'],
      action: () => { onNavigate('summaries_expanded'); onClose(); }
    },
    {
      id: 'nav-calendar', label: 'Calendar', description: 'View calendar & events', icon: <Calendar size={16} />,
      group: 'Navigate', keywords: ['calendar', 'events', 'schedule'],
      action: () => { onNavigate('calendar'); onClose(); }
    },
    {
      id: 'nav-research', label: 'Deep Research', description: 'Web search workspace', icon: <Globe size={16} />,
      group: 'Navigate', keywords: ['research', 'search', 'web'],
      action: () => { onNavigate('research_workspace'); onClose(); }
    },
    {
      id: 'nav-meetings', label: 'Recordings', description: 'Meeting recordings', icon: <Mic size={16} />,
      group: 'Navigate', keywords: ['meetings', 'recordings', 'audio'],
      action: () => { onNavigate('meetings'); onClose(); }
    },
    {
      id: 'nav-graph', label: 'Knowledge Graph', description: 'Visualize note connections', icon: <Network size={16} />,
      group: 'Navigate', keywords: ['graph', 'network', 'connections', 'links'],
      action: () => { onNavigate('graph_view'); onClose(); }
    },
    {
      id: 'nav-vault', label: 'Data Vault', description: 'Stored memories', icon: <Database size={16} />,
      group: 'Navigate', keywords: ['memory', 'vault', 'data', 'archive'],
      action: () => { onNavigate('archive'); onClose(); }
    },
    {
      id: 'nav-knowledge', label: 'Knowledge Nexus', description: 'System documentation', icon: <BookOpen size={16} />,
      group: 'Navigate', keywords: ['knowledge', 'docs', 'about'],
      action: () => { onNavigate('knowledge'); onClose(); }
    },
    {
      id: 'nav-logs', label: 'System Logs', description: 'View activity logs', icon: <History size={16} />,
      group: 'Navigate', keywords: ['logs', 'activity', 'debug'],
      action: () => { onNavigate('logs'); onClose(); }
    },
    {
      id: 'nav-settings', label: 'Settings', description: 'Configure Primnox', icon: <Settings size={16} />,
      group: 'Navigate', keywords: ['settings', 'config', 'preferences', 'api key'],
      action: () => { onNavigate('island_settings'); onClose(); }
    },
    {
      id: 'new-note', label: 'New Note', description: 'Create a blank note', icon: <Plus size={16} />,
      group: 'Create', keywords: ['new', 'create', 'add', 'write'],
      action: () => { onNavigate('notes_icon_sidebar'); onNewNote?.(); onClose(); }
    },
    {
      id: 'new-chat', label: 'New Chat', description: 'Start a new conversation', icon: <MessageSquare size={16} />,
      group: 'Create', keywords: ['new', 'chat', 'conversation'],
      action: () => { onNavigate('chat_expanded_sidebar'); onNewChat?.(); onClose(); }
    },
    {
      id: 'new-event', label: 'New Event', description: 'Add a calendar event', icon: <Calendar size={16} />,
      group: 'Create', keywords: ['event', 'meeting', 'schedule', 'appointment'],
      action: () => { onNavigate('calendar'); onClose(); }
    },
  ], [onNavigate, onClose, onNewNote, onNewChat]);

  const filtered = useMemo(() => {
    if (!query.trim()) return actions;
    const q = query.toLowerCase();
    return actions.filter(a =>
      a.label.toLowerCase().includes(q) ||
      a.description?.toLowerCase().includes(q) ||
      a.keywords?.some(k => k.includes(q))
    );
  }, [query, actions]);

  const groups = useMemo(() => {
    const map: Record<string, PaletteAction[]> = {};
    for (const a of filtered) {
      if (!map[a.group]) map[a.group] = [];
      map[a.group].push(a);
    }
    return map;
  }, [filtered]);

  const flatFiltered = filtered;

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    setSelected(0);
  }, [query]);

  const runSelected = useCallback(() => {
    if (flatFiltered[selected]) {
      flatFiltered[selected].action();
    } else if (query.trim() && onSendMessage) {
      onSendMessage(query.trim());
      onNavigate('chat_expanded_sidebar');
      onClose();
    }
  }, [flatFiltered, selected, query, onSendMessage, onNavigate, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return; }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const maxIdx = flatFiltered.length - 1 + (query.trim() && onSendMessage ? 1 : 0);
        setSelected(s => Math.min(s + 1, maxIdx));
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelected(s => Math.max(s - 1, 0));
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        runSelected();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onClose, flatFiltered, runSelected, query, onSendMessage]);

  // Scroll selected item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-index="${selected}"]`) as HTMLElement | null;
    el?.scrollIntoView({ block: 'nearest' });
  }, [selected]);

  let globalIdx = 0;

  return (
    <AnimatePresence>
      {isOpen && (
        <div
          className="fixed inset-0 z-[999] flex items-start justify-center pt-[15vh]"
          onClick={onClose}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-surface/60 backdrop-blur-sm" />

          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -10 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-full max-w-[600px] mx-4 bg-surface border border-on-surface/10 rounded-2xl shadow-2xl overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            {/* Search bar */}
            <div className="flex items-center gap-3 px-5 py-4 border-b border-on-surface/5">
              <Search size={18} className="text-on-surface/55 shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search commands, navigate, create..."
                className="flex-1 bg-transparent text-on-surface placeholder-on-surface/25 outline-none text-sm font-mono"
              />
              <div className="flex items-center gap-1 shrink-0">
                <kbd className="px-2 py-0.5 bg-on-surface/5 text-on-surface/55 rounded text-[10px] font-mono border border-on-surface/10">ESC</kbd>
              </div>
            </div>

            {/* Results */}
            <div ref={listRef} className="max-h-[400px] overflow-y-auto py-2">
              {Object.keys(groups).length === 0 && (
                <div className="px-5 py-8 text-center text-on-surface/55 font-mono text-xs">
                  No commands match "{query}"
                </div>
              )}
              {Object.entries(groups).map(([group, items]) => (
                <div key={group} className="mb-1">
                  <div className="px-5 py-1.5 text-[10px] font-mono uppercase tracking-widest text-on-surface/48">
                    {group}
                  </div>
                  {items.map((item) => {
                    const idx = globalIdx++;
                    const isActive = selected === idx;
                    return (
                      <button
                        key={item.id}
                        data-index={idx}
                        onMouseEnter={() => setSelected(idx)}
                        onClick={item.action}
                        className={`w-full flex items-center gap-3 px-5 py-3 text-left transition-colors ${
                          isActive ? 'bg-primary/10 text-on-surface' : 'text-on-surface/60 hover:text-on-surface'
                        }`}
                      >
                        <span className={`shrink-0 ${isActive ? 'text-primary' : 'text-on-surface/55'}`}>
                          {item.icon}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{item.label}</div>
                          {item.description && (
                            <div className="text-[11px] text-on-surface/55 truncate">{item.description}</div>
                          )}
                        </div>
                        {isActive && <ArrowRight size={14} className="text-primary/50 shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              ))}

              {/* Ask AI fallback when there's a query and no perfect match */}
              {query.trim() && onSendMessage && (
                <div className="border-t border-on-surface/5 mt-1 pt-1">
                  <button
                    data-index={globalIdx}
                    onMouseEnter={() => setSelected(globalIdx)}
                    onClick={() => { onSendMessage(query.trim()); onNavigate('chat_expanded_sidebar'); onClose(); }}
                    className={`w-full flex items-center gap-3 px-5 py-3 text-left transition-colors ${
                      selected === globalIdx ? 'bg-primary/10 text-on-surface' : 'text-on-surface/60 hover:text-on-surface'
                    }`}
                  >
                    <Sparkles size={16} className={selected === globalIdx ? 'text-primary' : 'text-on-surface/55'} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium">Ask AI: "{query}"</div>
                      <div className="text-[11px] text-on-surface/55">Send as message to Primnox</div>
                    </div>
                    {selected === globalIdx && <ArrowRight size={14} className="text-primary/50 shrink-0" />}
                  </button>
                </div>
              )}
            </div>

            {/* Footer hint */}
            <div className="px-5 py-2.5 border-t border-on-surface/5 flex items-center gap-4 text-[10px] font-mono text-on-surface/48">
              <span className="flex items-center gap-1.5">
                <kbd className="px-1.5 py-0.5 bg-on-surface/5 rounded border border-on-surface/10">↑↓</kbd> navigate
              </span>
              <span className="flex items-center gap-1.5">
                <kbd className="px-1.5 py-0.5 bg-on-surface/5 rounded border border-on-surface/10">↵</kbd> select
              </span>
              <span className="flex items-center gap-1.5">
                <kbd className="px-1.5 py-0.5 bg-on-surface/5 rounded border border-on-surface/10">ESC</kbd> close
              </span>
              <span className="ml-auto flex items-center gap-1">
                <Command size={10} /> K to open
              </span>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
