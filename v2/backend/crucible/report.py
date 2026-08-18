"""The Crucible Report.

Written to read like an internal engineering audit: what broke, how to reproduce
it, what probably causes it, which subsystem owns the fix. Not a bug list — a
bug list tells you what happened, an audit tells you what to do.

Findings lead. A report that opens with a score invites the reader to stop
there, and the score is the least useful thing in the document.
"""
from __future__ import annotations

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _findings(payload: dict) -> list[dict]:
    out = []
    for module in payload["modules"]:
        for f in module.get("findings", []):
            out.append({**f, "module_name": module["name"]})
    return sorted(out, key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["module"]))


def render(payload: dict, comparison: dict | None = None) -> str:
    s = payload["summary"]
    findings = _findings(payload)
    lines: list[str] = []
    add = lines.append

    add("# Primnox Crucible — Certification Report")
    add("")
    add(f"`crucible {payload['crucible_version']}` · seed `{payload['seed']}` · "
        f"mode **{payload['mode']}**")
    if payload["mode"] == "fast":
        add("")
        add("> **This is a reduced-scale run and is not a certification.** "
            "Artifact sizes were divided by 20 to keep the run short; a score "
            "from a fast run says the suite executes, not that the system passes.")
    add("")

    # ── verdict ──────────────────────────────────────────────────────────
    add("## Verdict")
    add("")
    add(f"**{s['verdict']}** — overall {s['overall']}/10 across "
        f"{s['modules_run']} executed modules.")
    add("")
    add(f"{s['total_findings']} findings: "
        f"{s['findings'].get('critical', 0)} critical · "
        f"{s['findings'].get('high', 0)} high · "
        f"{s['findings'].get('medium', 0)} medium · "
        f"{s['findings'].get('low', 0)} low.")
    add("")
    add(f"{s['modules_not_applicable']} modules were **not applicable** — their "
        f"subsystem does not exist in V2. They are listed in full at the end "
        f"rather than omitted, because a score computed over a hidden selection "
        f"is not a score.")
    add("")

    if s.get("by_axis"):
        add("| Axis | Score |")
        add("|---|---|")
        for axis, value in s["by_axis"].items():
            add(f"| {axis.replace('_', ' ').title()} | {value}/10 |")
        add("")

    # ── comparison ───────────────────────────────────────────────────────
    if comparison:
        add("## Change since the last run")
        add("")
        add(f"Overall {comparison['overall_before']} → {comparison['overall_after']}")
        add("")
        if comparison["regressions"]:
            add("**Regressions**")
            add("")
            for r in comparison["regressions"]:
                add(f"- `{r['module']}` {r['before']} → {r['after']} ({r['delta']})")
            add("")
        if comparison["new_findings"]:
            add("**New findings**")
            add("")
            for f in comparison["new_findings"]:
                add(f"- {f}")
            add("")
        if comparison["fixed_findings"]:
            add("**Resolved**")
            add("")
            for f in comparison["fixed_findings"]:
                add(f"- {f}")
            add("")

    # ── findings ─────────────────────────────────────────────────────────
    add("## Findings")
    add("")
    if not findings:
        add("None. Given the modules that ran, this means the suite is not "
            "yet hard enough — not that the system is finished.")
        add("")
    for i, f in enumerate(findings, 1):
        add(f"### {i}. {f['title']}")
        add("")
        add(f"**{f['severity'].upper()}** · owner: **{f['owner']}** · "
            f"found by {f['module']} ({f['module_name']})")
        add("")
        add(f"**What happened.** {f['what_happened']}")
        add("")
        if f.get("evidence"):
            add(f"**Evidence.** `{f['evidence']}`")
            add("")
        add(f"**Reproduction.**")
        add("")
        add("```")
        add(f["reproduction"])
        add("```")
        add("")
        if f.get("probable_cause"):
            add(f"**Probable cause.** {f['probable_cause']}")
            add("")
        if f.get("suggested_fix"):
            add(f"**Suggested fix.** {f['suggested_fix']}")
            add("")

    # ── modules ──────────────────────────────────────────────────────────
    add("## Modules executed")
    add("")
    add("| Module | Score | Findings | Time |")
    add("|---|---|---|---|")
    for m in payload["modules"]:
        if m["status"] != "RUN":
            continue
        avg = m["average"]
        add(f"| {m['key']} {m['name']} | {avg:.1f}/10 | "
            f"{len(m['findings'])} | {m['duration_s']}s |")
    add("")

    for m in payload["modules"]:
        if m["status"] != "RUN" or not m.get("measurements"):
            continue
        add(f"### {m['key']} — measurements")
        add("")
        add("```json")
        import json as _json
        add(_json.dumps(m["measurements"], indent=2)[:2400])
        add("```")
        add("")

    errored = [m for m in payload["modules"] if m["status"] == "ERROR"]
    if errored:
        add("## Modules that errored")
        add("")
        add("A module that crashes is a defect in the suite, not a result. "
            "These produced no score.")
        add("")
        for m in errored:
            add(f"### {m['key']} {m['name']}")
            add("")
            add("```")
            add(m["reason"].strip()[:1200])
            add("```")
            add("")

    add("## Not applicable")
    add("")
    add("Each of these was specified, and each targets a subsystem V2 does not "
        "have. Scoring them — as zero, or as a pass because nothing failed — "
        "would make the overall number describe scope rather than quality.")
    add("")
    for m in payload["modules"]:
        if m["status"] != "NOT_APPLICABLE":
            continue
        add(f"**{m['key']} — {m['name']}**")
        add("")
        add(m["reason"])
        add("")

    add("## Replay pack")
    add("")
    add("Every artifact is generated from the seed above and hashed into "
        "`pack/manifest.json`. A later build reruns the identical bytes, so a "
        "score change is a change in the system rather than a change in the "
        "input. `crucible.manifest.verify()` re-hashes the pack and reports "
        "drift; `--compare` diffs two runs and lists regressions, new findings "
        "and resolved ones.")
    add("")

    return "\n".join(lines)
