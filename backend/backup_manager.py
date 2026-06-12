# backend/backup_manager.py
"""
Primnox encrypted cloud backup.

Mnemonic (12 BIP-39 words, custom Primnox wordlist)
  → PBKDF2-SHA512(mnemonic, b"primnox-backup", 600_000 iter) → 32-byte AES-256 key
  → stored in OS keychain (keyring) for background sync
  → AES-256-GCM( gzip( SQLite dump of memory.db + chat.db + settings ) ) → .prx blob
  → upload to configured cloud provider

.prx binary format:
  Offset  Size   Field
  ──────────────────────────────────────────
  0       4      Magic  b"PRNX"
  4       1      Version 0x01
  5       12     GCM nonce (random per backup)
  17      N      AES-256-GCM ciphertext  (gzip-compressed payload)
                 ↑ last 16 bytes of ciphertext are the GCM auth tag (appended by AESGCM)
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import secrets
import sqlite3
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from logger import get_logger

log = get_logger("backup")

# ── Constants ──────────────────────────────────────────────────────────────────
MAGIC              = b"PRNX"
VERSION            = 0x01
_KEYRING_SERVICE   = "primnox-backup"
_KEYRING_USER      = "aes-key"
_WORDLIST_CACHE_KEY = "backup_wordlist"

# ── Key derivation ─────────────────────────────────────────────────────────────

def derive_key(mnemonic: str) -> bytes:
    """
    PBKDF2-SHA512(mnemonic, 'primnox-backup', 600_000 iterations) → 32-byte AES-256 key.
    Deterministic: same mnemonic always gives the same key.
    """
    return hashlib.pbkdf2_hmac(
        "sha512",
        mnemonic.strip().lower().encode("utf-8"),
        b"primnox-backup",
        600_000,
        dklen=32,
    )


def validate_mnemonic(mnemonic: str, wordlist: list[str]) -> tuple[bool, str]:
    """
    BIP-39-style checksum validation against a 2048-word custom wordlist.
    Returns (valid: bool, error_message: str).
    """
    words = mnemonic.strip().lower().split()
    if len(words) != 12:
        return False, f"Expected 12 words, got {len(words)}"

    if len(wordlist) != 2048:
        return False, "Wordlist must contain exactly 2048 words"

    unknown = [w for w in words if w not in wordlist]
    if unknown:
        return False, f"Unknown words: {', '.join(unknown)}"

    try:
        # BIP-39: 12 words × 11 bits = 132 bits = 128-bit entropy + 4-bit checksum
        word_to_idx = {}
        for i, w in enumerate(wordlist):
            if w in word_to_idx:
                return False, f"Wordlist has duplicate entry: '{w}'"
            word_to_idx[w] = i
        indices = [word_to_idx[w] for w in words]
        bits = "".join(f"{i:011b}" for i in indices)
        entropy_bits = bits[:128]
        checksum_bits = bits[128:]          # 4 bits

        entropy_bytes = int(entropy_bits, 2).to_bytes(16, "big")
        digest = hashlib.sha256(entropy_bytes).digest()
        expected_checksum = f"{digest[0]:08b}"[:4]

        if checksum_bits != expected_checksum:
            return False, "Checksum invalid — check for typos"
    except Exception as e:
        return False, f"Validation error: {e}"

    return True, ""


def generate_mnemonic(wordlist: list[str]) -> str:
    """
    Generate a cryptographically secure 12-word mnemonic from a 2048-word list.
    Follows BIP-39: 128 random bits + 4-bit SHA256 checksum = 12 × 11-bit indices.
    """
    if len(wordlist) != 2048:
        raise ValueError("Wordlist must contain exactly 2048 words")

    entropy = secrets.token_bytes(16)                       # 128 bits
    digest = hashlib.sha256(entropy).digest()

    entropy_bits = "".join(f"{b:08b}" for b in entropy)    # 128 bits
    checksum_bits = f"{digest[0]:08b}"[:4]                  # 4 bits
    all_bits = entropy_bits + checksum_bits                  # 132 bits

    indices = [int(all_bits[i*11:(i+1)*11], 2) for i in range(12)]
    return " ".join(wordlist[i] for i in indices)


# ── OS keychain helpers ────────────────────────────────────────────────────────

def _keychain_store(key: bytes) -> None:
    """Persist AES key hex in OS keychain for background sync."""
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, key.hex())
        log.debug("Backup key stored in keychain")
    except Exception as e:
        log.warning(f"Could not store key in keychain: {e}")


def _keychain_load() -> Optional[bytes]:
    """Load AES key from OS keychain. Returns None if not found."""
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


# ── SQLite hot-copy ────────────────────────────────────────────────────────────

def _safe_copy_db(src_path: Path) -> bytes:
    """
    Hot-copy a SQLite DB (WAL-safe) and return its raw bytes.
    Uses SQLite's built-in backup API — no locks held on the source.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    src = dst = None
    try:
        src = sqlite3.connect(str(src_path))
        dst = sqlite3.connect(str(tmp_path))
        src.backup(dst)
        src.close(); src = None
        dst.close(); dst = None   # must close before unlink on Windows
        return tmp_path.read_bytes()
    finally:
        if src is not None: src.close()
        if dst is not None: dst.close()
        tmp_path.unlink(missing_ok=True)


