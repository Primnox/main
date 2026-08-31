/* Conversation metadata for the web shell.
 *
 * The runtime knows a conversation only as an id with turns under it — CRS/1.0-W
 * has no `conversation.renamed` event, and inventing one would put a title in
 * the sealed log for something that is purely a local label. So titles, pins and
 * archive state live here, in localStorage, next to the tab that shows them.
 *
 * The consequence is honest and worth stating: this metadata does NOT sync
 * across devices. A conversation you renamed on your laptop is still "New Chat"
 * on your phone, while its turns — the part that is actually encrypted and
 * replicated — are identical on both.
 */

/* `created_at`, not `createdAt`: groupByDay and ChatRow were ported verbatim
   from desktop and read the server's snake_case conversation shape. Matching it
   here keeps both of them unmodified. */
export interface ConversationMeta {
  id: string;
  title: string;
  pinned: boolean;
  archived: boolean;
  /** epoch ms, for day-grouping the list */
  created_at: number;
}

const KEY = 'primnox2.web.conversations';

export function loadMeta(): Record<string, ConversationMeta> {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object') return {};
    return parsed as Record<string, ConversationMeta>;
  } catch {
    // Private mode denies localStorage, and a bad JSON blob must not take the
    // app down — an unnamed list is recoverable, a white screen is not.
    return {};
  }
}

export function saveMeta(all: Record<string, ConversationMeta>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch { /* private mode */ }
}

/** A conversation's first user message, trimmed to something a row can hold.
    Desktop titles a chat server-side; this is the same idea done locally. */
export function titleFrom(firstUserText: string | null | undefined): string {
  const t = (firstUserText ?? '').trim().replace(/\s+/g, ' ');
  if (!t) return 'New Chat';
  return t.length > 48 ? `${t.slice(0, 47)}…` : t;
}
