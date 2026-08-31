import { useSyncExternalStore } from 'react';
import type { PrimnoxClient, PrimnoxSnapshot } from '../client';
import type { SessionStore, SessionSnapshot } from '../auth/session';
import type { RuntimeState } from '../runtime/reducer';

export function usePrimnox(client: PrimnoxClient): PrimnoxSnapshot {
  return useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
}

export function useSession(auth: SessionStore): SessionSnapshot {
  return useSyncExternalStore(auth.subscribe, auth.getSnapshot, auth.getSnapshot);
}

export function useRuntime(client: PrimnoxClient): RuntimeState {
  return useSyncExternalStore(
    client.runtime.subscribe,
    client.runtime.getState,
    client.runtime.getState,
  );
}
