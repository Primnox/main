"""What the sandbox can actually run, probed rather than assumed.

Skills need to pick an implementation *before* they start, not discover a
missing runtime halfway through generating a document. The official pptx and
docx skills build their output with pptxgenjs / docx-js (Node); when Node
isn't usable the same deliverable is still reachable via python-pptx /
python-docx, at lower fidelity. Choosing between those is only possible if
something knows which runtimes work.

Everything here is probed INSIDE the sandbox, never by importing into
Primnox's own process. That distinction is the entire point: on this machine
`import reportlab` succeeds in Primnox and fails in the sandbox, because
Pillow's native _imaging extension can't initialise under the sandbox
account. Host-side availability predicts nothing. The same restriction takes
out libffi (_ctypes), libcrypto (_ssl/_hashlib) and Node's V8 — see the
module docstring in code_exec.py for the isolation boundary itself, and
docs/sandbox-runtime-limitations.md for the open investigation.

Results are cached for the process lifetime: a probe costs two sandboxed
executions, and nothing it measures changes without a restart.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field

from logger import get_logger

log = get_logger("runtime_capabilities")

# capability name -> the module whose import actually proves it.
#
# Deliberately NOT the top-level package in every case. `import PIL` succeeds
# in the sandbox and tells you nothing: Pillow's package __init__ is pure
# Python, and the native extension that does all the work (PIL._imaging) is
# what fails. Probing the shallow name reported Pillow as available and would
# have routed work straight into a runtime crash. Probe the piece that breaks.
_PROBED_LIBRARIES = {
    "python-pptx": "pptx",                    # PowerPoint fallback for the pptx skill
    "python-docx": "docx",                    # Word fallback for the docx skill
    "openpyxl": "openpyxl",                   # xlsx skill
    "reportlab": "reportlab.pdfgen.canvas",   # pdf generation
    "pypdf": "pypdf",                         # pdf reading
    "pillow": "PIL._imaging",                 # the native half, not the package
    "markitdown": "markitdown",               # how the official skills read documents
}

_PYTHON_PROBE = (
    "import json\n"
    "r = {}\n"
    f"for name, mod in {dict(_PROBED_LIBRARIES)!r}.items():\n"
    "    try:\n"
    "        __import__(mod)\n"
    "        r[name] = True\n"
    "    except Exception:\n"
    "        r[name] = False\n"
    "print('CAPS:' + json.dumps(r))\n"
)

_NODE_PROBE = (
    "const r = {};\n"
    "for (const m of ['pptxgenjs', 'docx']) {\n"
    "  try { require(m); r[m] = true; } catch (e) { r[m] = false; }\n"
    "}\n"
    "console.log('CAPS:' + JSON.stringify(r));\n"
)

_PROBE_TIMEOUT = 60  # generous: a cold node start on a busy machine is slow


@dataclass(frozen=True)
class Capabilities:
    sandbox: bool = False
    python: bool = False
    node: bool = False
    libraries: dict = field(default_factory=dict)   # python lib -> usable in sandbox
    node_modules: dict = field(default_factory=dict)  # npm module -> requireable
    notes: tuple = ()

    def has(self, name: str) -> bool:
        return bool(self.libraries.get(name) or self.node_modules.get(name))

    def summary(self) -> str:
        """Human-readable, and also what gets pasted into skill prompts."""
        if not self.sandbox:
            return "Sandboxed execution is unavailable — no code can be run."
        lines = [f"Python       {_tick(self.python)}", f"Node.js      {_tick(self.node)}"]
        for name, ok in sorted(self.libraries.items()):
            lines.append(f"{name:<12} {_tick(ok)}")
        for name, ok in sorted(self.node_modules.items()):
            lines.append(f"{name:<12} {_tick(ok)}")
        return "\n".join(lines)


def _tick(ok: bool) -> str:
    return "available" if ok else "UNAVAILABLE"


_cache: Capabilities | None = None
_lock = threading.Lock()


def detect(force: bool = False) -> Capabilities:
    global _cache
    with _lock:
        if _cache is not None and not force:
            return _cache
        _cache = _probe()
        log.info(f"Sandbox runtime capabilities:\n{_cache.summary()}")
        return _cache


def invalidate() -> None:
    """Drops the cache — call after provisioning or installing a runtime."""
    global _cache
    with _lock:
        _cache = None


def _probe() -> Capabilities:
    import code_exec
    from sandbox_account import sandbox_account_configured

    if not sandbox_account_configured():
        return Capabilities(notes=("sandbox account not provisioned",))

    libraries = _probe_one("python", _PYTHON_PROBE)
    python_ok = libraries is not None

    node_modules = _probe_one("node", _NODE_PROBE)
    node_ok = node_modules is not None

    notes = []
    if not node_ok:
        notes.append(
            "Node.js could not run in the sandbox; JavaScript document "
            "generation (pptxgenjs, docx-js) is unavailable."
        )
    if python_ok and not libraries.get("pillow", False):
        notes.append(
            "Pillow's native extension cannot initialise in the sandbox, so "
            "anything that renders images there will fail — including "
            "python-pptx and reportlab's image paths."
        )

    return Capabilities(
        sandbox=True,
        python=python_ok,
        node=node_ok,
        libraries=libraries or {},
        node_modules=node_modules or {},
        notes=tuple(notes),
    )


def _probe_one(language: str, probe_code: str) -> dict | None:
    """Returns the probe's dict, or None when the runtime itself is unusable.

    A probe failure is a normal outcome, not an error: Node genuinely does
    not start under the sandbox account on this machine. It is logged at info
    so a capability that silently disappeared is still traceable.
    """
    import code_exec

    label = language
    try:
        result = code_exec.run_probe(language, probe_code, timeout=_PROBE_TIMEOUT)
    except Exception as e:
        log.info(f"{label} capability probe raised: {e}")
        return None

    if not result.get("success"):
        detail = (result.get("error") or result.get("stderr") or "").strip()
        log.info(f"{label} unavailable in sandbox (rc={result.get('return_code')}) {detail[:200]}")
        return None

    for line in (result.get("stdout") or "").splitlines():
        if line.startswith("CAPS:"):
            try:
                return json.loads(line[len("CAPS:"):])
            except json.JSONDecodeError:
                break
    log.info(f"{label} probe produced no parsable capability line")
    return None
