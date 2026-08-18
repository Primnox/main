"""Modules whose subsystem does not exist in V2.

These are reported, not silently omitted. A certification suite that quietly
drops the modules it cannot run produces a score that looks like coverage and
is really selection — and the reader has no way to tell.

Each records what would be tested, and what has to exist first.
"""
from __future__ import annotations

from ..scoring import ModuleResult

ABSENT = [
    ("M02", "Presentation Torture (250 slides)",
     "Partially covered by tests/deck_audit.py, which grades a generated deck "
     "mechanically against a design system. Not run here because the 250-slide, "
     "12-theme variant needs a model to author the CONTENT — the builder can lay "
     "out 250 slides today, but a deck of generated filler measures the layout "
     "engine twice and the system under test not at all."),

    ("M03", "Document Torture (800-page PDF, OCR)",
     "Asset Service extracts PDF text via pypdf, so page count and footnote "
     "retrieval are testable. OCR is not: _extract_text returns "
     "{'ocr_required': True} and stops — there is no OCR backend in V2. Scanned "
     "pages, rotated pages and handwriting cannot be certified against a "
     "subsystem that does not exist."),

    ("M04", "Spreadsheet Torture (100k rows, pivots, macros)",
     "There is no spreadsheet service. openpyxl and xlsxwriter are available "
     "INSIDE the sandbox, so a model can generate a workbook, but Primnox has no "
     "ingestion path that reads one back — no sheet parsing, no formula "
     "evaluation, no pivot handling. Nothing to certify."),

    ("M05", "Workspace Torture (rename without breaking imports)",
     "Workspaces exist and are versioned, but the refactor this module asks for "
     "needs symbol-level rewriting across a tree. The knowledge graph now "
     "provides the call and import edges that would make it possible; the "
     "operation itself is unimplemented."),

    ("M08", "Sandbox Torture (compile, npm, infinite loop, fork bomb)",
     "The sandbox is real — Windows AppContainer with Job Objects — and timeout, "
     "cleanup and log preservation are covered in tests/test_l4_chaos.py. Left "
     "out of Crucible deliberately: fork-bomb and memory-exhaustion cases run "
     "unsandboxed against the host if isolation fails to start, and a "
     "certification suite must not be the thing that takes the machine down. "
     "Needs a disposable VM before it can be run honestly."),

    ("M09", "Browser Torture (40 tabs, downloads, session isolation)",
     "V2 has no browser subsystem. Nothing to test."),

    ("M12", "Markdown Torture",
     "The torture document is generated (crucible.generate.markdown_torture) and "
     "is in the pack, but rendering happens in react-markdown in the browser. "
     "Certifying it needs the frontend driven and looked at; asserting from the "
     "backend would measure the string, not the render."),

    ("M13", "Code Torture (500 files, 60k LOC, circular imports)",
     "The repository generator exists and produces the pathologies. Folded into "
     "M06 rather than run separately: extraction is the same code path, and "
     "reporting it twice would double-count one result."),

    ("M14", "Search Torture (synonyms, renamed entities)",
     "Asset search is substring LIKE and memory search is word overlap. Both "
     "would fail a synonym probe by construction, which is a known design state "
     "rather than a finding — asset_embeddings exists precisely for this upgrade "
     "and is unused. Scoring it would report a decision as a defect."),

    ("M17", "Small Model Torture (consistency across 300 files)",
     "Needs a live model and hours of generation. The retrieval half — whether "
     "the runtime PUTS the right material in front of a small model — is what "
     "M01 and M06 measure, and it is the half Primnox controls."),

    ("M18", "Accessibility Torture",
     "Contrast is enforced for generated documents (test_every_theme_meets_"
     "contrast, which caught two real WCAG failures). The application UI needs a "
     "screen reader and keyboard walkthrough by a person."),

    ("M19", "Export Torture (PDF, DOCX, PPTX, XLSX, ZIP)",
     "PPTX is covered by deck_audit. Report (PDF) and Doc (DOCX) builders exist "
     "but have no equivalent auditor, so 'formatting preserved' has no measure. "
     "XLSX and ZIP have no builder at all."),

    ("M20", "Ultimate Scenario (8-hour session)",
     "Composes every module above, several of which cannot run. Meaningful only "
     "once the absent subsystems exist; running a partial version would produce "
     "a number that reads as an end-to-end result and is not one."),
]


def run(ctx) -> list[ModuleResult]:
    out = []
    for key, name, reason in ABSENT:
        r = ModuleResult(key=key, name=name)
        r.skip(reason)
        out.append(r)
    return out
