# backend/sync_manager.py
"""
P2P device sync for Primnox.

Architecture
────────────
Main device
  • Registers mDNS service  _primnox._tcp.local.
  • Exposes GET /api/sync/snapshot  (authenticated by HMAC)
  • On startup: pulls latest .prx from cloud if no local snapshot is newer

Secondary device
  • Browses mDNS for _primnox._tcp.local.
  • When main is found: hits /api/sync/snapshot → restores if newer
  • Falls back to cloud (backup_manager.list_backups + restore) if main absent

Authentication
  • Both devices share the same AES-256 backup key (from keychain)
  • Request carries: device_id + unix_ts + HMAC-SHA256(f"{device_id}:{ts}", key)
  • Main verifies: device_id in ecosystem + HMAC valid + ts within ±60 s

Conflict resolution
  • "created_at" timestamp embedded in the .prx payload JSON decides winner
  • Newer timestamp wins; if equal, main device wins
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from datetime import datetime
from typing import Optional

from logger import get_logger

log = get_logger("sync")

_MDNS_TYPE    = "_primnox._tcp.local."
_MDNS_NAME    = "primnox"
_SYNC_PORT    = int(os.getenv("PRIMNOX_PORT", "8000"))   # matches the FastAPI server port
_TS_TOLERANCE = 60            # seconds — replay-attack window


# ── HMAC auth helpers ──────────────────────────────────────────────────────────

def make_auth_token(device_id: str, aes_key: bytes) -> tuple[str, int]:
    """Return (hmac_hex, unix_ts) for a sync request."""
    ts  = int(time.time())
    sig = hmac.new(aes_key, f"{device_id}:{ts}".encode(), hashlib.sha256).hexdigest()
    return sig, ts


def verify_auth_token(device_id: str, ts: int, sig: str, aes_key: bytes) -> bool:
    """Return True if the HMAC is valid and the timestamp is fresh."""
    if abs(time.time() - ts) > _TS_TOLERANCE:
        log.warning(f"Sync auth: stale timestamp from {device_id} (delta={abs(time.time()-ts):.0f}s)")
        return False
    expected = hmac.new(aes_key, f"{device_id}:{ts}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


# ── SyncManager ───────────────────────────────────────────────────────────────

class SyncManager:
    """Singleton — use the module-level `sync_manager` instance."""

    def __init__(self):
        self._zeroconf     = None
        self._service_info = None
        self._browser      = None
        self._peers: dict[str, dict] = {}   # device_id → {host, port, name}
        self._lock         = threading.Lock()
        self._sync_thread: Optional[threading.Thread] = None
        self._stop         = threading.Event()

    # ── mDNS advertisement (main device) ──────────────────────────────────────

    def start_advertising(self, port: int = _SYNC_PORT) -> None:
        """Register this device on the local network via mDNS."""
        try:
            from zeroconf import Zeroconf, ServiceInfo
            import socket
        except ImportError:
            log.warning("zeroconf not installed — mDNS advertising disabled. Run: pip install zeroconf")
            return

        from device_registry import get_device_info
        info = get_device_info()

        # The Zeroconf instance name must be unique per device — a fixed "primnox"
        # name makes two devices (or two local instances) collide on the same LAN.
        instance = f"{_MDNS_NAME}-{info['device_id'][:8]}"
        self._zeroconf = Zeroconf()
        self._service_info = ServiceInfo(
            _MDNS_TYPE,
            f"{instance}.{_MDNS_TYPE}",
            addresses=[socket.inet_aton(self._local_ip())],
            port=port,
            properties={
                "device_id":   info["device_id"].encode(),
                "device_name": info["device_name"].encode(),
                "role":        info["device_role"].encode(),
            },
        )
        self._zeroconf.register_service(self._service_info)
        log.info(f"mDNS: advertising as {info['device_name']} on port {port}")

    def stop_advertising(self) -> None:
        if self._zeroconf and self._service_info:
            self._zeroconf.unregister_service(self._service_info)
            self._zeroconf.close()
            self._zeroconf = None
            self._service_info = None
            log.info("mDNS: stopped advertising")

    # ── mDNS discovery (secondary device) ─────────────────────────────────────

    def start_discovery(self) -> None:
        """Browse for Primnox devices on the local network."""
        try:
            from zeroconf import Zeroconf, ServiceBrowser
        except ImportError:
            log.warning("zeroconf not installed — mDNS discovery disabled")
            return

        self._zeroconf = self._zeroconf or Zeroconf()

        class _Handler:
            def __init__(self_, mgr): self_._mgr = mgr

            def add_service(self_, zc, svc_type, name):
                info = zc.get_service_info(svc_type, name)
                if not info:
                    return
                import socket
                host = socket.inet_ntoa(info.addresses[0]) if info.addresses else None
                props = {k.decode(): v.decode() for k, v in info.properties.items()}
                did  = props.get("device_id", "")
                dname = props.get("device_name", "unknown")
                if not host or not did:
                    return
                with self_._mgr._lock:
                    self_._mgr._peers[did] = {
                        "host": host, "port": info.port,
                        "name": dname, "seen_at": datetime.now().isoformat(),
                    }
                log.info(f"mDNS: found peer {dname} ({did}) at {host}:{info.port}")

            def remove_service(self_, zc, svc_type, name):
                pass   # peers expire naturally via last_seen

            def update_service(self_, zc, svc_type, name):
                self_.add_service(zc, svc_type, name)

        self._browser = ServiceBrowser(self._zeroconf, _MDNS_TYPE, _Handler(self))
        log.info("mDNS: browsing for Primnox peers")

    def stop_discovery(self) -> None:
        if self._browser:
            self._browser.cancel()
            self._browser = None

    # ── Sync logic ─────────────────────────────────────────────────────────────

    def known_peers(self) -> list[dict]:
        with self._lock:
            return list(self._peers.values())

    def sync_from_peer(self, peer_host: str, peer_port: int) -> bool:
        """
        Pull the latest snapshot from a peer and restore if it's newer.
        Returns True if data was updated.
        """
        from backup_manager import _keychain_load, decrypt_backup, _restore_payload
        from settings_manager import load_settings
        from device_registry import get_device_info, touch_device

        key = _keychain_load()
        if not key:
            log.warning("Sync aborted — no key in keychain")
            return False

        info   = get_device_info()
        sig, ts = make_auth_token(info["device_id"], key)
        url = (
            f"http://{peer_host}:{peer_port}/api/sync/snapshot"
            f"?device_id={info['device_id']}&ts={ts}&sig={sig}"
        )

        try:
            import httpx
            r = httpx.get(url, timeout=30)
            if r.status_code == 403:
                log.warning("Sync: peer rejected our device_id — not in their ecosystem")
                return False
            if r.status_code != 200:
                log.warning(f"Sync: peer returned {r.status_code}")
                return False

            prx_bytes = r.content
            peer_device_id = r.headers.get("X-Device-Id", "unknown")

            compressed   = decrypt_backup(key, prx_bytes)
            peer_ts_str  = _extract_created_at(compressed)

            s = load_settings()
            local_ts_str = s.get("backup_last_sync")
            if local_ts_str and peer_ts_str:
                peer_dt  = datetime.fromisoformat(peer_ts_str.rstrip("Z"))
                local_dt = datetime.fromisoformat(local_ts_str)
                if peer_dt <= local_dt:
                    log.info(f"Sync: peer snapshot is not newer (peer={peer_ts_str}, local={local_ts_str}), skipping")
                    return False

            _restore_payload(compressed)
            touch_device(peer_device_id)
            log.info(f"Sync: restored snapshot from {peer_host}:{peer_port} (ts={peer_ts_str})")
            return True

        except Exception as e:
            log.error(f"Sync from peer {peer_host}:{peer_port} failed: {e}")
            return False

    def sync_from_cloud_fallback(self) -> bool:
        """Pull latest .prx from the configured cloud provider and restore if newer."""
        from backup_manager import backup_manager, _keychain_load, decrypt_backup, _restore_payload
        from settings_manager import load_settings

        key = _keychain_load()
        if not key:
            return False

        try:
            backups = backup_manager.list_backups()
            if not backups:
                return False

            latest = backups[0]   # already sorted newest-first by providers
            s = load_settings()
            local_ts = s.get("backup_last_sync")
            if local_ts and latest.get("timestamp"):
                peer_dt  = datetime.fromisoformat(latest["timestamp"].rstrip("Z"))
                local_dt = datetime.fromisoformat(local_ts)
                if peer_dt <= local_dt:
                    return False

            from backup_manager import _get_provider
            prx_bytes = _get_provider(s).download(latest["name"])
            compressed = decrypt_backup(key, prx_bytes)
            _restore_payload(compressed)
            log.info(f"Sync: restored from cloud ({latest['name']})")
            return True
        except Exception as e:
            log.error(f"Cloud fallback sync failed: {e}")
            return False

    def run_sync_cycle(self) -> None:
        """One sync attempt: try peers first, fall back to cloud."""
        from device_registry import get_device_info, is_authorized
        from settings_manager import load_settings

        role = get_device_info().get("device_role", "main")
        if role == "main":
            return   # main device only pushes (via backup_manager.backup_now)

        # Try each known peer (prefer main role)
        with self._lock:
            peers_copy = dict(self._peers)

        for did, peer in peers_copy.items():
            if not is_authorized(did):
                continue
            updated = self.sync_from_peer(peer["host"], peer["port"])
            if updated:
                return

        # No live peer found — try cloud
        self.sync_from_cloud_fallback()

    # ── Background polling ─────────────────────────────────────────────────────

    def start_sync_loop(self, interval_seconds: int = 300) -> None:
        """Poll for peers and sync every N seconds (default 5 min)."""
        if self._sync_thread and self._sync_thread.is_alive():
            return
        self._stop.clear()

        def _loop():
            log.info(f"Sync loop started (every {interval_seconds}s)")
            while not self._stop.wait(interval_seconds):
                try:
                    self.run_sync_cycle()
                except Exception as e:
                    log.error(f"Sync loop error: {e}")

        self._sync_thread = threading.Thread(target=_loop, daemon=True, name="sync-loop")
        self._sync_thread.start()

    def stop_sync_loop(self) -> None:
        self._stop.set()
        # Join so a subsequent start_sync_loop() can't race and spawn a 2nd loop
        # (is_alive() could otherwise still report the old thread as running).
        t = self._sync_thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=5)
        self._sync_thread = None

    def shutdown(self) -> None:
        """Tear down mDNS + sync loop. Call on server shutdown."""
        try:
            self.stop_sync_loop()
        except Exception as e:
            log.warning(f"stop_sync_loop failed: {e}")
        try:
            self.stop_discovery()
        except Exception as e:
            log.warning(f"stop_discovery failed: {e}")
        try:
            self.stop_advertising()
        except Exception as e:
            log.warning(f"stop_advertising failed: {e}")

    # ── Auto-start ─────────────────────────────────────────────────────────────

    def auto_start(self) -> None:
        """Called at server startup — wire up mDNS and sync loop."""
        from device_registry import get_or_create_device_id, get_device_info
        from settings_manager import load_settings

        get_or_create_device_id()   # ensure identity exists
        info = get_device_info()
        s    = load_settings()

        if not s.get("backup_enabled"):
            return   # backup not configured — nothing to sync

        if info["device_role"] == "main":
            self.start_advertising()
        else:
            self.start_discovery()
            self.start_sync_loop()

        log.info(f"Sync auto-started (role={info['device_role']})")

    # ── Utilities ──────────────────────────────────────────────────────────────

    @staticmethod
    def _local_ip() -> str:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()


def _extract_created_at(compressed: bytes) -> Optional[str]:
    """Parse the created_at field from a gzip-compressed backup payload."""
    import gzip, json
    try:
        raw  = gzip.decompress(compressed)
        data = json.loads(raw)
        return data.get("created_at")
    except Exception:
        return None


# ── Key distribution (device pairing) ─────────────────────────────────────────

class PairManager:
    """
    Secure one-time key handoff between devices on the local network.

    Protocol
    ─────────
    Device A (authorizer, already has backup key)
      1. POST /api/sync/pair/initiate  →  {pair_id, pair_code, expires_at}
         pair_code = 8 random hex chars shown to the user (≈ 32 bits entropy)

    Device B (joiner, wants the key)
      2. POST /api/sync/pair/redeem   (hits Device A's IP directly)
         body = {pair_code, device_id, device_name}
         →  {encrypted_key_b64, device_a_id}

    Encryption:  transfer_secret = SHA-256(pair_code + ":" + device_b_id)
                 encrypted_key   = AES-256-GCM(aes_key, key=transfer_secret)

    Device B decrypts, stores key in keychain, adds Device A to ecosystem.
    Each pair_code expires after PAIR_TTL_SECONDS and is one-time-use.
    """

    PAIR_TTL_SECONDS    = 300   # 5 minutes
    MAX_FAILED_ATTEMPTS = 10    # wrong-code guesses before a lockout kicks in
    LOCKOUT_SECONDS     = 60

    def __init__(self):
        self._pending: dict[str, dict] = {}   # pair_code → {expires, device_b_id}
        self._lock = threading.Lock()
        self._failed_attempts = 0
        self._lockout_until   = 0.0

    def initiate(self) -> dict:
        """Device A: generate a fresh pair code."""
        import secrets as _sec
        self._cleanup_expired()
        pair_code = _sec.token_hex(4).upper()   # 8 hex chars, e.g. "A1B2C3D4"
        expires   = time.time() + self.PAIR_TTL_SECONDS
        with self._lock:
            self._pending[pair_code] = {"expires": expires, "device_b_id": None}
        log.info(f"Pair code generated: {pair_code} (expires in {self.PAIR_TTL_SECONDS}s)")
        from datetime import datetime, timezone
        return {
            "pair_code":  pair_code,
            "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
        }

    def redeem(self, pair_code: str, device_b_id: str, device_b_name: str) -> bytes:
        """
        Device B calls this on Device A.
        Returns the AES key encrypted for Device B to decrypt using pair_code.
        Adds Device B to the ecosystem and marks the code as consumed.
        """
        from backup_manager import _keychain_load
        from device_registry import add_device

        pair_code = pair_code.upper()
        self._cleanup_expired()

        # Throttle online brute-force: after too many wrong guesses, lock out briefly.
        with self._lock:
            if time.time() < self._lockout_until:
                raise ValueError("Too many attempts — try again in a minute")

        # Load the key up front so a device with no key never consumes the pair
        # code (otherwise a transient keychain failure permanently burns it).
        key = _keychain_load()
        if not key:
            raise RuntimeError("No backup key in keychain on this device")

        with self._lock:
            entry = self._pending.get(pair_code)
            if not entry:
                self._failed_attempts += 1
                if self._failed_attempts >= self.MAX_FAILED_ATTEMPTS:
                    self._lockout_until = time.time() + self.LOCKOUT_SECONDS
                    self._failed_attempts = 0
                raise ValueError("Invalid or expired pair code")
            if entry["device_b_id"]:
                raise ValueError("Pair code already used")
            entry["device_b_id"] = device_b_id   # consume only after every check passes
            self._failed_attempts = 0

        encrypted = _encrypt_key_for_transfer(key, pair_code, device_b_id)

        # Authorize the new device
        add_device(device_b_id, device_b_name, role="secondary")
        log.info(f"Key handed off to new device: {device_b_name} ({device_b_id})")

        return encrypted

    def accept(self, encrypted_key: bytes, pair_code: str,
               device_a_id: str, device_a_name: str) -> None:
        """
        Device B: decrypt the transferred key and store it in the keychain.
        Also registers Device A in the local ecosystem.
        """
        from backup_manager import _keychain_store
        from device_registry import get_or_create_device_id, add_device

        own_id = get_or_create_device_id()
        key    = _decrypt_key_from_transfer(encrypted_key, pair_code.upper(), own_id)
        _keychain_store(key)
        add_device(device_a_id, device_a_name, role="main")
        log.info(f"Key received and stored. Registered Device A: {device_a_name} ({device_a_id})")

    def _cleanup_expired(self) -> None:
        now = time.time()
        with self._lock:
            stale = [c for c, e in self._pending.items() if e["expires"] < now]
            for c in stale:
                del self._pending[c]


# The pair code is only ~32 bits of entropy, so a plain hash would let an attacker
# who intercepts the encrypted blob brute-force it offline in seconds. A slow KDF
# (PBKDF2, 200k iterations) raises the cost of each guess by ~6 orders of magnitude,
# making exhaustion of the keyspace infeasible. The salt is derived from device_b_id
# (known to both sides, not secret) so both devices derive the same secret.
_PAIR_KDF_ITERATIONS = 200_000

def _derive_transfer_secret(pair_code: str, device_b_id: str) -> bytes:
    import hashlib
    salt = hashlib.sha256(f"primnox-pair-v2:{device_b_id}".encode()).digest()
    return hashlib.pbkdf2_hmac(
        "sha256", pair_code.encode(), salt, _PAIR_KDF_ITERATIONS, dklen=32
    )


def _encrypt_key_for_transfer(aes_key: bytes, pair_code: str, device_b_id: str) -> bytes:
    """AES-256-GCM encrypt `aes_key` using a KDF-derived secret from pair_code + device_b_id."""
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    transfer_secret = _derive_transfer_secret(pair_code, device_b_id)
    nonce = os.urandom(12)
    ct    = AESGCM(transfer_secret).encrypt(nonce, aes_key, None)
    return nonce + ct   # 12-byte nonce || ciphertext+tag


def _decrypt_key_from_transfer(blob: bytes, pair_code: str, device_b_id: str) -> bytes:
    """Reverse of _encrypt_key_for_transfer."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    transfer_secret = _derive_transfer_secret(pair_code, device_b_id)
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(transfer_secret).decrypt(nonce, ct, None)


# ── Conflict-aware merge ───────────────────────────────────────────────────────

def merge_restore(compressed_remote: bytes) -> dict:
    """
    Merge a remote backup payload into the local databases instead of
    fully overwriting.

    Merge rules
    ───────────
    memories   append-only  — remote rows INSERT OR IGNORE (never delete local)
    notes      last-write-wins — remote row wins when its timestamp > local row
    tasks      last-write-wins — same as notes
    settings   remote wins (newer snapshot's settings override local)

    Returns a summary dict of what changed.
    """
    import gzip, json, sqlite3
    from memory import DB_PATH as MEMORY_DB
    from chat_manager import DB_FILE as CHAT_DB
    from settings_manager import get_appdata_dir, save_settings
    from pathlib import Path

    raw  = gzip.decompress(compressed_remote)
    data = json.loads(raw)
    summary = {"memories_added": 0, "notes_merged": 0, "tasks_merged": 0,
               "settings_restored": False}

    # ── memory.db merge ───────────────────────────────────────────────────────
    if "memory.db" in data.get("databases", {}):
        remote_bytes = bytes.fromhex(data["databases"]["memory.db"])
        # sqlite3.connect needs a real path (BytesIO is not supported), so write
        # the remote DB to a temp file and always clean it up afterwards.
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        Path(tmp_path).write_bytes(remote_bytes)

        remote_conn = local_conn = None
        try:
            remote_conn = sqlite3.connect(tmp_path)
            remote_conn.row_factory = sqlite3.Row
            local_conn  = sqlite3.connect(str(MEMORY_DB))
            local_conn.row_factory = sqlite3.Row

            # memories — append-only
            try:
                rows = remote_conn.execute(
                    "SELECT key,text,category,timestamp,stale,session_id,compressed FROM memories"
                ).fetchall()
                row_errors = 0
                for row in rows:
                    try:
                        local_conn.execute(
                            "INSERT OR IGNORE INTO memories "
                            "(key,text,category,timestamp,stale,session_id,compressed) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (row["key"], row["text"], row["category"], row["timestamp"],
                             row["stale"], row["session_id"], row["compressed"]),
                        )
                        summary["memories_added"] += local_conn.changes()
                    except Exception as row_err:
                        row_errors += 1
                        if row_errors == 1:   # log the first failure only, to avoid spam
                            log.warning(f"Merge memories: row insert failed: {row_err}")
                if row_errors:
                    summary["memories_failed"] = row_errors
                    log.warning(f"Merge memories: {row_errors}/{len(rows)} rows failed (schema mismatch?)")
            except Exception as e:
                log.warning(f"Merge memories skipped: {e}")

            # notes — last-write-wins by timestamp
            try:
                remote_notes = remote_conn.execute(
                    "SELECT id,title,text,key_points,action_items,timestamp,project,parent_id,pinned FROM notes"
                ).fetchall()
                for rn in remote_notes:
                    existing = local_conn.execute(
                        "SELECT timestamp FROM notes WHERE id=?", (rn["id"],)
                    ).fetchone()
                    r_ts = rn["timestamp"] or ""
                    l_ts = existing["timestamp"] if existing else ""
                    if not existing or r_ts > l_ts:
                        local_conn.execute(
                            "INSERT OR REPLACE INTO notes "
                            "(id,title,text,key_points,action_items,timestamp,project,parent_id,pinned) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (rn["id"], rn["title"], rn["text"], rn["key_points"],
                             rn["action_items"], rn["timestamp"], rn["project"],
                             rn["parent_id"], rn["pinned"]),
                        )
                        summary["notes_merged"] += 1
            except Exception as e:
                log.warning(f"Merge notes skipped: {e}")

            # tasks — last-write-wins by timestamp
            try:
                remote_tasks = remote_conn.execute(
                    "SELECT id,text,priority,due_date,completed,timestamp FROM tasks"
                ).fetchall()
                for rt in remote_tasks:
                    existing = local_conn.execute(
                        "SELECT timestamp FROM tasks WHERE id=?", (rt["id"],)
                    ).fetchone()
                    r_ts = rt["timestamp"] or ""
                    l_ts = existing["timestamp"] if existing else ""
                    if not existing or r_ts > l_ts:
                        local_conn.execute(
                            "INSERT OR REPLACE INTO tasks "
                            "(id,text,priority,due_date,completed,timestamp) "
                            "VALUES (?,?,?,?,?,?)",
                            (rt["id"], rt["text"], rt["priority"],
                             rt["due_date"], rt["completed"], rt["timestamp"]),
                        )
                        summary["tasks_merged"] += 1
            except Exception as e:
                log.warning(f"Merge tasks skipped: {e}")

            local_conn.commit()
        finally:
            if local_conn is not None:
                local_conn.close()
            if remote_conn is not None:
                remote_conn.close()
            Path(tmp_path).unlink(missing_ok=True)

    # ── settings merge — remote wins ─────────────────────────────────────────
    if "settings" in data:
        remote_settings = data["settings"]
        # Preserve device-local config that must never be overwritten by a peer:
        # cloud credentials (stripped from backups), the BIP-39 wordlist, and this
        # device's own identity.
        from settings_manager import load_settings
        local = load_settings()
        if local.get("backup_providers"):
            remote_settings["backup_providers"] = local["backup_providers"]
        else:
            remote_settings.setdefault("backup_providers", {})
        if local.get("backup_wordlist"):
            remote_settings["backup_wordlist"] = local["backup_wordlist"]
        remote_settings["device_id"]   = local.get("device_id")
        remote_settings["device_name"] = local.get("device_name")
        remote_settings["device_role"] = local.get("device_role")
        save_settings(remote_settings)
        summary["settings_restored"] = True

    log.info(f"Merge complete: {summary}")
    return summary


# ── Module singletons ──────────────────────────────────────────────────────────
sync_manager = SyncManager()
pair_manager = PairManager()
