import { describe, expect, it } from 'vitest';
import { createVault } from '../crypto/vault';
import { ProviderKeyStore } from './keys';

const FAST = { alg: 'argon2id', m: 1024, t: 1, p: 1 } as const;

describe('ProviderKeyStore', () => {
  it('seals and unseals under the DEK, bound by AAD', async () => {
    const { dek } = await createVault('p', FAST);
    const store = new ProviderKeyStore();
    store.set({ provider: 'openrouter', model: 'anthropic/claude-3.5-sonnet', apiKey: 'sk-or-123' });
    store.set({ provider: 'groq', model: 'llama-3.1-70b', apiKey: 'gsk_456', label: 'fast' });

    const sealed = await store.seal(dek);
    const reopened = await ProviderKeyStore.unseal(dek, sealed);

    expect(reopened.list()).toHaveLength(2);
    expect(reopened.get('openrouter')?.apiKey).toBe('sk-or-123');
    expect(reopened.profile('groq')).toEqual({
      provider: 'groq',
      model: 'llama-3.1-70b',
      apiKey: 'gsk_456',
    });
  });

  it('a wrong DEK cannot unseal the key bundle', async () => {
    const { dek } = await createVault('p', FAST);
    const { dek: other } = await createVault('other', FAST);
    const store = new ProviderKeyStore();
    store.set({ provider: 'anthropic', model: 'claude', apiKey: 'sk-ant' });
    const sealed = await store.seal(dek);
    await expect(ProviderKeyStore.unseal(other, sealed)).rejects.toThrow();
  });

  it('replaces the active entry per provider and can remove one', () => {
    const store = new ProviderKeyStore();
    store.set({ provider: 'gemini', model: 'gemini-1.5-flash', apiKey: 'a' });
    store.set({ provider: 'gemini', model: 'gemini-1.5-pro', apiKey: 'b' });
    expect(store.get('gemini')?.model).toBe('gemini-1.5-pro');
    store.remove('gemini');
    expect(store.has('gemini')).toBe(false);
    expect(store.profile('gemini')).toBeUndefined();
  });
});
