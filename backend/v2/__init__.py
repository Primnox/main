"""Primnox V2 core substrate.

V2 is not "a bigger chat history". It is a secure, structured model of the
user's ongoing work: a world model of entities and relationships, durable
memory with provenance, structural code intelligence, a retrieval router,
resumable execution state, and cost-aware context construction.

Everything in this package is deliberately:

* **Stdlib-only.** No new pip dependencies. The V1 backend already carries a
  heavy optional-dependency surface (torch, easyocr, ultralytics); the
  substrate every other subsystem will sit on must not add to it.
* **Additive.** Nothing here monkey-patches or replaces a V1 module. V1
  keeps working untouched; integration happens at explicit call sites.
* **Import-cheap.** Importing a module here must not open a database, probe
  the filesystem, or spawn a thread. Storage is opened on first real use so
  that a process which never touches V2 pays nothing for it.

Submodules map onto the V2 architecture documents:

| Module          | V2 area                                            |
|-----------------|----------------------------------------------------|
| `ids`           | Stable typed IDs — the bridge between subsystems    |
| `store`         | Shared SQLite storage + schema registry             |
| `world_model`   | Entities, relationships, provenance, temporal truth |
| `episodes`      | Episodic/temporal memory and consolidation          |
| `result_store`  | Large tool results kept out of the transcript       |
| `task_state`    | Working/execution state and resumability            |
| `graphify`      | Structural code intelligence                        |
| `router`        | Retrieval routing (M/S/G/R/T/H/C)                   |
| `step_budget`   | Adaptive step budgets and cache economics           |
| `compaction`    | Immutable, cache-preserving context compaction      |
| `policy`        | Trust boundary, secrets, permissions, audit         |

Submodules are imported directly (`from v2 import world_model`) rather than
re-exported here, so that touching one subsystem does not drag the rest of
the package into memory.
"""

__all__ = [
    "ids",
    "store",
    "world_model",
    "episodes",
    "result_store",
    "task_state",
    "graphify",
    "router",
    "step_budget",
    "compaction",
    "policy",
]