# ── Backup payload builder ─────────────────────────────────────────────────────

def _build_payload() -> bytes:
    """
    Gather memory.db, chat.db, and settings.json into a gzip-compressed JSON blob.
    Returns gzip bytes ready for AES encryption.
    """
    from memory import DB_PATH as MEMORY_DB
    from chat_manager import DB_FILE as CHAT_DB
    from settings_manager import get_appdata_dir, load_settings

    payload: dict = {
        "version":    "1",
        "created_at": datetime.now().isoformat(),
        "databases":  {},
        "settings":   {},
    }

    for name, path in [("memory.db", Path(MEMORY_DB)), ("chat.db", Path(CHAT_DB))]:
        if path.exists():
            raw = _safe_copy_db(path)
            payload["databases"][name] = raw.hex()
            log.debug(f"Snapshot {name}: {len(raw):,} bytes")
        else:
            log.warning(f"DB not found, skipping: {path}")

    # Include settings but strip sensitive cloud credentials from the backup
    # (user re-enters those when restoring — only the mnemonic unlocks the data)
    s = load_settings()
    s.pop("backup_providers", None)   # contains cloud credentials — omit
    s.pop("backup_wordlist", None)    # large list, not needed in backup; omit so setdefault fires on restore
    payload["settings"] = s

    raw_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw_json, compresslevel=6)


# ── Encrypt / decrypt ──────────────────────────────────────────────────────────

def encrypt_backup(key: bytes, data: bytes) -> bytes:
    """Encrypt compressed payload → .prx bytes."""
    nonce = secrets.token_bytes(12)          # 96-bit random nonce
    aes   = AESGCM(key)
    ct    = aes.encrypt(nonce, data, None)   # GCM auth tag appended by AESGCM
    return MAGIC + bytes([VERSION]) + nonce + ct


def decrypt_backup(key: bytes, prx: bytes) -> bytes:
    """
    Decrypt .prx bytes → compressed payload.
    Raises ValueError on bad magic/version.
    Raises cryptography.exceptions.InvalidTag on wrong key or tampered data.
    """
    if len(prx) < 33:
        raise ValueError("File too small to be a valid .prx backup")
    if prx[:4] != MAGIC:
        raise ValueError("Not a Primnox backup file (.prx)")
    if prx[4] != VERSION:
        raise ValueError(f"Unsupported backup version: {prx[4]:#04x}")

    nonce = prx[5:17]
    ct    = prx[17:]
    return AESGCM(key).decrypt(nonce, ct, None)


