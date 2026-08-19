"""PDF ingestion quality — does Primnox actually read what's in a PDF, and
is it honest when it can't?

Everything here runs against REAL PDFs generated with reportlab in fixtures
(no binaries are committed) and against the REAL extraction code Primnox
ships. There is no mocked "pretend the model summarised it" layer: a
summary can only be as good as the text handed to the model, so these tests
pin the text.

Two things are deliberately unusual and worth explaining:

1. `server_pdf_ingest()` executes the actual `.pdf` branch out of
   `server.py`'s `/message` handler rather than reimplementing it. Importing
   `server` pulls in the whole backend (torch, audio devices, background
   threads) and writes into the user's real `%APPDATA%/primnox_extension` —
   the same reason `test_cors_origins.py` parsed `server.py` as text instead
   of importing it. Lifting the branch out with `ast` keeps the assertions
   behavioural (real pypdf, real truncation, real f-string) while importing
   nothing.

2. Several tests are `xfail(strict=True)`. Those are not aspirational
   wishes — each one is a capability the pipeline genuinely does not have
   today, written as the assertion that *would* pass if it did. Strict mode
   means the day someone implements it the test turns red and has to be
   un-xfailed, so the gap can't quietly stay open or quietly get fixed
   without notice.
"""

import ast
import io
import re
import textwrap
from pathlib import Path

import pytest

reportlab = pytest.importorskip("reportlab")
pypdf = pytest.importorskip("pypdf")

from pypdf import PdfReader  # noqa: E402

SERVER_PY = Path(__file__).resolve().parent.parent / "server.py"


# ─────────────────────────────────────────────────────────────────────────
# Running the real ingest code without importing the real backend
# ─────────────────────────────────────────────────────────────────────────

def _pdf_branch_source(function_name: str) -> str:
    """The body of the `if <...>.endswith(".pdf")` branch inside the named
    server.py handler, as source text.

    Located by AST rather than line number so it survives edits above it.
    """
    src = SERVER_PY.read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        is_func = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if not is_func or node.name != function_name:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.If):
                continue
            test_src = ast.get_source_segment(src, sub.test) or ""
            if ".pdf" not in test_src:
                continue
            # Sliced by line range, not stitched from per-statement source
            # segments: get_source_segment strips the first line's indent
            # only, so joining multi-line statements yields inconsistent
            # indentation that won't compile.
            block = lines[sub.body[0].lineno - 1:sub.body[-1].end_lineno]
            return textwrap.dedent("\n".join(block))
    raise AssertionError(
        f"No `.pdf` branch found in {function_name}() — server.py's PDF "
        "ingestion moved or was removed; these tests need re-pointing."
    )


def server_pdf_ingest(filename: str, content: bytes) -> str:
    """Run `/message`'s real PDF branch and return the string it appends to
    `extracted_parts` — i.e. exactly what the model gets told about the file."""
    parts: list[str] = []
    namespace = {"io": io, "filename": filename, "content": content,
                 "lower": filename.lower(), "extracted_parts": parts}
    exec(compile(_pdf_branch_source("post_message"), "<server.py:/message>", "exec"),
         namespace)
    assert len(parts) == 1, "the branch should contribute exactly one part"
    return parts[0]


def notes_batch_pdf_ingest(filename: str, content: bytes):
    """Same, for `/api/notes/generate-batch`. Returns the parsed_files entry,
    or raises whatever the branch raises (it validates, unlike /message)."""
    parsed: list[dict] = []

    class _F:
        pass

    f = _F()
    f.filename = filename
    namespace = {"io": io, "filename": filename.lower(), "content": content,
                 "parsed_files": parsed, "f": f}
    exec(compile(_pdf_branch_source("generate_batch_notes"), "<server.py:/notes>", "exec"),
         namespace)
    return parsed[0]


def ingest_cap() -> int:
    """The character cap `/message` applies to extracted PDF text, read out
    of the branch source so the tests can never drift from the real value."""
    match = re.search(r"pdf_text\[:(\d+)\]", _pdf_branch_source("post_message"))
    assert match, "`/message` no longer slices pdf_text — cap assertions need updating"
    return int(match.group(1))


def full_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures — every PDF is built here, at test time, from code
# ─────────────────────────────────────────────────────────────────────────

SIMPLE_FACTS = [
    "The Kestrel-7 rover landed in Ares Planitia on 14 March 2031.",
    "Its primary instrument is a neutron spectrometer named HALCYON.",
    "Mission cost was 412 million euros, 8 percent under the approved budget.",
    "Sample return is scheduled for the fourth quarter of 2034.",
]

