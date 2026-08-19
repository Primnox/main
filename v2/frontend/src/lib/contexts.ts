import { createContext } from 'react';

/* Opening a file is available wherever a file is mentioned — inside an
   execution, on a turn, in the rail — and those are three different depths of
   the tree. A context beats threading a callback through every one of them. */
export type OpenAsset = (asset: { id: string; name: string }) => void;
export const ViewerContext = createContext<OpenAsset>(() => {});

/* ChatRow lives outside App on purpose. A component defined inside another is
   a NEW component type on every render, so React remounts it — which throws
   away the focus and caret of the rename field the moment you type. The
   handlers reach it through a context instead. */
export type ChatActions = {
  activeId: string | null;
  folders: any[];
  editingId: string | null;
  menuId: string | null;
  draggingId: string | null;
  setDragging: (id: string | null) => void;
  open: (id: string) => void;
  setMenu: (id: string | null) => void;
  beginRename: (id: string) => void;
  commitRename: (id: string, title: string) => void;
  togglePin: (c: any) => void;
  move: (id: string, folderId: string | null) => void;
  archive: (id: string) => void;
  remove: (c: any) => void;
};
export const ChatsContext = createContext<ChatActions | null>(null);

