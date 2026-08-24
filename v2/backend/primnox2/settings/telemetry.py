"""What Mission Control puts at the top of the screen.

Every number here is measured. That constraint is the whole design of this
module, and it is why some of the tiles you would expect are missing:

  TOKENS PER SECOND is not here. Nothing in Primnox times the gap between
  tokens, and a throughput figure derived from total tokens over wall-clock
  would count the user's thinking time as slow inference. A made-up number on
  a dashboard is worse than a missing one, because a missing one prompts a
  question and a wrong one ends it.

  A QUALITY SCORE per provider is not here either. OmniRoute has one because it
  syncs Arena ELO into a table; Primnox does not, and inventing stars for
  "coding" and "vision" would be publishing a benchmark it never ran.

What IS measured: how many providers are configured, which local models the
engine currently has resident, how many turns ran today and how many of them
finished, and the first-token latency the routing layer already records per
endpoint. Those come from the turns table and the circuit registry, both of
which exist because something else needed them.
"""
from __future__ import annotations

import logging
import time

from ..storage import db

log = logging.getLogger("primnox2.routing.telemetry")

now_ms = lambda: int(time.time() * 1000)


def _midnight_ms() -> int:
    """Local midnight, not UTC. "Today" on a desktop means the user's today,
    and a dashboard that rolls over at 01:00 because the machine is in CET is
    a dashboard nobody trusts twice."""
    local = time.localtime()
    midnight = time.struct_time((local.tm_year, local.tm_mon, local.tm_mday,
                                 0, 0, 0, local.tm_wday, local.tm_yday, local.tm_isdst))
    return int(time.mktime(midnight) * 1000)


def turn_counts() -> dict:
    """Today's turns by outcome. Cheap: one indexed scan over a small table."""
    try:
        rows = db.connect().execute(
            "SELECT status, COUNT(*) AS n FROM turns WHERE created_at >= ? GROUP BY status",
            (_midnight_ms(),)).fetchall()
    except Exception as exc:                                  # noqa: BLE001
        log.debug("turn counts unavailable (%s)", exc)
        return {"today": 0, "completed": 0, "failed": 0, "cancelled": 0, "live": 0}

    by_status = {r["status"]: r["n"] for r in rows}
    terminal = ("completed", "failed", "cancelled")
    return {
        "today": sum(by_status.values()),
        "completed": by_status.get("completed", 0),
        "failed": by_status.get("failed", 0),
        "cancelled": by_status.get("cancelled", 0),
        "live": sum(n for s, n in by_status.items() if s not in terminal),
    }


def success_rate() -> float | None:
    """Completed over completed-plus-failed, today.

    Cancelled turns are excluded from both sides rather than counted as
    failures: the user pressing stop is not the provider getting it wrong, and
    folding the two together makes the number say nothing about either.

    None when nothing finished today — a rate over zero turns is 0%, which
    reads as catastrophe rather than as "no data".
    """
    counts = turn_counts()
    decided = counts["completed"] + counts["failed"]
    if not decided:
        return None
    return round(counts["completed"] / decided, 4)


def ollama_loaded() -> list[dict]:
    """Models the local engine currently has resident in memory.

    `/api/ps`, not `/api/tags`: installed and loaded are different states, and
    the one that costs VRAM right now is the one worth a tile. An engine that
    is not running answers nothing and gets an empty list rather than an error.
    """
    from . import models as store

    payload = store._fetch(f"{store.OLLAMA_HOST}/api/ps")
    if not isinstance(payload, dict):
        return []
    out = []
    for row in payload.get("models", []):
        size = row.get("size_vram") or row.get("size") or 0
        out.append({
            "name": row.get("name", ""),
            "vram_gb": round(size / 1_000_000_000, 1),
            "expires_at": row.get("expires_at", ""),
        })
    return sorted(out, key=lambda m: m["name"])


def snapshot() -> dict:
    """One call for the whole header. The UI polls this, so it stays cheap:
    two small SQL reads and one loopback request that fails fast when the
    engine is down."""
    from ..models import health
    from . import models as store

    profiles = store.profiles()
    circuits = health.snapshot()
    loaded = ollama_loaded()
    counts = turn_counts()

    # Latency across everything that has actually answered, weighted by how
    # much each endpoint was used — an endpoint called twice should not move
    # the headline as much as one called two hundred times.
    weighted = [(c["latency_ms"], c["calls"]) for c in circuits
                if c["latency_ms"] is not None and c["calls"]]
    total_calls = sum(n for _, n in weighted)
    latency = round(sum(ms * n for ms, n in weighted) / total_calls) if total_calls else None

    active = store.active_name()
    active_profile = next((p for p in profiles if p["name"] == active), None)
    local_active = bool(active_profile and active_profile.get("kind") in ("ollama", "local"))

    try:
        from . import service as settings_service
        scrubbing = settings_service.get("privacy.mirror_enabled", "on") == "on"
    except Exception:                                         # noqa: BLE001
        scrubbing = True

    return {
        "providers": len(profiles),
        "local_loaded": len(loaded),
        "loaded_models": loaded,
        "requests_today": counts["today"],
        "turns": counts,
        "success_rate": success_rate(),
        "latency_ms": latency,
        "open_circuits": sum(1 for c in circuits if c["open"]),
        "active": active,
        # Two separate facts, because "is my data safe" has two halves and a
        # single padlock icon answers neither: whether this turn stays on the
        # machine, and whether it is pseudonymized if it does not.
        "local_active": local_active,
        "scrubbing": scrubbing,
        "healthy": sum(1 for c in circuits if c["open"]) == 0,
    }
