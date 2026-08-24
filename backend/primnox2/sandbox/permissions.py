"""Permission manifests — declared before launch, validated by the Kernel.

Every execution says what it wants *before* it starts, instead of discovering
permissions through scattered checks while it runs. That inversion is the whole
point: a manifest can be shown to a user, stored with the execution record, and
refused — a scattered check can only be hit or missed.

Three tiers, from the architecture spec:

    safe      Python, Node, Markdown, HTML — workspace only, no network
    limited   Git, npm, pip — may touch Documents, HTTP only
    elevated  system changes — registry, PATH, services

One thing is deliberately NOT inherited from the tier: whether the user is
asked at all. V1 required explicit approval for every execution, and its own
documentation records that auto-approving "safe-looking code" was considered
and rejected. That decision is kept here. The tier controls how *often* the
question is asked, never whether it is asked.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

# What the AppContainer backend actually enforces, measured on this codebase
# rather than assumed. Written down because a manifest that claims more than
# the OS delivers is worse than no manifest at all.
#
#   filesystem   enforced. Reads and writes outside granted paths fail with
#                PermissionError, including the user's Documents.
#   network      enforced. Zero capabilities means no network capability at
#                all — a Windows Filtering Platform deny, not a firewall rule.
#   registry     PARTIALLY enforced. All writes fail, including HKLM and the
#                `Run` persistence key, and reads of protected keys fail.
#                Reads of general machine configuration (HKLM\SOFTWARE\...,
#                HKCU\Environment) SUCCEED and cannot be blocked by
#                AppContainer alone.
#
# So `registry: deny` below means "no writes, no protected reads". A sandboxed
# script can still read ordinary machine configuration. That is a disclosure
# boundary, not an integrity one, and callers should know which they have.
REGISTRY_READS_ENFORCED = False

# Resource limits, same standard: measured, not assumed.
#
#   timeout_s    enforced. Wall-clock, kills the whole job object.
#   memory_mb    enforced. Job object JobMemoryLimit; the allocation raises
#                MemoryError inside the script rather than swapping the box.
#   cpu_cores    enforced as a HARD CAP on a share of total CPU
#                (cpu_cores/os.cpu_count()), via job object CPU rate control.
#                Note it does NOT change what os.cpu_count() reports inside
#                the sandbox — the script still sees every core, it just
#                cannot consume more than its share. Measured at ~7.9x less
#                work done under cpu_cores=1 than uncapped on a 16-core box.
#   disk_mb      enforced BEST-EFFORT, in two parts: a poll kills an execution
#                whose directory grows past the limit mid-run, and a check
#                after exit fails one that ended over it. There is no true
#                quota underneath — Windows disk quotas are per-volume and
#                FSRM is a Server role — so a burst that completes between
#                polls is caught after the fact rather than prevented. The
#                execution is failed and its output is not presented as a
#                success, which is the part that matters.
#   processes    enforced. Job object ActiveProcessLimit caps a fork bomb.
#
# Cross-execution isolation is an ACL, not a convention: the shared sandbox
# root carries traverse-only, non-inheritable access, and each execution
# directory is granted to the container individually. Sibling directories
# carry no ACE for it and are denied on open — not merely hidden.


# Filesystem decisions
ALLOW, ASK, DENY = "allow", "ask", "deny"

# Tiers
SAFE, LIMITED, ELEVATED = "safe", "limited", "elevated"
TIERS = (SAFE, LIMITED, ELEVATED)

# Network modes
OFFLINE, BALANCED, FULL = "offline", "balanced", "full"
NETWORK_MODES = (OFFLINE, BALANCED, FULL)

RUNTIMES = ("python", "node", "shell")

# Scopes a manifest can speak about. `workspace` is the execution's own
# ephemeral directory; everything else is the user's real machine.
SCOPES = ("workspace", "documents", "desktop", "downloads", "system", "registry")

# Resource defaults, from the architecture spec's table.
DEFAULT_TIMEOUT_S = 300
DEFAULT_MEMORY_MB = 1024
DEFAULT_DISK_MB = 512
DEFAULT_CPU_CORES = 1

# Hard ceilings. A manifest asking for more is rejected rather than clamped —
# silently granting less than was asked for produces executions that fail in
# confusing ways much later.
MAX_TIMEOUT_S = 3600
MAX_MEMORY_MB = 8192
MAX_DISK_MB = 10240

_TIER_FILESYSTEM: dict[str, dict[str, str]] = {
    SAFE: {
        "workspace": ALLOW, "documents": DENY, "desktop": DENY,
        "downloads": DENY, "system": DENY, "registry": DENY,
    },
    LIMITED: {
        "workspace": ALLOW, "documents": ASK, "desktop": ASK,
        "downloads": ASK, "system": DENY, "registry": DENY,
    },
    ELEVATED: {
        "workspace": ALLOW, "documents": ASK, "desktop": ASK,
        "downloads": ASK, "system": ASK, "registry": ASK,
    },
}

_TIER_NETWORK = {SAFE: OFFLINE, LIMITED: BALANCED, ELEVATED: FULL}


@dataclass(frozen=True)
class Manifest:
    """What an execution is asking for. Immutable once validated."""

    runtime: str
    tier: str = SAFE
    filesystem: dict[str, str] = field(default_factory=dict)
    network: str = OFFLINE
    browser: bool = False
    timeout_s: int = DEFAULT_TIMEOUT_S
    memory_mb: int = DEFAULT_MEMORY_MB
    disk_mb: int = DEFAULT_DISK_MB
    cpu_cores: int = DEFAULT_CPU_CORES
    workspace_id: str | None = None      # set => persistent project, not ephemeral

    def to_dict(self) -> dict:
        return {
            "runtime": self.runtime, "tier": self.tier,
            "filesystem": dict(self.filesystem), "network": self.network,
            "browser": self.browser, "timeout_s": self.timeout_s,
            "memory_mb": self.memory_mb, "disk_mb": self.disk_mb,
            "cpu_cores": self.cpu_cores, "workspace_id": self.workspace_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "Manifest":
        return Manifest(
            runtime=d["runtime"], tier=d.get("tier", SAFE),
            filesystem=dict(d.get("filesystem") or {}),
            network=d.get("network", OFFLINE), browser=bool(d.get("browser", False)),
            timeout_s=int(d.get("timeout_s", DEFAULT_TIMEOUT_S)),
            memory_mb=int(d.get("memory_mb", DEFAULT_MEMORY_MB)),
            disk_mb=int(d.get("disk_mb", DEFAULT_DISK_MB)),
            cpu_cores=int(d.get("cpu_cores", DEFAULT_CPU_CORES)),
            workspace_id=d.get("workspace_id"),
        )

    def describe(self) -> str:
        """One line, for the permission prompt. What the user actually decides on."""
        reach = [s for s, d in sorted(self.filesystem.items())
                 if d != DENY and s != "workspace"]
        parts = [f"{self.runtime} ({self.tier} tier)"]
        parts.append(f"network: {self.network}")
        parts.append(f"can reach: {', '.join(reach)}" if reach else "workspace only")
        parts.append(f"limits: {self.timeout_s}s, {self.memory_mb}MB")
        return " · ".join(parts)


def manifest_for(runtime: str, tier: str = SAFE, **overrides) -> Manifest:
    """Build a manifest from a tier's defaults, with explicit overrides.

    Overrides are applied on top rather than replacing the tier, so a caller
    that widens one field cannot accidentally drop the rest of the tier's
    restrictions.
    """
    base = Manifest(
        runtime=runtime,
        tier=tier,
        filesystem=dict(_TIER_FILESYSTEM.get(tier, _TIER_FILESYSTEM[SAFE])),
        network=_TIER_NETWORK.get(tier, OFFLINE),
    )
    if "filesystem" in overrides:
        merged = dict(base.filesystem)
        merged.update(overrides.pop("filesystem") or {})
        base = replace(base, filesystem=merged)
    return replace(base, **overrides) if overrides else base


def validate(m: Manifest) -> list[str]:
    """Return a list of reasons this manifest may not launch. Empty == valid.

    Returning every problem at once, rather than raising on the first, means a
    caller fixing a manifest sees the whole picture instead of one round trip
    per mistake.
    """
    errors: list[str] = []
    if m.runtime not in RUNTIMES:
        errors.append(f"unknown runtime {m.runtime!r} (expected one of {', '.join(RUNTIMES)})")
    if m.tier not in TIERS:
        errors.append(f"unknown tier {m.tier!r}")
    if m.network not in NETWORK_MODES:
        errors.append(f"unknown network mode {m.network!r}")

    for scope, decision in m.filesystem.items():
        if scope not in SCOPES:
            errors.append(f"unknown filesystem scope {scope!r}")
        if decision not in (ALLOW, ASK, DENY):
            errors.append(f"scope {scope!r} has invalid decision {decision!r}")

    # An execution that cannot write its own workspace has nowhere to put
    # anything, which is a mistake rather than a restriction.
    if m.filesystem.get("workspace", ALLOW) == DENY:
        errors.append("workspace access cannot be denied — the execution has nowhere to write")

    # The tier is a ceiling, not a suggestion. Granting system or registry
    # access outside the elevated tier would let a caller quietly launder
    # privileges through a safe-looking manifest.
    if m.tier != ELEVATED:
        for scope in ("system", "registry"):
            if m.filesystem.get(scope, DENY) != DENY:
                errors.append(f"{scope} access requires the elevated tier")
    if m.tier == SAFE and m.network != OFFLINE:
        errors.append("network access requires at least the limited tier")

    if not 1 <= m.timeout_s <= MAX_TIMEOUT_S:
        errors.append(f"timeout_s must be 1..{MAX_TIMEOUT_S}")
    if not 64 <= m.memory_mb <= MAX_MEMORY_MB:
        errors.append(f"memory_mb must be 64..{MAX_MEMORY_MB}")
    if not 16 <= m.disk_mb <= MAX_DISK_MB:
        errors.append(f"disk_mb must be 16..{MAX_DISK_MB}")
    if m.cpu_cores < 1:
        errors.append("cpu_cores must be at least 1")
    return errors


def approval_scope(m: Manifest) -> str:
    """How long an approval for this manifest may be reused.

    `turn`  — ask once, reuse for the rest of this turn (safe tier)
    `always`— ask every single time (limited and elevated)

    Nothing returns "never ask". That is the V1 invariant being preserved: no
    model-supplied code runs without a human having said yes to something.
    """
    return "turn" if m.tier == SAFE and m.network == OFFLINE else "always"


def is_reusable(m: Manifest) -> bool:
    return approval_scope(m) == "turn"
