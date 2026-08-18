"""Scoring a system's answers against the pack's ground truth.

Five weighted axes, from the specification:

    answer     40%   did it say the right thing
    evidence   25%   could it name the artifacts that prove it
    time       15%   did it answer as of the right moment
    path       10%   did it traverse the relationships it claimed to
    speed      10%   did it do that inside a usable budget

WHY EVIDENCE IS WEIGHTED SO HEAVILY. A system that returns "Espresso" while
citing a document about laptops is not right — it guessed, and next month it
will guess wrong. Scoring only the answer rewards a confident coin flip exactly
as much as retrieval, and the difference between those two is the entire product.

PARTIAL CREDIT, NOT PASS/FAIL. A query whose answer is a list of eleven people
is not usefully scored by "did it return all eleven": a system returning ten is
much better than one returning none, and a binary score cannot see the
difference — so it cannot see an improvement either, which is what a benchmark
exists to detect. Sets are scored by F1.

AXES CAN BE DECLINED. If ground truth has no expected graph path, the path axis
is NOT scored zero — it is dropped and its weight is spread across the axes that
remain. Zero means "measured, failed"; a suite that cannot tell that apart from
"not applicable" reports coverage gaps as quality failures. Note that this is
about the ANSWER KEY declining to test an axis. A system that simply does not
answer a query scores zero on everything, because that is a measured failure.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

WEIGHTS = {"answer": 0.40, "evidence": 0.25, "time": 0.15, "path": 0.10,
           "speed": 0.10}

# Full marks at or under FAST_MS, nothing at or over SLOW_MS, linear between.
# Five seconds is where a local retrieval answer stops feeling like an answer
# and starts feeling like a job you submitted.
FAST_MS, SLOW_MS = 500.0, 5_000.0

GRADES = ((95.0, "EXCELLENT"), (85.0, "GOOD"), (70.0, "NEEDS WORK"))
REGRESSION = "RETRIEVAL REGRESSION"


def grade(percent: float | None) -> str:
    if percent is None:
        return "NOT MEASURED"
    for floor, name in GRADES:
        if percent >= floor:
            return name
    return REGRESSION


def _normalise(value):
    """Compare on meaning, not on formatting."""
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple, set)):
        return [_normalise(v) for v in value]
    if isinstance(value, dict):
        return {str(k).lower(): _normalise(v) for k, v in value.items()}
    return value


def _f1(expected, actual) -> float:
    """Set overlap. Unhashable members fall back to positional comparison."""
    try:
        want, got = set(map(_hashable, expected)), set(map(_hashable, actual))
    except TypeError:  # pragma: no cover - defensive
        return 1.0 if list(expected) == list(actual) else 0.0
    if not want and not got:
        return 1.0
    if not want or not got:
        return 0.0
    hit = len(want & got)
    if not hit:
        return 0.0
    precision, recall = hit / len(got), hit / len(want)
    return 2 * precision * recall / (precision + recall)


def _hashable(value):
    if isinstance(value, dict):
        return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple, set)):
        return tuple(_hashable(v) for v in value)
    return value


def compare_answer(expected, actual) -> float:
    """Graded similarity in [0, 1]."""
    want, got = _normalise(expected), _normalise(actual)
    if want == got:
        return 1.0
    if isinstance(want, list):
        return _f1(want, got if isinstance(got, list) else [got])
    if isinstance(want, dict):
        if not isinstance(got, dict):
            return 0.0
        # Every expected key counts, including ones the answer omitted —
        # otherwise a response containing a single correct field scores full
        # marks for being right about a fraction of the question.
        return statistics.mean(
            [compare_answer(v, got.get(k)) for k, v in want.items()]) if want else 1.0
    if isinstance(want, float) and isinstance(got, float):
        return 1.0 if abs(want - got) < 1e-9 else 0.0
    if isinstance(want, str) and isinstance(got, str):
        # Containment earns partial credit: an answer that says "the Framework
        # 16 (32GB)" when asked for a laptop name has found the right thing and
        # phrased it differently, which is not the same kind of wrong as naming
        # the previous laptop.
        if want in got or got in want:
            return 0.6
    return 0.0


def _speed(latency_ms: float | None) -> float | None:
    if latency_ms is None:
        return None
    if latency_ms <= FAST_MS:
        return 1.0
    if latency_ms >= SLOW_MS:
        return 0.0
    return 1.0 - (latency_ms - FAST_MS) / (SLOW_MS - FAST_MS)


def _time(expected_month, actual_month) -> float | None:
    if expected_month is None:
        return None
    if actual_month is None:
        return 0.0
    try:
        drift = abs(int(expected_month) - int(actual_month))
    except (TypeError, ValueError):
        return 0.0
    # One month out still lands in the right part of the life; two does not.
    return 1.0 if drift == 0 else 0.5 if drift == 1 else 0.0


def _path(expected: list, actual) -> float | None:
    if not expected:
        return None
    if not actual:
        return 0.0
    if list(expected) == list(actual):
        return 1.0
    return _f1(expected, actual)


@dataclass
class QueryScore:
    query_id: str
    level: int
    kind: str
    subsystem: str
    axes: dict = field(default_factory=dict)
    declined: list = field(default_factory=list)
    answered: bool = True

    @property
    def percent(self) -> float:
        """Weighted over the axes that were actually scored."""
        live = {a: v for a, v in self.axes.items() if v is not None}
        if not live:
            return 0.0
        total = sum(WEIGHTS[a] for a in live)
        return 100.0 * sum(WEIGHTS[a] * v for a, v in live.items()) / total

    def to_dict(self) -> dict:
        return {"query_id": self.query_id, "level": self.level, "kind": self.kind,
                "subsystem": self.subsystem, "answered": self.answered,
                "axes": {a: (None if v is None else round(v, 3))
                         for a, v in self.axes.items()},
                "declined": self.declined, "percent": round(self.percent, 2)}


def score_one(query: dict, response: dict | None) -> QueryScore:
    """One query. `response` is None when the system did not answer at all."""
    result = QueryScore(query_id=query["id"], level=query.get("level", 0),
                        kind=query.get("kind", ""),
                        subsystem=query.get("subsystem", ""))
    if not response:
        # Not declined: a missing answer is a measured failure, and folding it
        # into "not applicable" would let a system score well by staying quiet.
        result.answered = False
        result.axes = {axis: 0.0 for axis in WEIGHTS}
        return result

    result.axes = {
        "answer": compare_answer(query["answer"], response.get("answer")),
        "evidence": _f1(query.get("evidence", []), response.get("evidence", []) or [])
        if query.get("evidence") else None,
        "time": _time(query.get("as_of_month"), response.get("as_of_month")),
        "path": _path(query.get("graph_path", []), response.get("graph_path")),
        "speed": _speed(response.get("latency_ms")),
    }
    result.declined = sorted(a for a, v in result.axes.items() if v is None)
    return result


def run(queries: list[dict], responses: dict[str, dict]) -> dict:
    """Score a whole suite. Returns per-query rows and the aggregate report."""
    scored = [score_one(q, responses.get(q["id"])) for q in queries]
    overall = statistics.mean([s.percent for s in scored]) if scored else None

    def group(key):
        buckets: dict = {}
        for s in scored:
            buckets.setdefault(getattr(s, key), []).append(s.percent)
        return {str(k): {"queries": len(v), "percent": round(statistics.mean(v), 2),
                         "grade": grade(statistics.mean(v))}
                for k, v in sorted(buckets.items(), key=lambda kv: str(kv[0]))}

    by_axis = {}
    for axis in WEIGHTS:
        values = [s.axes.get(axis) for s in scored if s.axes.get(axis) is not None]
        if values:
            by_axis[axis] = round(100.0 * statistics.mean(values), 2)

    unanswered = [s.query_id for s in scored if not s.answered]
    return {
        "overall": round(overall, 2) if overall is not None else None,
        "grade": grade(overall),
        "queries": len(scored),
        "unanswered": len(unanswered),
        "unanswered_ids": unanswered[:20],
        "weights": dict(WEIGHTS),
        "by_axis": by_axis,
        "by_level": group("level"),
        "by_subsystem": group("subsystem"),
        # The worst results, because an aggregate tells you there is a problem
        # and this tells you where to look.
        "worst": [s.to_dict() for s in
                  sorted(scored, key=lambda s: s.percent)[:15]],
        "scores": [s.to_dict() for s in scored],
    }


def render(report: dict) -> str:
    """The report as a human reads it."""
    lines = [f"SLDB score {report['overall']}%  —  {report['grade']}",
             f"  {report['queries']} queries, {report['unanswered']} unanswered"]
    lines.append("  axes: " + "  ".join(
        f"{axis} {value}%" for axis, value in sorted(report["by_axis"].items())))
    lines.append("  by level:")
    for level, row in report["by_level"].items():
        lines.append(f"     L{level}  {row['percent']:>6}%  {row['grade']:<22}"
                     f"({row['queries']} queries)")
    lines.append("  weakest queries:")
    for row in report["worst"][:5]:
        lines.append(f"     {row['query_id']}  L{row['level']}  "
                     f"{row['percent']:>6}%  {row['kind']}")
    return "\n".join(lines)
