"""End-to-end document generation: a real model, the real sandbox, a real file.

Everything here is `@pytest.mark.live` and excluded from the default run by
`pytest.ini`'s `-m "not live"`, because each test costs an API call and a
sandboxed execution that takes tens of seconds. Run them with:

    cd backend && python -m pytest -m live tests/test_document_generation_live.py

These are the only tests in the suite where the *model's* output quality is
under test rather than a checker's. What keeps them from being vibes is that
they assert nothing about the model's prose: every assertion is applied to
the artifact on disk, using the same `deck_report`/`assert_deck_is_presentable`
checkers that `test_document_generation_pptx.py` proves correct against
deliberately-broken fixtures. If a live test fails, the deck really is
malformed.

Skips rather than fails when the environment can't support a real run —
no configured model, no sandbox, or (in this worktree) no installed skill
package, since `skills/claude_skills/*` is gitignored and therefore absent
from a fresh checkout.
"""

import shutil
from pathlib import Path

import pytest

pytest.importorskip("pptx")

import code_exec  # noqa: E402
from skills.adapted_skill import make_adapted_skill_class, parse_skill_md  # noqa: E402
from skills.base_skill import SkillContext  # noqa: E402
from skills.skill_router import _claude_skills_dir  # noqa: E402

from test_document_generation_pptx import (assert_deck_is_presentable,  # noqa: E402
                                           deck_report)

pytestmark = pytest.mark.live


# ─────────────────────────────────────────────────────────────────────────
# Environment gates
# ─────────────────────────────────────────────────────────────────────────

def _skill_package(name: str) -> Path:
    folder = _claude_skills_dir() / name
    if not (folder / "SKILL.md").is_file():
        pytest.skip(f"claude_skills/{name} is not installed (the folder is "
                    "gitignored, so a fresh checkout has no skill packages)")
    return folder


@pytest.fixture(scope="module")
def brain_is_reachable():
    """One cheap real call, so a missing API key skips the module instead of
    failing every test with the same configuration error."""
    from brain import think
    resp = think("Reply with the single word: ready.")
    if "error" in resp:
        pytest.skip(f"no usable model configured: {resp['error']}")
    return True


@pytest.fixture(scope="module")
def sandbox_is_reachable():
    result = code_exec.run_python("print('ok')", session_id="live-probe")
    if not result.get("success"):
        pytest.skip(f"sandbox unavailable: {result.get('error')}")
    return True


@pytest.fixture(scope="module")
def run_skill(brain_is_reachable, sandbox_is_reachable):
    """Runs a real installed skill package end to end and hands back
    (SkillResult, workspace Path). The workspace is a scratch directory under
    Primnox's own CodeExecution root — never user data — and is removed at the
    end of the module so repeat runs don't inherit a previous deck.

    Module-scoped so the class-scoped deck fixtures below can depend on it:
    each of those costs a real model call plus a sandbox run, so a deck is
    generated once and shared by every assertion in its class.
    """
    created = []

    def _run(skill_name: str, request: str, session_id: str):
        folder = _skill_package(skill_name)
        skill_cls = make_adapted_skill_class(folder, parse_skill_md(folder / "SKILL.md"))
        skill = skill_cls()
        ctx = SkillContext(user_message=request, session_id=session_id)
        workspace = code_exec.workspace_path(skill._workspace_id(ctx))
        created.append(workspace)
        return skill.run(ctx), workspace

    yield _run

    for path in created:
        shutil.rmtree(path, ignore_errors=True)


def _one_artifact(result, workspace: Path, suffix: str) -> Path:
    """The generated file, with a failure message that says what actually
    happened rather than just 'IndexError'."""
    assert result.success, f"the skill run failed: {result.error}"
    files = sorted(p for p in workspace.rglob(f"*{suffix}")
                   if "skill" not in p.relative_to(workspace).parts)
    assert files, (
        f"no {suffix} was produced. files_created={result.extras.get('files_created')}, "
        f"summary={result.output_text[:400]!r}")
    return files[-1]


# ─────────────────────────────────────────────────────────────────────────
# 18 (live). A real ten-slide deck
# ─────────────────────────────────────────────────────────────────────────