TABLE_ROWS = [
    ("Q1 2024", "1,240,000", "880,000", "360,000"),
    ("Q2 2024", "1,515,000", "910,000", "605,000"),
    ("Q3 2024", "1,702,500", "1,004,000", "698,500"),
    ("Q4 2024", "2,031,000", "1,150,000", "881,000"),
]
TABLE_HEADER = ("Quarter", "Revenue", "Expenses", "Net")

HUGE_PAGE_COUNT = 220
NEEDLE_PAGE = 173
NEEDLE = "ZEPHYR-CLAUSE-9931 indemnifies the licensor against consequential loss."


@pytest.fixture(scope="module")
def simple_pdf(tmp_path_factory) -> bytes:
    """A short, ordinary text PDF — the easy case that must never regress."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    path = tmp_path_factory.mktemp("pdfs") / "simple.pdf"
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 720, "Kestrel-7 Mission Briefing")
    c.setFont("Helvetica", 11)
    for i, line in enumerate(SIMPLE_FACTS):
        c.drawString(72, 680 - i * 22, line)
    c.showPage()
    c.save()
    return path.read_bytes()


@pytest.fixture(scope="module")
def scanned_pdf(tmp_path_factory) -> bytes:
    """An image-only PDF: the words exist as pixels, not as text objects.
    This is what a phone photo or a flatbed scan of a contract looks like."""
    PIL = pytest.importorskip("PIL")  # noqa: F841
    from PIL import Image, ImageDraw
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    tmp = tmp_path_factory.mktemp("scans")
    img = Image.new("RGB", (1400, 700), "white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 60), "CONFIDENTIAL MEMO - scanned page", fill="black")
    draw.text((40, 160), "Revenue exceeded projections by 12 percent.", fill="black")
    draw.text((40, 260), "Do not distribute outside the finance group.", fill="black")
    png = tmp / "scan.png"
    img.save(png)

    path = tmp / "scanned.pdf"
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.drawImage(ImageReader(str(png)), 46, 400, width=520, height=260)
    c.showPage()
    c.save()
    return path.read_bytes()


@pytest.fixture(scope="module")
def table_pdf(tmp_path_factory) -> bytes:
    """A financial table with a header row and four data rows."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    path = tmp_path_factory.mktemp("tables") / "financials.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=LETTER)
    styles = getSampleStyleSheet()
    table = Table([list(TABLE_HEADER)] + [list(r) for r in TABLE_ROWS])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
    ]))
    doc.build([
        Paragraph("Acme Holdings - FY2024 Financial Summary", styles["Title"]),
        Spacer(1, 14),
        table,
    ])
    return path.read_bytes()


@pytest.fixture(scope="module")
def two_column_pdf(tmp_path_factory) -> bytes:
    """A genuine two-frame newspaper layout. Every left-column line is
    tagged LEFTMARK<nn>, every right-column line RIGHTMARK<nn>, so reading
    order is checkable exactly rather than by eye."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                    Paragraph)

    width, height = LETTER
    col_width = (width - 120) / 2
    path = tmp_path_factory.mktemp("columns") / "twocol.pdf"
    doc = BaseDocTemplate(str(path), pagesize=LETTER)
    doc.addPageTemplates([PageTemplate(id="two", frames=[
        Frame(50, 50, col_width, height - 100, id="left"),
        Frame(50 + col_width + 20, 50, col_width, height - 100, id="right"),
    ])])
    body = getSampleStyleSheet()["BodyText"]
    story = [
        Paragraph(f"LEFTMARK{i:02d} left column paragraph {i}, with enough "
                  "filler text to wrap across several lines of the frame.", body)
        for i in range(1, 13)
    ] + [
        Paragraph(f"RIGHTMARK{i:02d} right column paragraph {i}, with enough "
                  "filler text to wrap across several lines of the frame.", body)
        for i in range(1, 13)
    ]
    doc.build(story)
    return path.read_bytes()


@pytest.fixture(scope="module")
def huge_pdf(tmp_path_factory) -> bytes:
    """220 pages, with one unique needle buried on page 173 — the case where
    'just send the whole document' is not an option."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    path = tmp_path_factory.mktemp("huge") / "huge.pdf"
    c = canvas.Canvas(str(path), pagesize=LETTER)
    for page in range(1, HUGE_PAGE_COUNT + 1):
        c.setFont("Helvetica", 10)
        c.drawString(72, 740, f"PAGEMARK{page:04d} - Master Services Agreement")
        for line in range(30):
            y = 710 - line * 20
            if page == NEEDLE_PAGE and line == 12:
                c.drawString(72, y, NEEDLE)
            else:
                c.drawString(72, y, f"Clause {page}.{line}: standard boilerplate "
                                    "text repeated for bulk.")
        c.showPage()
    c.save()
    return path.read_bytes()


