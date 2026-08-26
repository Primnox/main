/**
 * Extracted Conversation List Component
 *
 * Shows pinned chats, folders (collapsible), day-grouped recent chats, and search.
 * Supports drag-to-file and inline editing.
 *
 * DO-NOT-CHANGE:
 * - Order: Pinned → Folders → Day-grouped Recent (canonical structure)
 * - Incognito chats cannot be filed (no disk persistence)
 * - Search results override structure (flat list of matches only)
 */

import { ChevronRight, EyeOff, Folder, MessageSquare, MoreHorizontal, Pin, Search, X } from 'lucide-react';
import { useState, useMemo } from 'react';

export interface ConversationListItem {
  id: string;
  title: string;
  incognito?: boolean;
  pinned_at?: boolean;
  folder_id?: string;
  turn_count?: number;
  created_at?: number;
}

export interface Folder {
  id: string;
  name: string;
}

export interface ConversationListProps {
  conversations: ConversationListItem[];
  folders: Folder[];
  activeId?: string;
  onOpenConversation: (id: string) => void;
  onRenameConversation?: (id: string, newTitle: string) => void;
  onTogglePinned?: (id: string) => void;
  onMoveToFolder?: (id: string, folderId: string | null) => void;
  onDeleteConversation?: (id: string) => void;
  onCreateFolder?: (name: string) => void;
}

/**
 * Conversation list with pinning, folders, day grouping, and search.
 *
 * Structure (when not searching):
 * 1. Pinned items (at top)
 * 2. Folders (collapsible, contain non-pinned items)
 * 3. Recent/loose items (day-grouped: Today, Yesterday, etc.)
 *
 * When searching: flat list of matches (structure overridden)
 */
