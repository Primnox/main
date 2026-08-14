"""Identifiers — CRS/1.0 §1.

`<prefix>_<uuid7>`. UUIDv7 because it is time-ordered: ids sort by creation,
which keeps index locality good and makes a log readable in order. Python's
stdlib has no uuid7 yet (3.11), so it is built here from the RFC 9562 layout.

Identifiers are opaque to clients (§1.3). Nothing outside this module may parse
one, and ordering never comes from an id — it comes from `sequence`.
"""
from __future__ import annotations

import os
import time
import uuid

__all__ = ["uuid7", "new_id", "CONV", "TURN", "MSG", "JOB", "EVT", "WS", "ASSET",
           "NODE", "EDGE", "CLUSTER"]

CONV, TURN, MSG, JOB, EVT, WS, ASSET = "conv", "turn", "msg", "job", "evt", "ws", "asset"
NODE, EDGE, CLUSTER = "node", "edge", "clus"

_last_ms = 0
_seq = 0


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: 48-bit ms timestamp, 12-bit sub-ms counter, 62 bits random.

    The counter matters: several ids minted inside the same millisecond must
    still sort in creation order, and without it they would sort randomly.
    """
    global _last_ms, _seq
    ms = int(time.time() * 1000)
    if ms == _last_ms:
        _seq = (_seq + 1) & 0x0FFF
        if _seq == 0:            # counter wrapped inside one ms — step forward
            ms = _last_ms = ms + 1
    else:
        _last_ms, _seq = ms, 0

    rand = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (
        (ms & ((1 << 48) - 1)) << 80
        | 0x7 << 76                      # version 7
        | (_seq & 0x0FFF) << 64
        | 0b10 << 62                     # variant
        | rand
    )
    return uuid.UUID(int=value)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid7().hex}"