# ─────────────────────────────────────────────────────────────────────────
# 13. Simple PDF — the summary has to be about what is actually in the file
# ─────────────────────────────────────────────────────────────────────────

class TestSimpleTextPdf:
    def test_extraction_returns_the_real_sentences(self, simple_pdf):
        text = full_text(simple_pdf)
        for fact in SIMPLE_FACTS:
            assert fact in " ".join(text.split()), f"lost from extraction: {fact!r}"

    def test_distinctive_facts_survive_verbatim(self, simple_pdf):
        """The anti-hallucination anchor. A model handed this text can only
        say '412 million euros' because it was there; if extraction dropped
        the numbers, any figure in the summary would be invented."""
        text = " ".join(full_text(simple_pdf).split())
        assert "412 million euros" in text
        assert "Kestrel-7" in text
        assert "HALCYON" in text
        assert "14 March 2031" in text

    def test_nothing_invented_by_extraction(self, simple_pdf):
        text = full_text(simple_pdf)
        # Numbers the document does not contain must not appear. Extraction
        # inventing digits would be a far worse bug than dropping them.
        for absent in ("512 million", "2035", "Kestrel-8"):
            assert absent not in text

    def test_ingest_path_forwards_the_content_to_the_model(self, simple_pdf):
        """Extraction being right is useless if `/message` drops it."""
        part = server_pdf_ingest("briefing.pdf", simple_pdf)
        assert part.startswith("[File: briefing.pdf]")
        for fact in SIMPLE_FACTS:
            assert fact in " ".join(part.split())

    def test_small_pdf_is_not_truncated(self, simple_pdf):
        part = server_pdf_ingest("briefing.pdf", simple_pdf)
        assert len(full_text(simple_pdf)) < ingest_cap()
        assert "truncated" not in part.lower()


# ─────────────────────────────────────────────────────────────────────────
# 14. Scanned PDF — OCR it, or say plainly that you can't. Never both silent
#     and empty.
# ─────────────────────────────────────────────────────────────────────────

