import { useContext, useRef, useState } from 'react';
import { Archive, EyeOff, Folder, MessageSquare, MoreHorizontal, Pencil, Pin, Trash2 } from 'lucide-react';
import { ChatsContext } from '../lib/contexts';
import { MenuItem } from './MenuItem';
import { RowMenu } from './RowMenu';

export function ChatRow({ c }: { c: any }) {
  const a = useContext(ChatsContext)!;
  const active = c.id === a.activeId;
  const editing = a.editingId === c.id;
  const menuBtn = useRef<HTMLButtonElement>(null);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  // Two-step delete, same reason as the folder row: window.confirm() is
  // silently swallowed in several embedded webviews — no dialog, no error,
  // just a dead button. A second click inside the menu itself replaces it.
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  if (editing) {
    return (
      <input autoFocus defaultValue={c.title}
        aria-label={`Rename ${c.title}`}
        onKeyDown={e => {
          if (e.key === 'Enter') a.commitRename(c.id, (e.target as HTMLInputElement).value);
          if (e.key === 'Escape') a.commitRename(c.id, c.title);
        }}
        onBlur={e => a.commitRename(c.id, e.target.value)}
        className="w-full px-3 py-2 rounded-lg bg-on-surface/[0.07] border border-primary/40 text-[13px] outline-none" />
    );
  }

  const openMenuAt = (x: number, y: number) => {
    // A zero-size rect at the cursor. RowMenu positions against a rect, so the
    // pointer becomes the anchor and the menu opens where the click happened
    // rather than beside a button the user never touched.
    setAnchor(new DOMRect(x, y, 0, 0));
    a.setMenu(c.id);
  };

  // Every path that closes the menu goes through here, so the pending
  // "delete?" state never survives into the next time it opens.
  const closeMenu = () => { setAnchor(null); a.setMenu(null); setConfirmingDelete(false); };

  return (
    <div
      className={`relative group/c flex items-center rounded-lg transition-opacity duration-150
                  ${a.draggingId === c.id ? 'opacity-40' : ''}`}
      // Incognito conversations are never written to disk, so they have no
      // folder to be moved into — dragging one would promise a placement that
      // cannot survive the session.
      draggable={!c.incognito}
      onDragStart={e => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', c.id);
        a.setDragging(c.id);
      }}
      onDragEnd={() => a.setDragging(null)}
      onContextMenu={e => { e.preventDefault(); openMenuAt(e.clientX, e.clientY); }}>
      <button onClick={() => a.open(c.id)}
        aria-current={active ? 'page' : undefined}
        className={`flex-1 min-w-0 text-left px-3 py-2.5 rounded-lg flex items-center gap-2.5 transition duration-150 text-[13px]
          ${active ? 'bg-on-surface/[0.07] text-on-surface' : 'text-on-surface/55 hover:text-on-surface/85 hover:bg-on-surface/[0.03]'}`}>
        {c.incognito
          ? <EyeOff size={13} className="shrink-0 opacity-60" />
          : c.pinned_at
            ? <Pin size={12} className="shrink-0 opacity-60" />
            : <MessageSquare size={13} className="shrink-0 opacity-60" />}
        <span className="truncate flex-1">{c.title}</span>
        {c.turn_count > 0 && (
          <span className="font-mono text-[9px] text-on-surface/50 tabular-nums">{c.turn_count}</span>
        )}
      </button>

      <button ref={menuBtn}
        onClick={() => {
          const open = a.menuId === c.id;
          if (open) { closeMenu(); return; }
          const r = menuBtn.current!.getBoundingClientRect();
          openMenuAt(r.right, r.bottom);
        }}
        aria-label={`Actions for ${c.title}`} aria-expanded={a.menuId === c.id}
        className="absolute right-1 opacity-0 group-hover/c:opacity-60 hover:!opacity-100 focus-visible:opacity-100 p-1 rounded transition-opacity bg-[var(--nav-bg)]">
        <MoreHorizontal size={13} />
      </button>

      {a.menuId === c.id && anchor && (
        <RowMenu anchor={anchor} onClose={closeMenu}>
            <MenuItem icon={<Pencil size={12} />} onClick={() => a.beginRename(c.id)}>Rename</MenuItem>
            {!c.incognito && (
              <MenuItem icon={<Pin size={12} />} onClick={() => a.togglePin(c)}>
                {c.pinned_at ? 'Unpin' : 'Pin'}
              </MenuItem>
            )}
            {!c.incognito && a.folders.length > 0 && (
              <>
                <p className="px-label px-3 pt-2 pb-1">Move to</p>
                {a.folders.map(f => (
                  <MenuItem key={f.id} icon={<Folder size={12} />}
                    onClick={() => a.move(c.id, c.folder_id === f.id ? null : f.id)}>
                    {f.name}{c.folder_id === f.id ? ' ·  remove' : ''}
                  </MenuItem>
                ))}
              </>
            )}
            <div className="my-1 h-px bg-on-surface/[0.08]" />
            {!c.incognito && (
              <MenuItem icon={<Archive size={12} />} onClick={() => a.archive(c.id)}>
                Archive
              </MenuItem>
            )}
            {confirmingDelete ? (
              <MenuItem icon={<Trash2 size={12} />} danger onClick={() => a.remove(c)}>
                Confirm delete — its messages go with it
              </MenuItem>
            ) : (
              <MenuItem icon={<Trash2 size={12} />} danger onClick={() => setConfirmingDelete(true)}>
                Delete permanently
              </MenuItem>
            )}
        </RowMenu>
      )}
    </div>
  );
}

