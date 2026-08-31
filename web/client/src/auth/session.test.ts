import { describe, expect, it } from 'vitest';
import { SessionStore } from './session';
import { MockAuthClient } from './supabase';

describe('SessionStore', () => {
  it('starts unauthenticated with no session', async () => {
    const store = new SessionStore(new MockAuthClient());
    await store.init();
    expect(store.getSnapshot().status).toBe('unauthenticated');
    await expect(store.accessToken()).rejects.toThrow(/not authenticated/);
  });

  it('signs in with a password and provides an access token', async () => {
    const store = new SessionStore(new MockAuthClient());
    await store.init();
    const notified: string[] = [];
    store.subscribe(() => notified.push(store.getSnapshot().status));

    await store.signInWithPassword('a@b.co', 'pw');
    expect(store.getSnapshot().status).toBe('authenticated');
    expect(await store.accessToken()).toMatch(/^tok_/);
    expect(notified).toContain('authenticated');
  });

  it('goes to "expired" when the session drops while authenticated', async () => {
    const client = new MockAuthClient({
      userId: 'u1',
      accessToken: 'tok_x',
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
    });
    const store = new SessionStore(client);
    await store.init();
    expect(store.getSnapshot().status).toBe('authenticated');

    client.expire();
    expect(store.getSnapshot().status).toBe('expired');
  });

  it('re-reads the client when the token is near expiry and picks up the fresher token', async () => {
    const client = new MockAuthClient({
      userId: 'u1',
      accessToken: 'tok_stale',
      expiresAt: Math.floor(Date.now() / 1000) + 1, // within the refresh skew
    });
    const store = new SessionStore(client);
    await store.init();
    client.rotate('tok_fresh'); // supabase-js refreshed silently
    expect(await store.accessToken()).toBe('tok_fresh');
    expect(store.getSnapshot().status).toBe('authenticated');
  });

  it('reports expiry when a near-expiry re-read finds no session', async () => {
    const client = new MockAuthClient({
      userId: 'u1',
      accessToken: 'tok_stale',
      expiresAt: Math.floor(Date.now() / 1000) + 1,
    });
    const store = new SessionStore(client);
    await store.init();
    client.dropSilently(); // no onChange fires
    await expect(store.accessToken()).rejects.toThrow(/expired/);
    expect(store.getSnapshot().status).toBe('expired');
  });

  it('signs out back to unauthenticated', async () => {
    const store = new SessionStore(new MockAuthClient());
    await store.init();
    await store.signInWithPassword('a@b.co', 'pw');
    await store.signOut();
    expect(store.getSnapshot().status).toBe('unauthenticated');
  });
});