class TestLiveDeckGeneration:
    @pytest.fixture(scope="class")
    def deck(self, run_skill):
        result, workspace = run_skill(
            "pptx",
            "Create a 10-slide presentation introducing artificial intelligence "
            "to a non-technical audience. Save it as ai_intro.pptx.",
            session_id="live-pptx-basic",
        )
        return deck_report(_one_artifact(result, workspace, ".pptx"))

    def test_the_file_is_a_valid_openable_pptx(self, deck):
        assert deck["slide_count"] > 0

    def test_it_has_roughly_the_requested_number_of_slides(self, deck):
        # A band, not an equality: asking for 10 and getting 9 or 11 is a
        # judgement call, while getting 2 or 40 is a failure to follow the brief.
        assert 8 <= deck["slide_count"] <= 12, (
            f"asked for 10 slides, got {deck['slide_count']}")

    def test_every_slide_carries_real_text(self, deck):
        for slide in deck["slides"]:
            assert len(slide["text"].split()) >= 3, (
                f"slide {slide['index']} is effectively blank: {slide['text']!r}")

    def test_the_slides_are_about_the_requested_subject(self, deck):
        """Deliberately weak — this checks the deck is on-topic, not that any
        particular claim in it is true. Content accuracy is not something a
        deterministic assertion can settle."""
        joined = " ".join(s["text"] for s in deck["slides"]).lower()
        assert any(term in joined for term in
                   ("artificial intelligence", " ai ", "machine learning", "model"))

    def test_slides_are_not_near_duplicates(self, deck):
        """Padding to a slide count by restating the same slide is a common
        way to hit the number without doing the work."""
        texts = [" ".join(s["text"].split()).lower() for s in deck["slides"]]
        assert len(set(texts)) == len(texts), "the deck contains duplicate slides"

    def test_the_deck_is_geometrically_presentable(self, deck):
        """No overflow, no overlap, nothing off-canvas, no squashed images —
        judged by the checkers the default-run suite proves actually fire."""
        assert_deck_is_presentable(deck)


# ─────────────────────────────────────────────────────────────────────────
# 19 (live). Layout stress
# ─────────────────────────────────────────────────────────────────────────

class TestLiveLayoutStress:
    @pytest.fixture(scope="class")
    def dense_deck(self, run_skill):
        result, workspace = run_skill(
            "pptx",
            "Create a detailed 6-slide technical deck on database indexing. "
            "Each slide needs a title and at least 6 substantial bullet points "
            "of a full sentence each. Save it as indexing.pptx.",
            session_id="live-pptx-dense",
        )
        return deck_report(_one_artifact(result, workspace, ".pptx"))

    def test_the_content_actually_is_dense(self, dense_deck):
        """Guards the tests below: if the model quietly produced six one-line
        slides, they'd pass without testing anything."""
        words = sum(len(s["text"].split()) for s in dense_deck["slides"])
        assert words > 250, f"only {words} words — not a layout stress test"

    def test_no_text_overflows_its_placeholder(self, dense_deck):
        problems = [(s["index"], s["overflow"]) for s in dense_deck["slides"] if s["overflow"]]
        assert not problems, f"text spills out of its box on: {problems}"

    def test_no_two_shapes_overlap(self, dense_deck):
        problems = [(s["index"], s["overlap"]) for s in dense_deck["slides"] if s["overlap"]]
        assert not problems, f"shapes collide on: {problems}"

    def test_everything_stays_on_the_canvas(self, dense_deck):
        problems = [(s["index"], s["out_of_bounds"])
                    for s in dense_deck["slides"] if s["out_of_bounds"]]
        assert not problems, f"shapes hang off the slide on: {problems}"


# ─────────────────────────────────────────────────────────────────────────
# 20 (live). Images
# ─────────────────────────────────────────────────────────────────────────

class TestLiveImagePlacement:
    @pytest.fixture(scope="class")
    def image_deck(self, run_skill):
        result, workspace = run_skill(
            "pptx",
            "Create a 3-slide deck about coastal erosion. Generate a simple "
            "wide 1600x900 chart image with Pillow and place it on slide 2 "
            "without distorting it. Save the deck as erosion.pptx.",
            session_id="live-pptx-images",
        )
        return deck_report(_one_artifact(result, workspace, ".pptx"))

    def test_an_image_was_actually_placed(self, image_deck):
        from pptx import Presentation  # noqa: F401
        assert any(s["distorted_images"] is not None for s in image_deck["slides"])

    def test_images_keep_their_aspect_ratio(self, image_deck):
        problems = [(s["index"], s["distorted_images"])
                    for s in image_deck["slides"] if s["distorted_images"]]
        assert not problems, f"images placed at the wrong aspect ratio: {problems}"

    def test_images_stay_inside_the_slide(self, image_deck):
        problems = [(s["index"], s["out_of_bounds"])
                    for s in image_deck["slides"] if s["out_of_bounds"]]
        assert not problems, f"content hangs off the slide: {problems}"


# ─────────────────────────────────────────────────────────────────────────
# 21 (live). Editing a deck the model did not create
# ─────────────────────────────────────────────────────────────────────────

