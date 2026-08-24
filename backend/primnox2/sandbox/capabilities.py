"""What the sandbox can actually do — probed inside it, not assumed.

A model that doesn't know `reportlab` is available says "I can't generate PDF
files directly" and hands back HTML instead. That is a capability gap caused
purely by missing information, and it is fixed by telling it.

Two rules carried over from V1's `runtime_capabilities`, both learned the hard
way:

  Probe INSIDE the sandbox. The host interpreter having a library proves
  nothing about the sandboxed one — different ACLs, different environment.

  Probe the module that actually breaks. `import PIL` succeeds even when
  Pillow's native extension cannot load; `import PIL._imaging` is the one that
  tells the truth.

The result is cached on disk because probing costs a full sandbox launch, and
the answer only changes when the environment does.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import paths

# module to import → the name a model would recognise
PROBES = {
    "reportlab": "reportlab (PDF generation)",
    "PIL._imaging": "Pillow (image processing)",
    "pypdf": "pypdf (read/merge PDFs)",
    "docx": "python-docx (Word documents)",
    "pptx": "python-pptx (PowerPoint)",
    "openpyxl": "openpyxl (Excel)",
    "xlsxwriter": "xlsxwriter (Excel writing)",
    "pandas": "pandas (dataframes)",
    "numpy": "numpy",
    "matplotlib": "matplotlib (charts)",
    "bs4": "beautifulsoup4 (HTML parsing)",
    "lxml": "lxml (XML)",
}

CACHE_TTL_S = 7 * 24 * 3600
_memo: dict | None = None


def _cache_path() -> Path:
    d = paths.root() / "sandbox"
    d.mkdir(parents=True, exist_ok=True)
    return d / ".capabilities.json"


def _build_probe() -> str:
    modules = json.dumps(sorted(PROBES))
    return (
        "import importlib, json\n"
        f"mods = {modules}\n"
        "out = {}\n"
        "for m in mods:\n"
        "    try:\n"
        "        importlib.import_module(m)\n"
        "        out[m] = True\n"
        "    except Exception:\n"
        "        out[m] = False\n"
        "print('CAPS:' + json.dumps(out))\n"
    )


def detect(force: bool = False) -> dict[str, bool]:
    """Return {module: available}. Cached in memory, then on disk."""
    global _memo
    if _memo is not None and not force:
        return _memo

    cache = _cache_path()
    if not force and cache.is_file():
        try:
            blob = json.loads(cache.read_text(encoding="utf-8"))
            if time.time() - blob.get("at", 0) < CACHE_TTL_S:
                _memo = blob["capabilities"]
                return _memo
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    from . import manager, permissions

    result = manager.execute(
        code=_build_probe(), runtime="python",
        manifest=permissions.manifest_for("python", permissions.SAFE, timeout_s=120),
    )
    caps = {m: False for m in PROBES}
    for line in (result.get("stdout") or "").splitlines():
        if line.startswith("CAPS:"):
            try:
                caps.update(json.loads(line[5:]))
            except json.JSONDecodeError:
                pass
            break

    _memo = caps
    try:
        cache.write_text(json.dumps({"at": time.time(), "capabilities": caps}),
                         encoding="utf-8")
    except OSError:
        pass
    return caps


def available_names() -> list[str]:
    return [label for mod, label in PROBES.items() if detect().get(mod)]


def describe() -> str:
    """One line for the system prompt, or empty if nothing could be probed.

    Empty rather than a guess: telling a model a library exists when it does
    not produces a confident failure halfway through a workflow, which is worse
    than it choosing a different approach up front.
    """
    names = available_names()
    if not names:
        return ""
    return (
        "Libraries already installed in the sandbox — use them directly, and do "
        "not claim you cannot produce these formats:\n  " + ", ".join(names)
    )
