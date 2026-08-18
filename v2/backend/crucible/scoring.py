"""Scores, findings, and the grade.

Five axes per module, 0-10 each, from the Crucible specification:

    Correctness   did it produce the right answer
    Consistency   did it produce the SAME answer across identical runs
    Recovery      did it survive the thing that went wrong
    Performance   did it stay inside its budget
    UX Stability  did the surface stay usable while it happened

A module may decline any axis it cannot honestly measure. Declining is not zero:
zero says "measured, failed", and a suite that cannot tell those apart reports
architecture failures that are really coverage gaps.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

CRITICAL, HIGH, MEDIUM, LOW = "critical", "high", "medium", "low"

# Which V2 subsystem owns a fix. Named here so a finding cannot invent an owner
# that nobody is responsible for.
OWNERS = (
    "Event Bus", "Sandbox Manager", "Context Service", "Asset Service",
    "Workspace System", "Knowledge Service", "Memory Service", "Storage",
    "Scheduler", "Model Gateway", "Frontend Shell", "Privacy Gateway (future)",
)

AXES = ("correctness", "consistency", "recovery", "performance", "ux_stability")

NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class Finding:
    """One defect. Written to be actionable without the conversation that found it."""
    module: str
    title: str
    severity: str
    owner: str
    what_happened: str
    reproduction: str
    probable_cause: str = ""
    suggested_fix: str = ""
    evidence: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ModuleResult:
    key: str
    name: str
    status: str = "RUN"                       # RUN | NOT_APPLICABLE | ERROR
    reason: str = ""                          # why, when not RUN
    scores: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    measurements: dict = field(default_factory=dict)
    duration_s: float = 0.0

    def score(self, **axes) -> None:
        for axis, value in axes.items():
            if axis not in AXES:
                raise ValueError(f"unknown axis {axis!r}")
            self.scores[axis] = max(0, min(10, value))

    def find(self, **kwargs) -> Finding:
        f = Finding(module=self.key, **kwargs)
        self.findings.append(f)
        return f

    def skip(self, reason: str) -> None:
        self.status = NOT_APPLICABLE
        self.reason = reason

    @property
    def average(self) -> float | None:
        """None when nothing was measured, so it can be excluded rather than
        counted as zero."""
        if self.status != "RUN" or not self.scores:
            return None
        return statistics.mean(self.scores.values())

    def to_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name, "status": self.status,
            "reason": self.reason, "scores": self.scores,
            "average": self.average, "duration_s": round(self.duration_s, 2),
            "measurements": self.measurements,
            "findings": [f.to_dict() for f in self.findings],
        }


def grade(overall: float | None) -> str:
    if overall is None:
        return "NOT MEASURED"
    if overall >= 9.5:
        return "PRODUCTION READY"
    if overall >= 8.5:
        return "BETA"
    if overall >= 7.0:
        return "ALPHA"
    return "ARCHITECTURE FAILURE"


def summarise(results: list[ModuleResult]) -> dict:
    scored = [r for r in results if r.average is not None]
    # Averaged over modules that RAN. Modules whose subsystem is absent are
    # reported separately rather than folded in: a missing browser is a scope
    # fact, not a quality signal, and letting it drag the score down would make
    # the number say something it does not mean.
    overall = statistics.mean(r.average for r in scored) if scored else None
    by_severity = {s: 0 for s in (CRITICAL, HIGH, MEDIUM, LOW)}
    for r in results:
        for f in r.findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    # A single critical finding caps the grade regardless of the average. Ten
    # modules at 9.8 and one subsystem that loses data is not a beta.
    verdict = grade(overall)
    if by_severity.get(CRITICAL) and verdict in ("PRODUCTION READY", "BETA"):
        verdict = "ALPHA (capped: unresolved critical finding)"

    return {
        "overall": round(overall, 2) if overall is not None else None,
        "verdict": verdict,
        "modules_run": len(scored),
        "modules_not_applicable": sum(1 for r in results if r.status == NOT_APPLICABLE),
        "modules_errored": sum(1 for r in results if r.status == "ERROR"),
        "findings": by_severity,
        "total_findings": sum(by_severity.values()),
        "by_axis": {
            axis: round(statistics.mean(
                [r.scores[axis] for r in scored if axis in r.scores]), 2)
            for axis in AXES
            if any(axis in r.scores for r in scored)
        },
    }
