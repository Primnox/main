/* Wire the real dependency graph from config. The UI calls `createPrimnox()`
   once and holds the returned client. */

import { config, isConfigured } from './config';
import { PrimnoxClient } from './client';
import { SessionStore } from './auth/session';
import { SupabaseAuthClient } from './auth/supabase';
import { HttpTransport } from './runtime/transport';
import { OfflineAwareTransport } from './runtime/offline';
import { SupabaseRealtimeSource } from './runtime/realtime-supabase';
import { LocalStore } from './storage/idb';

const SYSTEM_PROMPT =
  'You are Primnox, a personal AI environment. Be plain, specific, and ' +
  'non-euphemistic. When something fails, say what happened and what was lost.';

export function createPrimnox(): PrimnoxClient {
  if (!isConfigured()) {
    throw new Error(
      'Primnox Web is not configured. Set VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, ' +
        'and VITE_RENDER_API_BASE (see .env.example).',
    );
  }

  const auth = new SessionStore(new SupabaseAuthClient());
  const store = new LocalStore();
  const http = new HttpTransport(config.renderApiBase, auth.accessToken);
  const transport = new OfflineAwareTransport(http, store);

  return new PrimnoxClient({
    config: {
      renderApiBase: config.renderApiBase,
      githubAppSlug: config.githubAppSlug,
      systemPrompt: SYSTEM_PROMPT,
    },
    auth,
    transport,
    realtime: new SupabaseRealtimeSource(),
    store,
  });
}

export { config, isConfigured } from './config';
