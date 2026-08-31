/* Offline mock wiring — the whole UI runs with no Supabase / Render / GitHub.

   Used when VITE_MOCK is set, or as a fallback when the app is not configured.
   The vault still persists to IndexedDB, so a reload keeps you signed in and
   only needs the passphrase. The "echo" model streams a canned reply. */

import { PrimnoxClient } from '../client';
import { SessionStore } from '../auth/session';
import { MockAuthClient, type MockAuthClient as _MA } from '../auth/supabase';
import { MockTransport } from '../runtime/transport';
import { MockRealtimeSource } from '../runtime/realtime';
import { OfflineAwareTransport } from '../runtime/offline';
import { LocalStore } from '../storage/idb';
import { ModelRouter } from '../model';
import type { ModelRequest, Provider, ProviderId, StreamEvent } from '../model';

const echoProvider: Provider = {
  id: 'openrouter',
  defaultBaseUrl: '',
  async *stream(req: ModelRequest): AsyncGenerator<StreamEvent> {
    const last = [...req.messages].reverse().find((m) => m.role === 'user')?.content ?? '';
    const reply =
      `Echo (mock model). You said: "${last.slice(0, 200)}". ` +
      `Wire a real provider key in Settings to talk to OpenRouter / Anthropic / Gemini / Groq.`;
    for (const word of reply.split(/(\s+)/)) {
      await new Promise((r) => setTimeout(r, 12));
      yield { type: 'token', text: word };
    }
    yield { type: 'usage', inputTokens: Math.ceil(last.length / 4), outputTokens: Math.ceil(reply.length / 4) };
    yield { type: 'done', finishReason: 'stop' };
  },
};

export function createMockPrimnox(): PrimnoxClient {
  const authClient: _MA = new MockAuthClient();
  const auth = new SessionStore(authClient);
  const store = new LocalStore();

  const mock = new MockTransport();
  const realtime = new MockRealtimeSource();
  mock.pipeTo(realtime);
  const transport = new OfflineAwareTransport(mock, store);

  // in-memory /vault so createVault / unlock work across the session
  let vaultBlob: unknown = null;
  const realFetch = globalThis.fetch;
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith('/vault')) {
      const method = init?.method ?? 'GET';
      if (method === 'GET') return new Response(JSON.stringify(vaultBlob), { status: 200 });
      if (method === 'PUT') {
        vaultBlob = JSON.parse(init!.body as string);
        return new Response('{}', { status: 200 });
      }
    }
    if (u.endsWith('/github/status')) {
      return new Response(JSON.stringify({ status: 'disconnected', repo_full_name: null }), { status: 200 });
    }
    return realFetch(url, init);
  }) as typeof fetch;

  const client = new PrimnoxClient({
    config: { renderApiBase: 'mock://render', githubAppSlug: 'primnox-data', systemPrompt: 'mock' },
    auth,
    transport,
    realtime,
    store,
  });
  (client as unknown as { router: ModelRouter }).router = new ModelRouter({
    providers: { openrouter: echoProvider } as Record<ProviderId, Provider>,
  });
  return client;
}
