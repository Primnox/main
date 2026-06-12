# P2P Device Sync — shelved for future scope

This is the local peer-to-peer device sync feature, parked here intentionally.
It works (the pairing + crypto logic is tested), but it was shelved because
GitHub is the de-facto sync mechanism for this project: commit → pull elsewhere.

If you ever want to bring it back, this folder holds the self-contained core.
The wiring into shared files was removed — re-add the pieces below to restore it.

## What's here
- `sync_manager.py` — mDNS advertise/discover, HMAC-authenticated snapshot pull,
  `PairManager` (one-time pair-code key handoff, PBKDF2-wrapped), conflict-aware
  `merge_restore`.
- `device_registry.py` — device identity (id/name/role) + ecosystem membership,
  stored in settings.json.
- `local_sync_test.py` — deterministic two-instance pair-and-sync test (no mDNS).

## Wiring that was removed (re-add to restore)

**`backend/server.py`**
- Sync auto-start block (`from sync_manager import sync_manager; _sm.auto_start()`).
- `@app.on_event("shutdown")` → `sync_manager.shutdown()`.
- All `/api/sync/*` endpoints: status, snapshot, trigger, devices (GET/POST/DELETE),
  device PATCH, pair/initiate, pair/redeem, pair/accept, restore-merge.
- The firewall middleware's private-LAN exemption for the two P2P paths
  (`_P2P_LAN_PATHS`, `_is_private_lan`, `import ipaddress`).
- `PRIMNOX_HOST` / `PRIMNOX_PORT` env handling on the uvicorn bind (needed so a real
  LAN peer can connect — bind must be `0.0.0.0`, not `127.0.0.1`).

**`backend/backup_manager.py`**
- `_keyring_service()` — per-instance keychain isolation keyed off `PRIMNOX_DATA_DIR`
  (so two local instances don't share one key). Reverted to a fixed service name.

**`backend/settings_manager.py`**
- `PRIMNOX_DATA_DIR` override in `get_appdata_dir()` (isolated instance data dir).

**`frontend/src/app/components/SettingsView.tsx`**
- The whole `Sync` tab: state vars, the `activeTab` effect that fetches sync status,
  the helper fns (generatePairCode, joinEcosystem, triggerSync, saveDeviceName,
  removeEcosystemDevice), the tabs-array entry, and the tab JSX panel.

**`backend/requirements.txt`**
- `zeroconf` (mDNS/Bonjour for local discovery).

## Local two-instance test (when restored)
Launch two isolated backends, then run the test:
```
# A:  PRIMNOX_PORT=8000  PRIMNOX_DATA_DIR=<tmp>/A  python backend/server.py
# B:  PRIMNOX_PORT=8001  PRIMNOX_DATA_DIR=<tmp>/B  python backend/server.py
python future_scope/sync/local_sync_test.py
```
Real cross-device sync additionally needs `PRIMNOX_HOST=0.0.0.0` on both.
