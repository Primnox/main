/* Crypto core — CRS/1.0-W §5.

   Everything the browser needs to hold the keys and turn plaintext into the
   ciphertext that leaves the device. No key material is ever serialized or
   sent; the DEK and KEK exist only as non-extractable CryptoKeys for the
   session. */

export { bytesToB64, b64ToBytes, utf8, fromUtf8, randomBytes, wipe } from './bytes';
export { DEFAULT_KDF, newKdfParams, deriveKek } from './kdf';
export type { KdfParams, KdfCost } from './kdf';
export { seal, open, sealString, openString, sealJSON, openJSON, isSealed } from './aead';
export type { Sealed } from './aead';
export { newMnemonic, isValidMnemonic, normalizeMnemonic } from './mnemonic';
export {
  createVault,
  unlockVault,
  changePassphrase,
  addRecovery,
  hasRecovery,
  unlockWithMnemonic,
  resetPassphraseWithMnemonic,
} from './vault';
export type { VaultBlob } from './vault';