# ── Restore ────────────────────────────────────────────────────────────────────

def _restore_payload(compressed: bytes) -> None:
    """Decompress and restore databases + settings from a backup payload."""
    from memory import DB_PATH as MEMORY_DB
    from chat_manager import DB_FILE as CHAT_DB
    from settings_manager import get_appdata_dir, load_settings, save_settings

    raw  = gzip.decompress(compressed)
    data = json.loads(raw.decode("utf-8"))

    for name, path in [("memory.db", Path(MEMORY_DB)), ("chat.db", Path(CHAT_DB))]:
        if name in data.get("databases", {}):
            db_bytes = bytes.fromhex(data["databases"][name])
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".restore_tmp")
            tmp.write_bytes(db_bytes)
            tmp.replace(path)           # atomic rename
            log.info(f"Restored {name}: {len(db_bytes):,} bytes")

    if settings := data.get("settings"):
        # backup_providers is stripped from backups (see _build_payload), so a naive
        # save would wipe the local cloud credentials. Preserve device-local config:
        # the cloud credentials and the BIP-39 wordlist.
        local = load_settings()
        if local.get("backup_providers"):
            settings["backup_providers"] = local["backup_providers"]
        if local.get("backup_wordlist"):
            settings.setdefault("backup_wordlist", local["backup_wordlist"])
        save_settings(settings)
        log.info("Restored settings.json")


# ── Provider factory ───────────────────────────────────────────────────────────

def _get_provider(settings: dict):
    ptype = settings.get("backup_provider", "s3")
    cfg   = settings.get("backup_providers", {}).get(ptype, {})

    if ptype == "s3":
        from backup_providers.s3 import S3Provider
        return S3Provider(cfg)
    if ptype == "gdrive":
        from backup_providers.gdrive import GDriveProvider
        return GDriveProvider(cfg)
    if ptype == "dropbox":
        from backup_providers.dropbox_prov import DropboxProvider
        return DropboxProvider(cfg)
    if ptype == "https":
        from backup_providers.https_prov import HTTPSProvider
        return HTTPSProvider(cfg)
    raise ValueError(f"Unknown backup provider: {ptype!r}")


# ── BackupManager ──────────────────────────────────────────────────────────────

