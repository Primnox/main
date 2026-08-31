import { describe, expect, it } from 'vitest';
import { openString, sealString } from './aead';
import {
  addRecovery,
  changePassphrase,
  createVault,
  resetPassphraseWithMnemonic,
  unlockVault,
  unlockWithMnemonic,
} from './vault';
import { isValidMnemonic } from './mnemonic';

// Fast KDF for tests — real defaults (19 MiB, t=2) are exercised in one case below.
const FAST = { alg: 'argon2id', m: 1024, t: 1, p: 1 } as const;

const round = async (dek: CryptoKey, s: string, aad = 'test:1') =>
  openString(dek, await sealString(dek, s, aad), aad);

describe('vault', () => {
  it('creates a vault and round-trips content under the DEK', async () => {
    const { dek } = await createVault('correct horse battery staple', FAST);
    expect(await round(dek, 'hello world')).toBe('hello world');
  });

  it('unlocks with the right passphrase and rejects the wrong one', async () => {
    const { blob } = await createVault('right-passphrase', FAST);
    const dek = await unlockVault('right-passphrase', blob);
    expect(await round(dek, 'secret')).toBe('secret');
    await expect(unlockVault('WRONG-passphrase', blob)).rejects.toThrow(/wrong passphrase|corrupt/i);
  });

  it('a DEK from unlock decrypts data sealed by the DEK from create', async () => {
    const { dek: dek1, blob } = await createVault('p', FAST);
    const sealed = await sealString(dek1, 'persisted', 'msg:m1/body');
    const dek2 = await unlockVault('p', blob);
    expect(await openString(dek2, sealed, 'msg:m1/body')).toBe('persisted');
  });

  it('rejects decryption when the AAD context does not match', async () => {
    const { dek } = await createVault('p', FAST);
    const sealed = await sealString(dek, 'x', 'msg:m1/body');
    await expect(openString(dek, sealed, 'msg:m2/body')).rejects.toThrow();
  });

  it('changePassphrase re-wraps without touching data', async () => {
    const { dek: dek1, blob: b1 } = await createVault('old-pass', FAST);
    const sealed = await sealString(dek1, 'unchanged', 'x');

    const b2 = await changePassphrase('old-pass', 'new-pass', b1, FAST);
    expect(b2.keyVersion).toBe(2);
    await expect(unlockVault('old-pass', b2)).rejects.toThrow();

    const dek2 = await unlockVault('new-pass', b2);
    expect(await openString(dek2, sealed, 'x')).toBe('unchanged');
  });

  it('changePassphrase rejects a wrong old passphrase', async () => {
    const { blob } = await createVault('old', FAST);
    await expect(changePassphrase('not-old', 'new', blob, FAST)).rejects.toThrow();
  });

  describe('recovery', () => {
    it('adds a valid 24-word phrase and unlocks with it', async () => {
      const { dek: dek1, blob: b1 } = await createVault('pass', FAST);
      const sealed = await sealString(dek1, 'recoverable', 'x');

      const { blob: b2, mnemonic } = await addRecovery('pass', b1);
      expect(mnemonic.trim().split(/\s+/)).toHaveLength(24);
      expect(isValidMnemonic(mnemonic)).toBe(true);

      const dek2 = await unlockWithMnemonic(mnemonic, b2);
      expect(await openString(dek2, sealed, 'x')).toBe('recoverable');
    });

    it('rejects a bad phrase', async () => {
      const { blob } = await createVault('pass', FAST);
      const { blob: withRec } = await addRecovery('pass', blob);
      await expect(unlockWithMnemonic('all your base are belong to us', withRec)).rejects.toThrow();
    });

    it('recovery survives a passphrase change', async () => {
      const { dek: dek1, blob: b1 } = await createVault('p1', FAST);
      const sealed = await sealString(dek1, 'still here', 'x');
      const { blob: b2, mnemonic } = await addRecovery('p1', b1);
      const b3 = await changePassphrase('p1', 'p2', b2, FAST);

      const dek = await unlockWithMnemonic(mnemonic, b3);
      expect(await openString(dek, sealed, 'x')).toBe('still here');
    });

    it('resets the passphrase via the mnemonic', async () => {
      const { dek: dek1, blob: b1 } = await createVault('forgotten', FAST);
      const sealed = await sealString(dek1, 'kept', 'x');
      const { blob: b2, mnemonic } = await addRecovery('forgotten', b1);

      const b3 = await resetPassphraseWithMnemonic(mnemonic, 'brand-new', b2, FAST);
      await expect(unlockVault('forgotten', b3)).rejects.toThrow();
      const dek = await unlockVault('brand-new', b3);
      expect(await openString(dek, sealed, 'x')).toBe('kept');
    });
  });

  it('works with the real default KDF cost (slow)', async () => {
    const { dek, blob } = await createVault('production-grade passphrase');
    const dek2 = await unlockVault('production-grade passphrase', blob);
    const sealed = await sealString(dek, 'default-cost', 'x');
    expect(await openString(dek2, sealed, 'x')).toBe('default-cost');
  }, 20_000);
});
