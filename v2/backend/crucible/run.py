"""Crucible runner.

    python crucible/run.py                 # full run
    python crucible/run.py --fast          # reduced scale, for a commit hook
    python crucible/run.py --compare prev.json

Runs against a THROWAWAY database, always. A suite that deliberately wounds
turns, abandons jobs and imports 50,000 nodes must never be pointed at a real
one, and making that a flag would eventually make it a mistake.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os  # noqa: E402

os.environ.setdefault("PRIMNOX2_AUTO_APPROVE", "all")
_HOME = Path(tempfile.mkdtemp(prefix="crucible-"))
os.environ["PRIMNOX2_HOME"] = str(_HOME)

from primnox2 import paths                      # noqa: E402
from primnox2.storage import db                 # noqa: E402

from crucible import VERSION, manifest, report, scoring   # noqa: E402


@dataclass
class Context:
    """Everything a module needs, and the knobs a fast run turns down."""
    root: Path
    seed: int = 20260815
    fast: bool = False
    pack: manifest.Pack | None = None
    scales: dict = field(default_factory=dict)

    def scale(self, name: str, full: int) -> int:
        """Reduced sizes for a fast run, recorded so the report says which ran.

        A fast run is explicitly NOT a certification — the report labels it, so
        a 9.8 from a reduced run can never be mistaken for the real thing.
        """
        value = max(1, full // 20) if self.fast else full
        self.scales[name] = value
        return value


def _prepare(root: Path) -> None:
    paths.configure(root)
    db.configure(root / "primnox.db")
    db.init()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Primnox Crucible")
    ap.add_argument("--fast", action="store_true", help="reduced scale")
    ap.add_argument("--seed", type=int, default=20260815)
    ap.add_argument("--out", default=None, help="directory for the report and pack")
    ap.add_argument("--compare", default=None, help="a previous crucible.json")
    args = ap.parse_args(argv)

    out_dir = Path(args.out) if args.out else _HOME / "crucible-out"
    out_dir.mkdir(parents=True, exist_ok=True)

    _prepare(_HOME)

    ctx = Context(root=_HOME, seed=args.seed, fast=args.fast,
                  pack=manifest.Pack(root=out_dir / "pack", seed=args.seed))

    from crucible import modules

    print(f"Primnox Crucible {VERSION} — {'FAST' if args.fast else 'FULL'} "
          f"run, seed {args.seed}")
    print(f"  sandboxed home: {_HOME}")

    results: list[scoring.ModuleResult] = []
    for module in modules.ORDER:
        name = getattr(module, "NAME", module.__name__)
        started = time.perf_counter()
        try:
            produced = module.run(ctx)
        except Exception:
            key = getattr(module, "KEY", module.__name__)
            failed = scoring.ModuleResult(key=key, name=name)
            failed.status = "ERROR"
            failed.reason = traceback.format_exc(limit=6)
            failed.duration_s = time.perf_counter() - started
            results.append(failed)
            print(f"  {key} {name}: ERRORED")
            continue

        for r in (produced if isinstance(produced, list) else [produced]):
            results.append(r)
            if r.status == scoring.NOT_APPLICABLE:
                print(f"  {r.key} {r.name}: n/a")
            else:
                avg = r.average
                print(f"  {r.key} {r.name}: {avg:.1f}/10 "
                      f"({len(r.findings)} findings, {r.duration_s:.1f}s)"
                      if avg is not None else f"  {r.key} {r.name}: no score")

    summary = scoring.summarise(results)
    payload = {
        "crucible_version": VERSION,
        "seed": args.seed,
        "mode": "fast" if args.fast else "full",
        "scales": ctx.scales,
        "summary": summary,
        "modules": [r.to_dict() for r in results],
    }

    (out_dir / "crucible.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if ctx.pack:
        ctx.pack.write()

    md = report.render(payload,
                       comparison=manifest.compare(
                           json.loads(Path(args.compare).read_text(encoding="utf-8")),
                           payload) if args.compare else None)
    (out_dir / "CRUCIBLE_REPORT.md").write_text(md, encoding="utf-8")

    print()
    print(f"  overall {summary['overall']}  ->  {summary['verdict']}")
    print(f"  findings: {summary['findings']}")
    print(f"  report:   {out_dir / 'CRUCIBLE_REPORT.md'}")

    # Non-zero only on a critical finding. A suite that fails a build for a
    # medium finding gets disabled within a week.
    return 1 if summary["findings"].get(scoring.CRITICAL) else 0


if __name__ == "__main__":
    raise SystemExit(main())
