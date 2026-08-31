import { afterEach, describe, expect, it, vi } from 'vitest';
import { PrimnoxClient } from './client';
import { SessionStore } from './auth/session';
import { MockAuthClient } from './auth/supabase';
import { MockTransport } from './runtime/transport';
import { MockRealtimeSource } from './runtime/realtime';
import { LocalStore } from './storage/idb';
import { ModelRouter } from './model';
import type { ModelRequest, Provider, ProviderId, StreamEvent } from './model';
import { turnsOf } from './runtime/reducer';

// in-memory /vault endpoint; everything else 404s
function mockVaultServer() {
  let stored: unknown = null;
  globalThis.fetch = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const u = String(url);
    const method = init?.method ?? 'GET';
    if (u.endsWith('/vault') && method === 'GET') {
      return new Response(JSON.stringify(stored), { status: 200 });
    }
    if (u.endsWith('/vault') && method === 'PUT') {
      stored = JSON.parse(init!.body as string);
      return new Response('{}', { status: 200 });
    }
    return new Response('nope', { status: 404 });
  }) as typeof fetch;
  return { reset: () => (stored = null) };
}

function make() {
  const auth = new SessionStore(new MockAuthClient());
  const transport = new MockTransport();
  const realtime = new MockRealtimeSource();
  transport.pipeTo(realtime); // appended rows fan out like Supabase Realtime
  const store = new LocalStore();
  const client = new PrimnoxClient({
    config: { renderApiBase: 'https://render.test', githubAppSlug: 'primnox-data', systemPrompt: 'sys' },
    auth,
    transport,
    realtime,
    store,
  });
  // deterministic router
  (client as unknown as { router: ModelRouter }).router = new ModelRouter({
    providers: {
      openrouter: {
        id: 'openrouter',
        defaultBaseUrl: '',
        async *stream(_r: ModelRequest) {
          yield { type: 'token', text: 'Hel' } as StreamEvent;
          yield { type: 'token', text: 'lo' } as StreamEvent;
          yield { type: 'usage', inputTokens: 4, outputTokens: 2 } as StreamEvent;
          yield { type: 'done', finishReason: 'stop' } as StreamEvent;
        },
      } as Provider,
    } as Record<ProviderId, Provider>,
  });
  return { client, auth, transport, realtime, store };
}

afterEach(() => vi.restoreAllMocks());

describe('PrimnoxClient', () => {
  it('creates a vault, returns a recovery phrase, and reports unlocked', async () => {
    mockVaultServer();
    const { client, auth } = make();
    await client.init();
    await auth.signInWithPassword('a@b.co', 'pw');
    await client.refreshVault();
    expect(client.getSnapshot().vault).toBe('no-vault');

    const { mnemonic } = await client.createVault('correct horse battery staple');
    expect(mnemonic.trim().split(/\s+/)).toHaveLength(24);
    expect(client.getSnapshot().vault).toBe('unlocked');
  });

  it('persists the vault so a second client can unlock it', async () => {
    mockVaultServer();
    const a = make();
    await a.client.init();
    await a.auth.signInWithPassword('a@b.co', 'pw');
    await a.client.refreshVault();
    await a.client.createVault('passphrase-1');

    const b = make();
    await b.client.init();
    await b.auth.signInWithPassword('a@b.co', 'pw');
    await b.client.refreshVault();
    expect(b.client.getSnapshot().vault).toBe('locked');
    await b.client.unlock('passphrase-1');
    expect(b.client.getSnapshot().vault).toBe('unlocked');
    await expect(b.client.unlock('wrong')).rejects.toThrow();
  });

  it('stores a provider key in the vault and uses it to run a turn', async () => {
    mockVaultServer();
    const { client, auth, transport } = make();
    await client.init();
    await auth.signInWithPassword('a@b.co', 'pw');
    await client.refreshVault();
    await client.createVault('pp');

    // no key yet
    let res = await client.send('conv_1', 'hi');
    expect(res).toMatchObject({ ok: false, error: { code: 'provider_auth' } });

    await client.setProviderKey({ provider: 'openrouter', model: 'anthropic/claude-3.5-sonnet', apiKey: 'sk-or-1' });
    res = await client.send('conv_1', 'hello there');
    expect(res).toMatchObject({ ok: true, text: 'Hello' });

    // the turn log folded into the runtime store via the feed
    const [t] = turnsOf(client.runtime.getState(), 'conv_1');
    expect(t!.assistantText).toBe('Hello');
    expect(t!.status).toBe('completed');

    // a model.egress audit fact was logged (counts only)
    expect(transport.rows.some((r) => r.kind === 'model.egress')).toBe(true);
  });

  it('the provider key survives a lock / unlock cycle', async () => {
    mockVaultServer();
    const { client, auth } = make();
    await client.init();
    await auth.signInWithPassword('a@b.co', 'pw');
    await client.refreshVault();
    await client.createVault('pp');
    await client.setProviderKey({ provider: 'openrouter', model: 'm', apiKey: 'sk-or-9' });

    client.lock();
    expect(client.getSnapshot().vault).toBe('locked');
    await client.unlock('pp');
    expect(client.listProviderKeys().map((k) => k.apiKey)).toEqual(['sk-or-9']);
  });

  it('cancel() aborts an in-flight turn', async () => {
    mockVaultServer();
    const { client, auth, transport } = make();
    // a slow router that yields, waits, then yields more
    (client as unknown as { router: ModelRouter }).router = new ModelRouter({
      providers: {
        openrouter: {
          id: 'openrouter',
          defaultBaseUrl: '',
          async *stream() {
            yield { type: 'token', text: 'start ' } as StreamEvent;
            await new Promise((r) => setTimeout(r, 20));
            yield { type: 'token', text: 'end' } as StreamEvent;
          },
        } as Provider,
      } as Record<ProviderId, Provider>,
    });
    await client.init();
    await auth.signInWithPassword('a@b.co', 'pw');
    await client.refreshVault();
    await client.createVault('pp');
    await client.setProviderKey({ provider: 'openrouter', model: 'm', apiKey: 'k' });

    const p = client.send('conv_1', 'go', {
      onEvent: (e) => {
        if (e.type === 'token') {
          const [t] = turnsOf(client.runtime.getState(), 'conv_1');
          if (t) client.cancel(t.id);
        }
      },
    });
    const res = await p;
    expect(res).toMatchObject({ ok: false, cancelled: true });
    expect(transport.cancelled.length).toBe(1);
  });
});