class TestScannedImageOnlyPdf:
    def test_the_fixture_really_is_image_only(self, scanned_pdf):
        """Guards the rest of the class: if reportlab ever started emitting
        a text layer here, the honesty tests below would pass vacuously."""
        reader = PdfReader(io.BytesIO(scanned_pdf))
        assert len(reader.pages) == 1
        assert (reader.pages[0].extract_text() or "").strip() == ""
        assert len(list(reader.pages[0].images)) == 1, "expected one embedded raster"

    def test_ocr_is_installed_but_no_pdf_path_uses_it(self):
        """The sharp end of this gap: Primnox already ships an OCR engine.

        `easyocr` is a hard requirement (requirements.txt) and `spatial_engine.py`
        reads text off the screen with it. Nothing in the PDF pipeline ever
        calls it, so a scanned document is unreadable for want of wiring, not
        for want of a dependency.
        """
        import importlib.util
        assert importlib.util.find_spec("easyocr") is not None, (
            "easyocr is a declared requirement; if it's gone, the OCR gap "
            "described here has changed shape and needs re-documenting.")

        # Checked as an import, not a substring: server.py's PDF branch now
        # *mentions* easyocr in a comment explaining why it isn't used.
        imported = set()
        for node in ast.walk(ast.parse(SERVER_PY.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "easyocr" not in imported, (
            "server.py now imports OCR — wire it into the PDF branch and "
            "drop the xfail on the OCR test below.")

    def test_ingest_does_not_claim_the_document_is_empty(self, scanned_pdf):
        """THE failure this class exists for.

        A user attaches a scanned contract and asks "what does it say?". If
        `/message` hands the model `[File: contract.pdf]` and nothing else,
        the model has no way to know the difference between "this PDF is
        blank" and "I could not read this PDF", and will confidently answer
        as though it read a blank page.
        """
        part = server_pdf_ingest("contract.pdf", scanned_pdf)
        body = part.split("]", 1)[1].strip()
        assert body != "", (
            "SILENT EMPTY INGEST: /message forwarded an image-only PDF as "
            f"{part!r} — no text and no explanation. The model cannot tell "
            "this apart from a genuinely blank document."
        )

    def test_ingest_says_what_it_could_not_do(self, scanned_pdf):
        part = server_pdf_ingest("contract.pdf", scanned_pdf).lower()
        assert any(word in part for word in ("no extractable text", "scanned",
                                             "image-only", "could not")), (
            f"the ingest note gives the model no diagnosis: {part!r}")

    def test_notes_batch_endpoint_already_refuses_rather_than_lying(self, scanned_pdf):
        """/api/notes/generate-batch got this right first — it raises instead
        of generating notes from nothing. Pinned so it stays that way, and as
        the in-repo precedent for the behaviour asserted above."""
        with pytest.raises(ValueError, match="No text could be extracted"):
            notes_batch_pdf_ingest("contract.pdf", scanned_pdf)

    @pytest.mark.xfail(strict=True, reason=(
        "GAP: no PDF OCR path. easyocr is installed and already used by "
        "spatial_engine.py for screen reading, but server.py's PDF branch never "
        "invokes it, so an image-only PDF's words stay unreachable. The pipeline "
        "now reports that honestly (tests above), which is the floor — reading "
        "them is the fix."))
    def test_ocr_recovers_the_words_from_the_image(self, scanned_pdf):
        part = server_pdf_ingest("contract.pdf", scanned_pdf)
        assert "Revenue exceeded projections" in part


# ─────────────────────────────────────────────────────────────────────────
# 15. Tables — rows and columns have to survive extraction
# ─────────────────────────────────────────────────────────────────────────

class TestTablePdf:
    def test_every_cell_survives(self, table_pdf):
        text = full_text(table_pdf)
        for cell in TABLE_HEADER:
            assert cell in text, f"header cell lost: {cell}"
        for row in TABLE_ROWS:
            for cell in row:
                assert cell in text, f"data cell lost: {cell}"

    def test_rows_stay_together_in_order(self, table_pdf):
        """pypdf flattens a table to one cell per line in row-major order, so
        a surviving row is four consecutive tokens. If the row broke apart,
        a summariser would happily attribute Q3's revenue to Q1."""
        lines = [ln.strip() for ln in full_text(table_pdf).splitlines() if ln.strip()]
        for row in TABLE_ROWS:
            start = lines.index(row[0])
            assert lines[start:start + 4] == list(row), (
                f"row {row[0]} came out interleaved: {lines[start:start + 4]}")

    def test_columns_are_recoverable_by_position(self, table_pdf):
        """Reassemble the table from the flattened text and check the column
        that matters: Revenue - Expenses must equal Net for every row."""
        lines = [ln.strip() for ln in full_text(table_pdf).splitlines() if ln.strip()]
        header_at = lines.index(TABLE_HEADER[0])
        assert lines[header_at:header_at + 4] == list(TABLE_HEADER)

        body = lines[header_at + 4:header_at + 4 + 4 * len(TABLE_ROWS)]
        rebuilt = [body[i:i + 4] for i in range(0, len(body), 4)]
        assert len(rebuilt) == len(TABLE_ROWS)
        for quarter, revenue, expenses, net in rebuilt:
            assert quarter.startswith("Q")
            to_int = lambda s: int(s.replace(",", ""))  # noqa: E731
            assert to_int(revenue) - to_int(expenses) == to_int(net), (
                f"{quarter}: columns landed in the wrong order")

    def test_the_table_reaches_the_model_intact(self, table_pdf):
        part = server_pdf_ingest("financials.pdf", table_pdf)
        for row in TABLE_ROWS:
            for cell in row:
                assert cell in part


# ─────────────────────────────────────────────────────────────────────────
# 16. Multi-column PDF — reading order must not interleave
# ─────────────────────────────────────────────────────────────────────────

class TestTwoColumnPdf:
    @staticmethod
    def _marks(text: str, prefix: str) -> list[int]:
        return [int(m) for m in re.findall(rf"{prefix}(\d{{2}})", text)]

    def test_both_columns_are_present(self, two_column_pdf):
        text = full_text(two_column_pdf)
        assert self._marks(text, "LEFTMARK") == list(range(1, 13))
        assert self._marks(text, "RIGHTMARK") == list(range(1, 13))

    def test_columns_are_not_interleaved(self, two_column_pdf):
        """The classic two-column failure: line 1 of the left column followed
        by line 1 of the right column, producing grammatical-looking nonsense.
        Every LEFTMARK must precede every RIGHTMARK."""
        text = full_text(two_column_pdf)
        positions = [(m.start(), m.group(0)) for m in
                     re.finditer(r"(LEFT|RIGHT)MARK\d{2}", text)]
        sides = [name[:4] for _, name in positions]
        first_right = sides.index("RIGH")
        assert "LEFT" not in sides[first_right:], (
            "reading order interleaved the two columns: "
            f"{[n for _, n in positions][max(0, first_right - 2):first_right + 3]}")

    def test_sentences_are_not_spliced_across_columns(self, two_column_pdf):
        """A spliced read glues the tail of a left-column line onto the head
        of a right-column one. Every marker must still own its own paragraph
        number, i.e. no marker text contains the other column's marker."""
        for para in re.split(r"(?=LEFTMARK|RIGHTMARK)", full_text(two_column_pdf)):
            if not para.strip():
                continue
            assert len(re.findall(r"(?:LEFT|RIGHT)MARK\d{2}", para)) == 1, (
                f"two markers fused into one run: {para[:120]!r}")


# ─────────────────────────────────────────────────────────────────────────
# 17. Huge PDF — what actually reaches the model
# ─────────────────────────────────────────────────────────────────────────

class TestHugePdf:
    def test_the_fixture_is_genuinely_huge(self, huge_pdf):
        reader = PdfReader(io.BytesIO(huge_pdf))
        assert len(reader.pages) >= 200
        assert NEEDLE in (reader.pages[NEEDLE_PAGE - 1].extract_text() or "")

    def test_the_whole_document_is_not_shipped_to_the_model(self, huge_pdf):
        """The one thing the pipeline definitely gets right: it does not try
        to paste 220 pages into a prompt."""
        part = server_pdf_ingest("msa.pdf", huge_pdf)
        assert len(full_text(huge_pdf)) > 300_000, "fixture too small to be a real test"
        assert len(part) < 10_000, (
            f"/message forwarded {len(part)} chars of a 220-page PDF")

    def test_the_cap_is_exactly_what_server_py_applies(self, huge_pdf):
        cap = ingest_cap()
        part = server_pdf_ingest("msa.pdf", huge_pdf)
        header, _, rest = part.partition("\n")
        assert header == "[File: msa.pdf]"
        content, _, notice = rest.partition("\n...[truncated")
        assert len(content) == cap, (
            f"expected exactly {cap} capped chars of document text, got {len(content)}")
        assert notice, "the truncation notice went missing"

    def test_the_cap_is_blind_head_truncation_not_retrieval(self, huge_pdf):
        """Documents the real strategy: the first N characters, which is
        pages 1-2 of 220. Nothing looks at the user's question."""
        cap = ingest_cap()
        part = server_pdf_ingest("msa.pdf", huge_pdf)
        pages_included = [int(m) for m in re.findall(r"PAGEMARK(\d{4})", part)]
        assert pages_included[0] == 1
        assert max(pages_included) < 10, (
            f"cap of {cap} chars reaches page {max(pages_included)} of "
            f"{HUGE_PAGE_COUNT} — update this test if the strategy changed")

    def test_truncation_is_announced(self, huge_pdf):
        """Was silent. A model handed 2500 unmarked characters cannot tell a
        two-page memo from page 1 of a 220-page contract, and will summarise
        the fragment as though it were the whole document."""
        part = server_pdf_ingest("msa.pdf", huge_pdf)
        assert re.search(r"truncat", part, re.I), (
            "no truncation notice in the text handed to the model")
        assert "START of the document" in part, (
            "the notice must say which end of the document survived")

    def test_the_truncation_notice_states_the_real_scale(self, huge_pdf):
        """Knowing it's 220 pages is what lets the model caveat its answer
        instead of presenting a two-page summary as complete."""
        part = server_pdf_ingest("msa.pdf", huge_pdf)
        notice = part.partition("...[truncated")[2]
        assert str(HUGE_PAGE_COUNT) in notice, f"page count missing from {notice!r}"
        assert str(len(full_text(huge_pdf))) in notice, "character total missing"

    @pytest.mark.xfail(strict=True, reason=(
        "GAP: there is no targeted retrieval for large PDFs. Nothing indexes "
        "or searches the document against the user's question — a clause on "
        "page 173 is simply unreachable through the attachment path."))
    def test_a_clause_deep_in_the_document_is_retrievable(self, huge_pdf):
        part = server_pdf_ingest("msa.pdf", huge_pdf)
        assert "ZEPHYR-CLAUSE-9931" in part

    def test_the_needle_is_absent_and_the_model_is_told_why(self, huge_pdf):
        """Retrieval is missing, but the omission is at least declared: the
        clause on page 173 never arrives, and the notice says the text was
        cut. Silent absence plus a confident answer is the failure mode."""
        part = server_pdf_ingest("msa.pdf", huge_pdf)
        assert NEEDLE not in part
        assert "truncated" in part