export function ConversationList({
  conversations,
  folders,
  activeId,
  onOpenConversation,
  onRenameConversation,
  onTogglePinned: _onTogglePinned,
  onMoveToFolder: _onMoveToFolder,
  onDeleteConversation: _onDeleteConversation,
  onCreateFolder: _onCreateFolder,
}: ConversationListProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [openFolders, setOpenFolders] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);

  // Group conversations
  const pinned = useMemo(() => conversations.filter(c => c.pinned_at), [conversations]);
  const unpinned = useMemo(() => conversations.filter(c => !c.pinned_at), [conversations]);
  const loose = useMemo(() => unpinned.filter(c => !c.folder_id), [unpinned]);

  // Search
  const matches = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return null;
    return conversations.filter(c => (c.title ?? '').toLowerCase().includes(q));
  }, [searchQuery, conversations]);

  // Day grouping
  const groupByDay = (items: ConversationListItem[]): Array<[string, ConversationListItem[]]> => {
    const now = Date.now();
    const groups: Record<string, ConversationListItem[]> = {
      today: [],
      yesterday: [],
      older: [],
    };

    items.forEach(item => {
      if (!item.created_at) {
        groups.older.push(item);
        return;
      }
      const ageMs = now - item.created_at;
      const ageDays = ageMs / (1000 * 60 * 60 * 24);

      if (ageDays < 1) groups.today.push(item);
      else if (ageDays < 2) groups.yesterday.push(item);
      else groups.older.push(item);
    });

    const result: Array<[string, ConversationListItem[]]> = [];
    if (groups.today.length > 0) result.push(['Today', groups.today]);
    if (groups.yesterday.length > 0) result.push(['Yesterday', groups.yesterday]);
    if (groups.older.length > 0) result.push(['Older', groups.older]);
    return result;
  };

  const toggleFolder = (id: string) => {
    setOpenFolders(s => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full bg-[var(--nav-bg)] border-r border-on-surface/[0.07]">
      {/* Header with search and new chat button */}
      <div className="sticky top-0 z-10 bg-[var(--nav-bg)] px-3 pt-3 pb-2 space-y-2 border-b border-on-surface/[0.07]">
        <div className="flex items-center gap-2">
          <button className="px-interactive group/n flex-1 flex items-center justify-between rounded-lg border border-on-surface/[0.10] px-3 py-2 text-[13px] hover:border-on-surface/25 hover:bg-on-surface/[0.03]">
            New chat
          </button>
          <button
            aria-label="New incognito chat"
            title="Nothing is written to disk. It ends when closed."
            className="px-interactive shrink-0 rounded-lg border border-dashed border-on-surface/[0.16] p-2 text-on-surface/60 hover:border-on-surface/30 hover:text-on-surface"
          >
            <EyeOff size={14} aria-hidden="true" />
          </button>
        </div>

        {/* Search */}
        <label htmlFor="chat-search" className="sr-only">
          Search chats
        </label>
        <div className="flex items-center gap-2 rounded-lg border border-on-surface/[0.10] px-2.5 py-1.5 focus-within:border-on-surface/30">
          <Search size={12} className="shrink-0 text-on-surface/50" aria-hidden="true" />
          <input
            id="chat-search"
            type="search"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search chats"
            className="min-w-0 flex-1 bg-transparent text-[12px] outline-none placeholder:text-on-surface/50"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
              className="px-interactive shrink-0 text-on-surface/50 hover:text-on-surface"
            >
              <X size={12} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {/* Conversations list */}
      <nav className="flex-1 overflow-y-auto px-2 pb-3">
        {matches !== null ? (
          // Search results: flat list
          <>
            <p className="px-label mx-3 mb-1.5">
              {matches.length} {matches.length === 1 ? 'match' : 'matches'}
            </p>
            {matches.map(c => (
              <ConversationRow
                key={c.id}
                conversation={c}
                active={c.id === activeId}
                isEditing={c.id === editingId}
                onOpen={() => onOpenConversation(c.id)}
                onRename={(title) => {
                  if (onRenameConversation) onRenameConversation(c.id, title);
                  setEditingId(null);
                }}
                onEdit={() => setEditingId(c.id)}
              />
            ))}
            {matches.length === 0 && (
              <p className="px-3 py-4 text-xs text-on-surface/50">
                Nothing matches "{searchQuery.trim()}".
              </p>
            )}
          </>
        ) : (
          // Normal view: pinned → folders → recent
          <>
            {/* Pinned */}
            {pinned.length > 0 && (
              <>
                <p className="px-label mx-3 mb-1.5 flex items-center gap-1.5">
                  <Pin size={9} aria-hidden="true" /> Pinned
                </p>
                {pinned.map(c => (
                  <ConversationRow
                    key={c.id}
                    conversation={c}
                    active={c.id === activeId}
                    isEditing={c.id === editingId}
                    onOpen={() => onOpenConversation(c.id)}
                    onRename={(title) => {
                      if (onRenameConversation) onRenameConversation(c.id, title);
                      setEditingId(null);
                    }}
                    onEdit={() => setEditingId(c.id)}
                  />
                ))}
                <div className="h-3" />
              </>
            )}

            {/* Folders */}
            {folders.map(f => {
              const inside = unpinned.filter(c => c.folder_id === f.id);
              const open = openFolders.has(f.id);

              return (
                <div key={f.id} className="mb-1">
                  <button
                    onClick={() => toggleFolder(f.id)}
                    aria-expanded={open}
                    className="flex-1 min-w-0 text-left px-3 py-1.5 rounded-lg flex items-center gap-2 text-[12px] text-on-surface/55 hover:text-on-surface/85 hover:bg-on-surface/[0.03] transition duration-150 w-full"
                  >
                    <ChevronRight
                      size={11}
                      className={`shrink-0 opacity-60 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
                    />
                    <Folder size={12} className="shrink-0 opacity-60" />
                    <span className="truncate flex-1">{f.name}</span>
                    <span className="font-mono text-[9px] text-on-surface/50 tabular-nums">
                      {inside.length}
                    </span>
                  </button>
                  {open && (
                    <div className="pl-3">
                      {inside.map(c => (
                        <ConversationRow
                          key={c.id}
                          conversation={c}
                          active={c.id === activeId}
                          isEditing={c.id === editingId}
                          onOpen={() => onOpenConversation(c.id)}
                          onRename={(title) => {
                            if (onRenameConversation) onRenameConversation(c.id, title);
                            setEditingId(null);
                          }}
                          onEdit={() => setEditingId(c.id)}
                        />
                      ))}
                      {inside.length === 0 && (
                        <p className="px-3 py-2 text-[11px] text-on-surface/50">Empty</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Divider */}
            {folders.length > 0 && <div className="mx-3 mt-2 mb-1 border-t border-on-surface/[0.07]" />}

            {/* Recent/loose items (day-grouped) */}
            {groupByDay(loose).map(([label, rows]) => (
              <div key={label}>
                {label && (
                  <p className="px-label px-3 pt-3 pb-1.5 text-on-surface/50">{label}</p>
                )}
                {rows.map(c => (
                  <ConversationRow
                    key={c.id}
                    conversation={c}
                    active={c.id === activeId}
                    isEditing={c.id === editingId}
                    onOpen={() => onOpenConversation(c.id)}
                    onRename={(title) => {
                      if (onRenameConversation) onRenameConversation(c.id, title);
                      setEditingId(null);
                    }}
                    onEdit={() => setEditingId(c.id)}
                  />
                ))}
              </div>
            ))}

            {conversations.length === 0 && (
              <p className="px-3 py-4 text-xs text-on-surface/50">Nothing yet</p>
            )}
          </>
        )}
      </nav>
    </div>
  );
}

interface ConversationRowProps {
  conversation: ConversationListItem;
  active?: boolean;
  isEditing?: boolean;
  onOpen: () => void;
  onRename: (title: string) => void;
  onEdit: () => void;
}

/**
 * Single conversation row with click-to-open and inline edit.
 */
function ConversationRow({
  conversation: c,
  active,
  isEditing,
  onOpen,
  onRename,
  onEdit,
}: ConversationRowProps) {
  if (isEditing) {
    return (
      <input
        autoFocus
        defaultValue={c.title}
        aria-label={`Rename ${c.title}`}
        onKeyDown={e => {
          if (e.key === 'Enter') onRename((e.target as HTMLInputElement).value);
          if (e.key === 'Escape') onRename(c.title);
        }}
        onBlur={e => onRename(e.target.value)}
        className="w-full px-3 py-2 rounded-lg bg-on-surface/[0.07] border border-primary/40 text-[13px] outline-none"
      />
    );
  }

  return (
    <div className="group/c relative flex items-center rounded-lg transition-opacity duration-150">
      <button
        onClick={onOpen}
        aria-current={active ? 'page' : undefined}
        className={`flex-1 min-w-0 text-left px-3 py-2.5 rounded-lg flex items-center gap-2.5 transition duration-150 text-[13px]
          ${active ? 'bg-on-surface/[0.07] text-on-surface' : 'text-on-surface/55 hover:text-on-surface/85 hover:bg-on-surface/[0.03]'}`}
      >
        {c.incognito ? (
          <EyeOff size={13} className="shrink-0 opacity-60" />
        ) : c.pinned_at ? (
          <Pin size={12} className="shrink-0 opacity-60" />
        ) : (
          <MessageSquare size={13} className="shrink-0 opacity-60" />
        )}
        <span className="truncate flex-1">{c.title}</span>
        {(c.turn_count ?? 0) > 0 && (
          <span className="font-mono text-[9px] text-on-surface/50 tabular-nums">{c.turn_count}</span>
        )}
      </button>

      {/* Menu button (hover) */}
      <button
        onClick={onEdit}
        aria-label={`Actions for ${c.title}`}
        className="absolute right-1 opacity-0 group-hover/c:opacity-60 hover:!opacity-100 focus-visible:opacity-100 p-1 rounded transition-opacity"
      >
        <MoreHorizontal size={13} />
      </button>
    </div>
  );
}