class TestLiveDeckEditing:
    @pytest.fixture(scope="class")
    def edited(self, run_skill):
        """Seeds a known deck into the workspace first, so the edit operates
        on something whose exact contents the assertions already know."""
        from test_document_generation_pptx import AI_SLIDES, build_clean_deck

        folder = _skill_package("pptx")
        skill_cls = make_adapted_skill_class(folder, parse_skill_md(folder / "SKILL.md"))
        skill = skill_cls()
        ctx = SkillContext(session_id="live-pptx-edit")
        workspace = code_exec.workspace_path(skill._workspace_id(ctx))
        workspace.mkdir(parents=True, exist_ok=True)
        build_clean_deck(workspace / "existing.pptx")

        result, workspace = run_skill(
            "pptx",
            "The file existing.pptx is in your working directory. Change the "
            "title on slide 1 to 'A Practical Guide to Machine Learning', then "
            "append two new slides at the end: one titled 'Agents' and one "
            "titled 'Cost Control'. Leave every other slide exactly as it is. "
            "Save the result as existing.pptx.",
            session_id="live-pptx-edit",
        )
        assert result.success, f"the edit run failed: {result.error}"
        return deck_report(workspace / "existing.pptx"), AI_SLIDES

    def test_the_edited_file_is_not_corrupt(self, edited):
        deck, _ = edited
        assert deck["slide_count"] > 0

    def test_two_slides_were_added(self, edited):
        deck, originals = edited
        assert deck["slide_count"] == len(originals) + 2, (
            f"expected {len(originals) + 2} slides, got {deck['slide_count']}")

    def test_the_title_changed(self, edited):
        deck, _ = edited
        assert "Practical Guide" in deck["slides"][0]["text"]

    def test_the_untouched_original_slides_survived(self, edited):
        """The real risk in an "edit": a rebuild from scratch that keeps the
        headline slides and silently drops everything it didn't reproduce."""
        deck, originals = edited
        joined = " ".join(s["text"] for s in deck["slides"])
        missing = [title for title, _ in originals[1:] if title not in joined]
        assert not missing, f"original slides lost in the edit: {missing}"

    def test_the_original_bodies_survived_too(self, edited):
        deck, originals = edited
        joined = " ".join(s["text"] for s in deck["slides"])
        missing = [body[:40] for _, body in originals[1:] if body not in joined]
        assert not missing, f"original slide bodies were rewritten or lost: {missing}"

    def test_the_edited_deck_is_still_presentable(self, edited):
        deck, _ = edited
        assert_deck_is_presentable(deck)


# ─────────────────────────────────────────────────────────────────────────
# 13 (live). A real PDF summary, against a PDF whose contents we control
# ─────────────────────────────────────────────────────────────────────────

class TestLivePdfSummary:
    @pytest.fixture(scope="class")
    def summary(self, run_skill):
        """Seeds a PDF with facts invented for this test, so nothing in it
        can be answered from the model's pretraining — every correct detail
        in the summary had to come from actually reading the file."""
        pytest.importorskip("reportlab")
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas

        folder = _skill_package("pdf")
        skill_cls = make_adapted_skill_class(folder, parse_skill_md(folder / "SKILL.md"))
        skill = skill_cls()
        ctx = SkillContext(session_id="live-pdf-summary")
        workspace = code_exec.workspace_path(skill._workspace_id(ctx))
        workspace.mkdir(parents=True, exist_ok=True)

        c = canvas.Canvas(str(workspace / "briefing.pdf"), pagesize=LETTER)
        c.setFont("Helvetica", 12)
        for i, line in enumerate([
            "Kestrel-7 Mission Briefing",
            "The rover landed in Ares Planitia on 14 March 2031.",
            "Its primary instrument is a neutron spectrometer named HALCYON.",
            "Mission cost was 412 million euros, 8 percent under budget.",
            "Sample return is scheduled for the fourth quarter of 2034.",
        ]):
            c.drawString(72, 720 - i * 24, line)
        c.showPage()
        c.save()

        result, _ = run_skill("pdf", "Summarise briefing.pdf. Include the landing "
                               "date, the instrument name and the mission cost.",
                        session_id="live-pdf-summary")
        assert result.success, f"the summary run failed: {result.error}"
        return result.output_text

    def test_the_summary_reports_facts_from_the_file(self, summary):
        """These values exist nowhere but the generated PDF, so getting them
        right is proof the file was read rather than imagined."""
        assert "HALCYON" in summary
        assert "412" in summary
        assert "2031" in summary

    def test_the_summary_does_not_invent_details(self, summary):
        for absent in ("Kestrel-8", "512 million", "Valles Marineris"):
            assert absent not in summary, f"hallucinated detail: {absent}"


# ─────────────────────────────────────────────────────────────────────────
# 22 (live). A deliberately impossible request must not come back as success
# ─────────────────────────────────────────────────────────────────────────

class TestLiveFailureIsReported:
    def test_an_impossible_request_does_not_report_a_phantom_file(self, run_skill):
        """The live counterpart of the mocked verification tests: whatever the
        model says, the result must not present a file that isn't on disk."""
        result, workspace = run_skill(
            "pptx",
            "Open the file /nonexistent/definitely_missing_deck.pptx, add a "
            "slide to it, and save it as updated.pptx.",
            session_id="live-pptx-impossible",
        )
        on_disk = {p.name for p in workspace.rglob("*.pptx")}
        claimed = set(result.extras.get("files_created") or [])
        assert claimed <= on_disk, (
            f"reported files that do not exist: {claimed - on_disk}")
        if not on_disk:
            assert not result.success, (
                "no deck was produced, yet the run reported success with "
                f"summary: {result.output_text[:400]!r}")
