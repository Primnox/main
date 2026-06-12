#!/usr/bin/env python3
"""
Local two-instance pair-and-sync test for Primnox P2P sync.

Drives the real pairing + snapshot flow against two backends running on one
machine (different ports + isolated data dirs). It proves, deterministically and
without mDNS, that:

  • a pair code is issued by A and redeemed by B through the real HTTP stack
  • the AES key is handed off and B independently stores it (isolated keychain)
  • A and B end up in each other's ecosystem
  • each side serves an authenticated, decryptable snapshot to the other
    (the exact request a secondary makes during sync)

────────────────────────────────────────────────────────────────────────────────
SETUP — launch two isolated instances first (two terminals):

  Terminal A:
    set PRIMNOX_PORT=8000
    set PRIMNOX_DATA_DIR=%TEMP%\primnox_A
    python backend/server.py

  Terminal B:
    set PRIMNOX_PORT=8001
    set PRIMNOX_DATA_DIR=%TEMP%\primnox_B
    python backend/server.py

  Then, in a third terminal:
    python scripts/local_sync_test.py

(PowerShell: use  $env:PRIMNOX_PORT=8000  instead of  set PRIMNOX_PORT=8000)
────────────────────────────────────────────────────────────────────────────────
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

A = "http://127.0.0.1:8000"   # main
B = "http://127.0.0.1:8001"   # secondary

# Pure crypto helpers reused from the backend (no server state touched).
from backup_manager import derive_key, decrypt_backup      # noqa: E402
from sync_manager import make_auth_token                    # noqa: E402

_passed, _failed = 0, 0


def check(name: str, cond: bool, detail: str = "") -> bool:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}  {detail}")
    return cond


def call(base: str, method: str, path: str, body: dict | None = None,
         raw: bool = False, timeout: int = 30):
    """Minimal JSON HTTP client. Returns (status, parsed_or_bytes)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload or b"{}"))
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload or b"{}")
        except Exception:
            return e.code, payload
    except Exception as e:
        return 0, {"error": str(e)}


def require_up(base: str, label: str):
    status, _ = call(base, "GET", "/api/sync/status", timeout=5)
    if status != 200:
        print(f"\n  Cannot reach {label} at {base} (status={status}).")
        print(f"  Is the instance running with the right PRIMNOX_PORT?\n")
        sys.exit(2)


def snapshot_proof(server: str, signer_device_id: str, key: bytes) -> bool:
    """Call /api/sync/snapshot the way a peer does, and decrypt the result."""
    sig, ts = make_auth_token(signer_device_id, key)
    q = f"?device_id={signer_device_id}&ts={ts}&sig={sig}"
    status, payload = call(server, "GET", "/api/sync/snapshot" + q, raw=True)
    if status != 200 or not isinstance(payload, (bytes, bytearray)):
        print(f"        snapshot status={status} payload={payload!r:.80}")
        return False
    try:
        decrypt_backup(key, bytes(payload))   # raises InvalidTag on wrong key
        return True
    except Exception as e:
        print(f"        decrypt failed: {e}")
        return False


def main():
    print("Primnox local two-instance sync test")
    print(f"  A (main)      = {A}")
    print(f"  B (secondary) = {B}\n")

    require_up(A, "instance A")
    require_up(B, "instance B")

    # ── Give A a wordlist + backup key ────────────────────────────────────────
    print("[1] Configure backup on A")
    wl_path = REPO / "website" / "wordlist.txt"
    if wl_path.exists():
        words = [w.strip() for w in wl_path.read_text(encoding="utf-8").splitlines() if w.strip()]
        call(A, "POST", "/api/backup/wordlist", {"wordlist": words[:2048]})

    status, d = call(A, "POST", "/api/backup/generate-mnemonic")
    if status != 200:
        check("A generated a mnemonic", False, f"status={status} {d}")
        return _summary()
    mnemonic = d["mnemonic"]
    check("A generated a mnemonic", bool(mnemonic))

    status, d = call(A, "POST", "/api/backup/setup", {
        "mnemonic": mnemonic,
        "provider": "https",
        "provider_config": {"url": "http://127.0.0.1:9/unused"},   # never contacted by setup
        "interval_hours": 9999,
    })
    check("A backup setup stored the key", status == 200, f"status={status} {d}")
    key = derive_key(mnemonic)   # the script's own copy, to verify snapshots

    # ── Pairing ───────────────────────────────────────────────────────────────
    print("[2] Pair B with A")
    status, d = call(A, "POST", "/api/sync/pair/initiate")
    pair_code = d.get("pair_code", "")
    check("A issued a pair code", status == 200 and bool(pair_code), f"{d}")

    _, bstat = call(B, "GET", "/api/sync/status")
    b_id   = bstat.get("device", {}).get("device_id", "")
    b_name = bstat.get("device", {}).get("device_name", "Instance B")
    check("B has a device identity", bool(b_id))

    # B redeems on A — exactly the call the frontend's joinEcosystem() makes.
    status, d = call(A, "POST", "/api/sync/pair/redeem", {
        "pair_code": pair_code, "device_id": b_id, "device_name": b_name,
    })
    enc = d.get("encrypted_key", "")
    check("A accepted the redeem and returned the wrapped key", status == 200 and bool(enc), f"status={status} {d}")
    a_id   = d.get("device_a_id", "")
    a_name = d.get("device_a_name", "Instance A")

    # B accepts — decrypts with its own device_id and stores in ITS keychain.
    status, ad = call(B, "POST", "/api/sync/pair/accept", {
        "encrypted_key": enc, "pair_code": pair_code,
        "device_a_id": a_id, "device_a_name": a_name,
    })
    check("B accepted and stored the key", status == 200, f"status={status} {ad}")

    # ── Ecosystem wiring ──────────────────────────────────────────────────────
    print("[3] Verify ecosystem membership")
    _, astat = call(A, "GET", "/api/sync/status")
    check("A's ecosystem now lists B", any(x.get("id") == b_id for x in astat.get("ecosystem", [])))
    _, bstat = call(B, "GET", "/api/sync/status")
    check("B's ecosystem now lists A", any(x.get("id") == a_id for x in bstat.get("ecosystem", [])))

    # ── Authenticated snapshot, both directions ───────────────────────────────
    print("[4] Authenticated snapshot exchange (the real sync request)")
    check("A serves a decryptable snapshot to B", snapshot_proof(A, b_id, key))
    check("B serves a decryptable snapshot to A (proves B holds the same key)",
          snapshot_proof(B, a_id, key))

    return _summary()


def _summary():
    print(f"\n{_passed}/{_passed + _failed} checks passed")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
