import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Database, CheckCircle, Search, Trash2, Tag, Clock, Plus } from 'lucide-react';

const API_BASE_URL = 'http://localhost:8000';

const CATEGORY_COLORS: Record<string, string> = {
  work:    'text-blue-400 bg-blue-500/10 border-blue-500/20',
  personal:'text-violet-400 bg-violet-500/10 border-violet-500/20',
  project: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  session: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
};

export const DataVaultPage = ({
  memory = [],
  onMemoryDeleted,
}: {
  onAccess?: () => void;
  memory?: any[];
  onMemoryDeleted?: (key: string) => void;
}) => {
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  // Manual add
  const [showAddForm, setShowAddForm] = useState(false);
  const [newMemText, setNewMemText] = useState('');
  const [newMemCat, setNewMemCat] = useState<'work' | 'personal' | 'project' | 'session'>('personal');
  const [addingMem, setAddingMem] = useState(false);
  const [addResult, setAddResult] = useState<'saved' | 'duplicate' | null>(null);

  const handleSearch = useCallback(async (q: string) => {
    setQuery(q);
    if (!q.trim()) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/memories/search?q=${encodeURIComponent(q)}&limit=30`);
      const data = await resp.json();
      setSearchResults(data?.memories ?? []);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, []);

  const handleDelete = useCallback(async (key: string) => {
    if (!key) return;
    setDeletingKey(key);
    try {
      await fetch(`${API_BASE_URL}/api/memories/${encodeURIComponent(key)}`, { method: 'DELETE' });
      onMemoryDeleted?.(key);
      // Also remove from search results if active
      setSearchResults(prev => prev ? prev.filter(m => m.key !== key) : null);
    } catch {
      // ignore
    } finally {
      setDeletingKey(null);
    }
  }, [onMemoryDeleted]);

  const handleAddMemory = useCallback(async () => {
    const text = newMemText.trim();
    if (!text) return;
    setAddingMem(true);
    setAddResult(null);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/memories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, category: newMemCat }),
      });
      const data = await resp.json();
      setAddResult(data.duplicate ? 'duplicate' : 'saved');
      if (!data.duplicate) {
        setNewMemText('');
        onMemoryDeleted?.('__refresh__'); // signal parent to refetch
      }
      setTimeout(() => { setAddResult(null); if (!data.duplicate) setShowAddForm(false); }, 2000);
    } catch {
      setAddResult(null);
    } finally {
      setAddingMem(false);
    }
  }, [newMemText, newMemCat, onMemoryDeleted]);

  const displayed = searchResults ?? memory;

  return (
    <div className="flex-1 flex flex-col h-full bg-black animate-in fade-in slide-in-from-right-8 duration-1000 overflow-hidden text-left">
      {/* Header */}
      <div className="p-8 lg:p-12 border-b border-white/5 bg-zinc-950 flex items-center justify-between">
        <div className="flex flex-col">
          <span className="font-mono text-primary text-[10px] uppercase tracking-[0.4em] mb-2 block font-bold">Cold_Storage_Interface</span>
          <h2 className="text-white text-xl font-bold tracking-tighter italic">Data_Vault.sh</h2>
        </div>
        <div className="flex items-center gap-4">
          <div className="px-4 py-2 bg-primary/10 border border-primary/20 rounded-lg">
            <span className="font-mono text-[10px] text-primary font-bold animate-pulse">ENCRYPTION: ACTIVE</span>
          </div>
          <span className="font-mono text-[10px] text-white/30">{memory.length} nodes</span>
          <button
            onClick={() => setShowAddForm(f => !f)}
            className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-white/60 hover:text-white transition-colors"
            title="Manually inject a memory"
          >
            <Plus size={13} />
            <span className="font-mono text-[9px] uppercase tracking-widest font-bold">Inject</span>
          </button>
        </div>
      </div>

      {/* Search bar */}
      <div className="px-8 lg:px-12 py-4 border-b border-white/5 bg-zinc-950/60">
        <div className="relative max-w-md">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
          <input
            type="text"
            value={query}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Search memories..."
            className="w-full bg-white/5 border border-white/10 rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-primary/40 transition-colors font-mono"
          />
          {searching && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 w-3 h-3 border border-primary/60 border-t-primary rounded-full animate-spin" />
          )}
        </div>
        {searchResults !== null && (
          <p className="mt-2 font-mono text-[10px] text-white/30">
            {searchResults.length} result{searchResults.length !== 1 ? 's' : ''} for &ldquo;{query}&rdquo;
          </p>
        )}
      </div>

      {/* Inject Memory form */}
      <AnimatePresence>
        {showAddForm && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-b border-white/5 bg-zinc-950/40"
          >
            <div className="px-8 lg:px-12 py-4 flex flex-col gap-3 max-w-2xl">
              <textarea
                autoFocus
                value={newMemText}
                onChange={e => setNewMemText(e.target.value)}
                placeholder="Enter the memory to inject..."
                rows={2}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:border-primary/40 transition-colors resize-none"
              />
              <div className="flex items-center gap-3">
                <select
                  value={newMemCat}
                  onChange={e => setNewMemCat(e.target.value as any)}
                  className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-[10px] font-mono text-white/60 outline-none focus:border-primary/40"
                >
                  <option value="personal">personal</option>
                  <option value="work">work</option>
                  <option value="project">project</option>
                  <option value="session">session</option>
                </select>
                <button
                  onClick={handleAddMemory}
                  disabled={!newMemText.trim() || addingMem}
                  className="px-4 py-1.5 bg-primary/10 border border-primary/20 rounded-lg text-primary font-mono text-[9px] uppercase tracking-widest hover:bg-primary/20 disabled:opacity-30 transition-all"
                >
                  {addingMem ? 'Saving…' : addResult === 'saved' ? 'Saved ✓' : addResult === 'duplicate' ? 'Duplicate ✗' : 'Save Memory'}
                </button>
                <button
                  onClick={() => setShowAddForm(false)}
                  className="text-white/20 hover:text-white transition-colors font-mono text-[10px]"
                >
                  cancel
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Memory grid */}
      <div className="flex-1 overflow-y-auto p-8 lg:p-12 custom-scrollbar">
        <div className="max-w-6xl w-full grid grid-cols-1 md:grid-cols-2 gap-6">
          <AnimatePresence mode="popLayout">
            {displayed.length === 0 ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="col-span-full p-20 text-center text-white/10 font-mono text-xs uppercase tracking-[0.4em]"
              >
                {query ? 'No memories match your search' : 'Neural Vault Empty'}
              </motion.div>
            ) : (
              displayed.map((item: any, i: number) => {
                const catStyle = CATEGORY_COLORS[item.category] ?? CATEGORY_COLORS.session;
                const timeStr = item.timestamp
                  ? new Date(item.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric' })
                  : null;
                return (
                  <motion.div
                    key={item.key ?? i}
                    layout
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.9 }}
                    transition={{ delay: Math.min(i * 0.05, 0.5) }}
                    className="p-8 bg-zinc-900/20 border border-white/5 rounded-2xl group hover:border-primary/30 transition-all relative overflow-hidden"
                  >
                    <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                      <Database size={80} />
                    </div>

                    <div className="flex justify-between items-start mb-4">
                      <span className="font-mono text-[9px] text-white/20 tracking-widest">
                        VOL_{i.toString().padStart(3, '0')}
                      </span>
                      <div className="flex items-center gap-2">
                        {item.category && (
                          <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full border text-[8px] font-mono uppercase tracking-wider ${catStyle}`}>
                            <Tag size={8} />
                            {item.category}
                          </span>
                        )}
                        <div className="p-1.5 rounded-lg border border-emerald-500/20 text-emerald-500 bg-emerald-500/5">
                          <CheckCircle size={14} />
                        </div>
                      </div>
                    </div>

                    <p className="text-white font-medium text-sm leading-relaxed mb-4 italic">
                      {item.text || String(item)}
                    </p>

                    <div className="flex justify-between items-center pt-4 border-t border-white/[0.04]">
                      {timeStr ? (
                        <span className="flex items-center gap-1.5 font-mono text-[9px] text-white/30">
                          <Clock size={10} />
                          {timeStr}
                        </span>
                      ) : (
                        <span className="font-mono text-[9px] text-white/20">NODE_SAVED</span>
                      )}
                      <button
                        onClick={() => handleDelete(item.key)}
                        disabled={deletingKey === item.key}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/5 hover:bg-red-500/20 text-red-400/40 hover:text-red-400 border border-red-500/10 hover:border-red-500/30 font-mono text-[9px] uppercase tracking-widest rounded-lg transition-all opacity-0 group-hover:opacity-100 disabled:opacity-30"
                      >
                        <Trash2 size={10} />
                        {deletingKey === item.key ? 'Deleting...' : 'Forget'}
                      </button>
                    </div>
                  </motion.div>
                );
              })
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};
