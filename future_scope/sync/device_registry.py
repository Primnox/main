# backend/device_registry.py
"""
Device identity and ecosystem membership for Primnox P2P sync.

Every Primnox install gets a stable device_id (UUID4) on first run.
The "ecosystem" is the list of devices that share the same backup AES key
and are allowed to pull/push snapshots from one another.

Settings keys managed here:
  device_id          : str  — stable UUID, generated once
  device_name        : str  — human label ("Work Laptop")
  device_role        : "main" | "secondary"
  ecosystem_devices  : list[dict]  — authorized peers
    each: {id, name, role, last_seen, added_at}
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from logger import get_logger

log = get_logger("device_registry")


# ── Own identity ───────────────────────────────────────────────────────────────

def get_or_create_device_id() -> str:
    """Return this device's stable ID, creating it on first call."""
    from settings_manager import load_settings, save_settings
    s = load_settings()
    if not s.get("device_id"):
        s["device_id"] = str(uuid.uuid4())
        if not s.get("device_name"):
            s["device_name"] = _default_device_name()
        if not s.get("device_role"):
            s["device_role"] = "main"          # first install is always main
        save_settings(s)
        log.info(f"New device identity: {s['device_id']} ({s['device_name']}, {s['device_role']})")
    return s["device_id"]


def get_device_info() -> dict:
    from settings_manager import load_settings
    s = load_settings()
    return {
        "device_id":   s.get("device_id") or get_or_create_device_id(),
        "device_name": s.get("device_name", _default_device_name()),
        "device_role": s.get("device_role", "main"),
    }


def set_device_name(name: str) -> None:
    from settings_manager import load_settings, save_settings
    s = load_settings()
    s["device_name"] = name.strip()
    save_settings(s)


def set_device_role(role: str) -> None:
    if role not in ("main", "secondary"):
        raise ValueError("role must be 'main' or 'secondary'")
    from settings_manager import load_settings, save_settings
    s = load_settings()
    s["device_role"] = role
    save_settings(s)


def _default_device_name() -> str:
    import platform
    return platform.node() or "Primnox Device"


# ── Ecosystem (authorized peers) ───────────────────────────────────────────────

def list_ecosystem_devices() -> list[dict]:
    from settings_manager import load_settings
    return load_settings().get("ecosystem_devices", [])


def add_device(device_id: str, name: str, role: str = "secondary") -> dict:
    """Add a peer to the authorized ecosystem. Idempotent."""
    from settings_manager import load_settings, save_settings
    s = load_settings()
    devices: list[dict] = s.get("ecosystem_devices", [])

    existing = next((d for d in devices if d["id"] == device_id), None)
    if existing:
        existing["name"]      = name
        existing["role"]      = role
        existing["last_seen"] = datetime.now().isoformat()
    else:
        entry = {
            "id":        device_id,
            "name":      name,
            "role":      role,
            "added_at":  datetime.now().isoformat(),
            "last_seen": None,
        }
        devices.append(entry)
        existing = entry
        log.info(f"Added device to ecosystem: {name} ({device_id}, {role})")

    s["ecosystem_devices"] = devices
    save_settings(s)
    return existing


def remove_device(device_id: str) -> bool:
    from settings_manager import load_settings, save_settings
    s = load_settings()
    devices = s.get("ecosystem_devices", [])
    before  = len(devices)
    s["ecosystem_devices"] = [d for d in devices if d["id"] != device_id]
    save_settings(s)
    removed = len(s["ecosystem_devices"]) < before
    if removed:
        log.info(f"Removed device from ecosystem: {device_id}")
    return removed


def is_authorized(device_id: str) -> bool:
    """Return True if device_id is in the ecosystem."""
    own = get_device_info()
    if device_id == own["device_id"]:
        return True
    return any(d["id"] == device_id for d in list_ecosystem_devices())


def touch_device(device_id: str) -> None:
    """Update last_seen timestamp for a peer."""
    from settings_manager import load_settings, save_settings
    s = load_settings()
    for d in s.get("ecosystem_devices", []):
        if d["id"] == device_id:
            d["last_seen"] = datetime.now().isoformat()
            break
    save_settings(s)
