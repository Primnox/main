# backend/local_vault.py
"""
Primnox local vault — 12-word seed-phrase encryption for data at rest.

Same scheme as backup_manager's cloud backups, applied to the local
memory.db (and optionally chat.db) so the files on disk are useless
without the user's 12-word mnemonic.

Mnemonic (12 BIP-39 words, standard English wordlist bundled at
website/wordlist.txt)
  → PBKDF2-SHA512(mnemonic, b"primnox-local", 600_000 iter) → 32-byte AES-256 key
  → key cached in OS keychain (keyring) so the app can unlock itself on
    normal startup without re-prompting every time
  → AES-256-GCM(gzip(memory.db bytes)) → memory.db.vault

.vault binary format:
  Offset  Size   Field
  ──────────────────────────────────────────
  0       4      Magic  b"PRNL"
  4       1      Version 0x01
  5       12     GCM nonce (random per encryption)
  17      N      AES-256-GCM ciphertext (gzip-compressed payload)
                 ↑ last 16 bytes of ciphertext are the GCM auth tag

The plaintext memory.db only ever exists on disk while the app is
unlocked. On clean shutdown it is re-encrypted to memory.db.vault and
the plaintext copy is securely removed.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from logger import get_logger

log = get_logger("local_vault")

MAGIC = b"PRNL"
VERSION = 0x01

_KEYRING_SERVICE = "primnox-local"
_KEYRING_USER = "vault-key"

_WORDLIST_PATH = Path(__file__).parent.parent / "website" / "wordlist.txt"


# ── Wordlist ─────────────────────────────────────────────────────────────────

def load_wordlist() -> list[str]:
    """Load the bundled 2048-word BIP-39 English wordlist."""
    try:
        words = _WORDLIST_PATH.read_text(encoding="utf-8").split()
        if len(words) != 2048:
            raise ValueError(f"wordlist has {len(words)} entries, expected 2048")
        return words
    except Exception as e:
        log.error(f"Failed to load wordlist: {e}")
        raise


# ── Key derivation (mirrors backup_manager, distinct salt) ─────────────────────

def derive_key(mnemonic: str) -> bytes:
    """
    PBKDF2-SHA512(mnemonic, 'primnox-local', 600_000 iterations) → 32-byte AES-256 key.
    Deterministic: same mnemonic always gives the same key.
    Uses a different salt than backup_manager so a backup mnemonic and a
    local-vault mnemonic can never collide to the same key.

    Whitespace is normalized to match validate_mnemonic()'s tolerance for
    stray double-spaces/tabs, so a typo doesn't silently derive a different
    key and lock the user out.
    """
    normalized = " ".join(mnemonic.strip().lower().split())
    return hashlib.pbkdf2_hmac(
        "sha512",
        normalized.encode("utf-8"),
        b"primnox-local",
        600_000,
        dklen=32,
    )


def generate_mnemonic() -> str:
    """Generate a fresh cryptographically secure 12-word BIP-39 mnemonic."""
    from backup_manager import generate_mnemonic as _gen
    return _gen(load_wordlist())


def validate_mnemonic(mnemonic: str) -> tuple[bool, str]:
    """BIP-39 checksum validation of a 12-word mnemonic."""
    from backup_manager import validate_mnemonic as _validate
    return _validate(mnemonic, load_wordlist())


# ── OS keychain helpers ─────────────────────────────────────────────────────

def _keychain_store(key: bytes) -> None:
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, key.hex())
    except Exception as e:
        log.warning(f"Could not store vault key in keychain: {e}")


def _keychain_load() -> Optional[bytes]:
    try:
        import keyring
        val = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        return bytes.fromhex(val) if val else None
    except Exception:
        return None


def _keychain_clear() -> None:
    try:
        import keyring
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
    except Exception:
        pass


# ── File encryption helpers ─────────────────────────────────────────────────

def _encrypt_bytes(data: bytes, key: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    compressed = gzip.compress(data)
    ct = AESGCM(key).encrypt(nonce, compressed, None)
    return MAGIC + bytes([VERSION]) + nonce + ct


def _decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    if blob[:4] != MAGIC:
        raise ValueError("Not a Primnox vault file (bad magic)")
    if blob[4] != VERSION:
        raise ValueError(f"Unsupported vault version: {blob[4]}")
    nonce = blob[5:17]
    ct = blob[17:]
    compressed = AESGCM(key).decrypt(nonce, ct, None)
    return gzip.decompress(compressed)


def _secure_delete(path: Path) -> None:
    """Best-effort overwrite-then-delete of a plaintext file."""
    try:
        size = path.stat().st_size
        with open(path, "wb") as f:
            f.write(secrets.token_bytes(min(size, 1024 * 1024)))
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# ── Vault lifecycle ──────────────────────────────────────────────────────────

def vault_path(db_path: Path) -> Path:
    return db_path.with_suffix(db_path.suffix + ".vault")


def is_enabled(db_path: Path) -> bool:
    """A vault is 'enabled' for this DB if a .vault file exists for it."""
    return vault_path(db_path).exists()


def is_locked(db_path: Path) -> bool:
    """Locked = vault file exists but no plaintext DB is present."""
    return is_enabled(db_path) and not db_path.exists()


def setup_vault(db_path: Path, mnemonic: Optional[str] = None) -> str:
    """
    Enable the vault for db_path.

    - If mnemonic is None, a fresh one is generated and returned (the
      caller MUST show this to the user — it cannot be recovered later).
    - If mnemonic is provided, it must be a valid 12-word phrase.

    Encrypts the current plaintext db (if any) into db_path.vault,
    caches the derived key in the OS keychain, and leaves the plaintext
    db in place (so the running app keeps working without a restart).
    """
    if mnemonic is None:
        mnemonic = generate_mnemonic()
    else:
        ok, err = validate_mnemonic(mnemonic)
        if not ok:
            raise ValueError(f"Invalid mnemonic: {err}")

    key = derive_key(mnemonic)

    if db_path.exists():
        data = db_path.read_bytes()
        blob = _encrypt_bytes(data, key)
        vault_path(db_path).write_bytes(blob)
    else:
        # Nothing to encrypt yet — create an empty encrypted placeholder
        vault_path(db_path).write_bytes(_encrypt_bytes(b"", key))

    _keychain_store(key)
    log.info(f"Local vault enabled for {db_path.name}")
    return mnemonic


def unlock_vault(db_path: Path, mnemonic: Optional[str] = None) -> None:
    """
    Decrypt db_path.vault → db_path (plaintext) using either the supplied
    mnemonic or the key cached in the OS keychain.
    """
    vp = vault_path(db_path)
    if not vp.exists():
        raise FileNotFoundError(f"No vault found at {vp}")

    if mnemonic:
        ok, err = validate_mnemonic(mnemonic)
        if not ok:
            raise ValueError(f"Invalid mnemonic: {err}")
        key = derive_key(mnemonic)
    else:
        key = _keychain_load()
        if key is None:
            raise PermissionError("Vault is locked and no key in keychain — mnemonic required")

    blob = vp.read_bytes()
    try:
        data = _decrypt_bytes(blob, key)
    except Exception:
        raise PermissionError("Incorrect mnemonic — could not decrypt vault")

    if data:
        db_path.write_bytes(data)
    if mnemonic:
        _keychain_store(key)
    log.info(f"Local vault unlocked for {db_path.name}")


def lock_vault(db_path: Path, key: Optional[bytes] = None) -> None:
    """
    Re-encrypt the current plaintext db_path → db_path.vault and securely
    delete the plaintext copy. Call on shutdown.
    """
    if not db_path.exists():
        return
    if key is None:
        key = _keychain_load()
    if key is None:
        log.warning("lock_vault: no key available, skipping re-encrypt (plaintext left as-is)")
        return

    data = db_path.read_bytes()
    blob = _encrypt_bytes(data, key)
    vault_path(db_path).write_bytes(blob)
    _secure_delete(db_path)
    log.info(f"Local vault locked for {db_path.name}")


def sync_vault(db_path: Path) -> None:
    """
    Re-encrypt db_path → db_path.vault WITHOUT deleting the plaintext.
    Useful for periodic snapshots while the app keeps running.
    """
    if not db_path.exists() or not is_enabled(db_path):
        return
    key = _keychain_load()
    if key is None:
        return
    data = db_path.read_bytes()
    vault_path(db_path).write_bytes(_encrypt_bytes(data, key))


def disable_vault(db_path: Path) -> None:
    """Decrypt (if locked) and remove the .vault file + keychain entry."""
    if is_locked(db_path):
        unlock_vault(db_path)
    vp = vault_path(db_path)
    if vp.exists():
        vp.unlink()
    _keychain_clear()
    log.info(f"Local vault disabled for {db_path.name}")