class BackupManager:
    """Singleton orchestrator — use the module-level `backup_manager` instance."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop   = threading.Event()
        self._lock   = threading.Lock()    # prevent concurrent backups

    # ── Setup ──────────────────────────────────────────────────────────────────

    def setup(
        self,
        mnemonic: str,
        provider: str,
        provider_cfg: dict,
        interval_hours: int = 24,
    ) -> None:
        """
        Validate mnemonic, derive + cache the AES key, persist provider config,
        then start the background scheduler.
        """
        key = derive_key(mnemonic)
        _keychain_store(key)

        from settings_manager import load_settings, save_settings
        s = load_settings()
        s["backup_enabled"]       = True
        s["backup_provider"]      = provider
        s["backup_interval_hours"] = interval_hours
        s.setdefault("backup_providers", {})[provider] = provider_cfg
        save_settings(s)

        log.info(f"Backup configured — provider={provider}, every {interval_hours}h")
        self.start_scheduler(interval_hours)

    def disable(self) -> None:
        """Turn off backups and remove the key from keychain."""
        self.stop_scheduler()
        _keychain_clear()
        from settings_manager import load_settings, save_settings
        s = load_settings()
        s["backup_enabled"] = False
        save_settings(s)
        log.info("Backup disabled — key removed from keychain")

    # ── On-demand operations ───────────────────────────────────────────────────

    def backup_now(self, mnemonic: Optional[str] = None) -> str:
        """
        Create + upload a backup. Returns the remote filename.

        If `mnemonic` is provided the key is re-derived (e.g. user triggered
        manually after entering their phrase). Otherwise the keychain-stored key
        is used (background scheduler path).
        """
        with self._lock:
            if mnemonic:
                key = derive_key(mnemonic)
                _keychain_store(key)
            else:
                key = _keychain_load()
                if not key:
                    raise RuntimeError(
                        "No key in keychain — enter your mnemonic phrase to unlock backups"
                    )

            from settings_manager import load_settings, save_settings
            settings = load_settings()
            provider = _get_provider(settings)

            log.info("Building backup snapshot…")
            compressed = _build_payload()
            encrypted  = encrypt_backup(key, compressed)

            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"primnox_{ts}.prx"

            provider.upload(filename, encrypted)

            settings["backup_last_sync"] = datetime.now().isoformat()
            save_settings(settings)

            log.info(f"✓ Backup complete: {filename} ({len(encrypted):,} bytes)")
            return filename

    def restore(self, filename: str, mnemonic: str) -> None:
        """Download + decrypt + restore a named backup. Requires mnemonic."""
        with self._lock:
            key = derive_key(mnemonic)

            from settings_manager import load_settings
            provider = _get_provider(load_settings())

            log.info(f"Downloading backup: {filename}")
            prx        = provider.download(filename)
            compressed = decrypt_backup(key, prx)   # raises InvalidTag on wrong key
            # Restore first; only cache key after full success so a partial
            # restore failure leaves the keychain clean for a retry.
            _restore_payload(compressed)
            _keychain_store(key)
            log.info("Restore complete — restart Primnox for changes to take effect")

    def list_backups(self) -> list[dict]:
        from settings_manager import load_settings
        try:
            return _get_provider(load_settings()).list_backups()
        except Exception as e:
            log.error(f"list_backups error: {e}")
            return []

    def delete_backup(self, filename: str) -> None:
        from settings_manager import load_settings
        _get_provider(load_settings()).delete(filename)

    def test_connection(self) -> bool:
        from settings_manager import load_settings
        try:
            return _get_provider(load_settings()).test_connection()
        except Exception as e:
            log.error(f"Connection test error: {e}")
            return False

    def status(self) -> dict:
        from settings_manager import load_settings
        s = load_settings()
        return {
            "enabled":        s.get("backup_enabled", False),
            "provider":       s.get("backup_provider"),
            "interval_hours": s.get("backup_interval_hours", 24),
            "last_sync":      s.get("backup_last_sync"),
            "key_unlocked":   _keychain_load() is not None,
        }

    # ── Background scheduler ───────────────────────────────────────────────────

    def start_scheduler(self, interval_hours: int = 24) -> None:
        self.stop_scheduler()
        # Guard: if the old thread didn't exit in time (blocked on a slow upload),
        # don't start a concurrent scheduler — log and bail instead.
        if self._thread and self._thread.is_alive():
            log.warning("Previous backup scheduler still running; skipping restart")
            return
        self._stop.clear()

        def _loop():
            log.info(f"Backup scheduler running (every {interval_hours}h)")
            # Wait one full interval before the first automatic backup
            # (user may have just done a manual backup during setup)
            while not self._stop.wait(interval_hours * 3600):
                try:
                    self.backup_now()
                except Exception as e:
                    log.error(f"Scheduled backup failed: {e}")

        self._thread = threading.Thread(
            target=_loop, daemon=True, name="backup-scheduler"
        )
        self._thread.start()

    def stop_scheduler(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            if not self._thread.is_alive():
                self._thread = None
            # If still alive: leave self._thread set so start_scheduler can detect it.

    def _auto_start(self) -> None:
        """Called at server startup — restart scheduler if backup was previously enabled."""
        from settings_manager import load_settings
        s = load_settings()
        if s.get("backup_enabled") and _keychain_load():
            hours = int(s.get("backup_interval_hours", 24))
            log.info(f"Resuming backup scheduler ({hours}h interval)")
            self.start_scheduler(hours)


# ── Module singleton ───────────────────────────────────────────────────────────
backup_manager = BackupManager()
