"""The worst failure mode in document generation: a confident "Done!" over a
file that was never written.

Everything else in this suite is about a document being *bad*. This file is
about a document not *existing* while Primnox says it does. A user who is
told their deck is ready and finds nothing has been actively misled, and —
unlike a wonky layout — there is no way for them to notice from the reply.

The model is the unreliable component here. It is told the command failed
(`_build_followup_prompt` says so explicitly), and it may still summarise as
though everything worked: that is a well-known LLM behaviour, not a bug that
can be prompted away with certainty. So the guarantee has to come from
Primnox, which knows something the model's summary doesn't — whether any
file was actually produced.

Everything here is deterministic. `brain.think` and `code_exec.run_*` are
both mocked, so a failing generation script is simulated exactly and no API
call or sandbox run happens.

Also covers the OUTPUT QUALITY half of the execution contract, since that is
the other place where "it opens" gets mistaken for "it's finished".
"""

from pathlib import Path

import pytest

import brain
import code_exec
import runtime_capabilities
from skills.adapted_skill import (AdaptedClaudeSkill, ParsedSkill,
                                  make_adapted_skill_class)
from skills.base_skill import SkillContext


@pytest.fixture(autouse=True)
def isolated_workspace(monkeypatch, tmp_path_factory):
    """execute() stages the skill package into a real execution workspace.
    Unpatched that resolves to the user's actual Documents\\Primnox\\
    CodeExecution — so without this, these tests would write into live user
    data. Same guard as test_adapted_skill.py's."""
    root = tmp_path_factory.mktemp("verify_ws")
    monkeypatch.setattr(code_exec, "workspace_path", lambda wid: root / wid)
    return root


@pytest.fixture(autouse=True)
def stub_capabilities(monkeypatch):
    """_execution_contract probes real capabilities, which runs code as the
    sandbox account — far too slow for a unit test, and it would make results
    depend on whether Node happens to work on this machine."""
    monkeypatch.setattr(runtime_capabilities, "detect", lambda force=False: (
        runtime_capabilities.Capabilities(
            sandbox=True, python=True, node=True,
            libraries={"python-pptx": True, "reportlab": True, "pypdf": True},
            node_modules={"pptxgenjs": True},
        )))


def _reply(content):
    return {"choices": [{"message": {"content": content}}]}


def _pptx_skill(tmp_path, name="pptx"):
    """An adapted skill standing in for the real claude_skills/pptx package.
    Named "pptx" because the quality contract keys off the skill name."""
    parsed = ParsedSkill(name=name, description="creates presentations",
                         body="Build the deck the user asked for.")
    return make_adapted_skill_class(tmp_path, parsed)()


def _scripted_think(*contents):
    replies = iter(contents)
    return lambda *a, **kw: _reply(next(replies))


# The lie under test: the model insists the deck exists.
CONFIDENT_LIE = (
    "Done! I've created your 10-slide deck on machine learning. "
    "You'll find it saved as ai_overview.pptx in your working directory. "
    "Let me know if you'd like any changes!"
)

GENERATION_CODE = "```python\nfrom pptx import Presentation\nPresentation().save('ai_overview.pptx')\n```"


class TestFailedGenerationIsNotReportedAsSuccess:
    """Test 22. The single most important behaviour in this suite."""

    @pytest.fixture
    def failed_run(self, monkeypatch, tmp_path):
        """A generation script that dies, followed by a model that claims it
        worked. `files_created` is empty because nothing was written."""
        monkeypatch.setattr(brain, "think",
                            _scripted_think(GENERATION_CODE, CONFIDENT_LIE))
        monkeypatch.setattr(code_exec, "run_python", lambda code, **kw: {
            "success": False,
            "error": "ModuleNotFoundError: No module named 'pptx'",
            "stdout": "",
            "stderr": "Traceback (most recent call last):\n  ModuleNotFoundError",
            "files_created": [],
        })
        return _pptx_skill(tmp_path).run(SkillContext(user_message="make me a deck",
                                                      session_id="s-fail"))

    def test_no_artifacts_are_reported(self, failed_run):
        assert failed_run.extras.get("files_created") == []

    def test_the_result_is_not_marked_successful(self, failed_run):
        assert failed_run.success is False, (
            "Primnox reported success for a run where the generation script "
            "failed and no file was produced. The model's summary claimed the "
            "deck was ready; nothing contradicted it."
        )

    def test_the_failure_reason_reaches_the_caller(self, failed_run):
        assert failed_run.error, "a failed run must carry an error"
        assert "ModuleNotFoundError" in failed_run.error, (
            f"the underlying cause was dropped: {failed_run.error!r}")

    def test_the_caller_is_warned_the_summary_cannot_be_trusted(self, failed_run):
        assert "no file" in failed_run.error.lower() or "not produced" in failed_run.error.lower()

    def test_use_skill_does_not_hand_the_lie_to_the_model(self, monkeypatch, failed_run):
        """The end of the chain. `use_skill` is what the orchestrating model
        reads; if it returns the summary verbatim, the lie is laundered into
        the user's chat with nothing marking it."""
        import tools
        from skills import skill_router

        monkeypatch.setattr(skill_router, "route_skill", lambda **kw: {
            "success": failed_run.success,
            "output_text": failed_run.output_text,
            "error": failed_run.error,
            **failed_run.extras,
        })
        reply = tools.execute_tool(
            "use_skill", {"skill_name": "pptx", "query": "make me a deck"})

        # The summary is still quoted — it's useful diagnostic context — but
        # it must arrive attributed and after the contradiction, never as the
        # reply's own voice.
        assert reply.startswith("The pptx run did not produce a file"), (
            f"the reply leads with something other than the failure: {reply!r}")
        assert "ModuleNotFoundError" in reply
        assert reply.index("did not produce a file") < reply.index("Done!"), (
            "the false claim appears before it is contradicted")
        assert "closing summary was:" in reply, (
            "the quoted claim is not attributed, so it reads as fact")


class TestSuccessfulGenerationStillSucceeds:
    """The other half of the guarantee: the failure check must not turn
    working runs into false alarms, which would be its own kind of lying."""

    def _run(self, monkeypatch, tmp_path, exec_results, replies):
        results = iter(exec_results)
        monkeypatch.setattr(brain, "think", _scripted_think(*replies))
        monkeypatch.setattr(code_exec, "run_python", lambda code, **kw: next(results))
        return _pptx_skill(tmp_path).run(
            SkillContext(user_message="make me a deck", session_id="s-ok"))

    def test_a_clean_run_is_a_success(self, monkeypatch, tmp_path):
        result = self._run(
            monkeypatch, tmp_path,
            [{"success": True, "stdout": "saved", "stderr": "",
              "files_created": ["ai_overview.pptx"]}],
            [GENERATION_CODE, "Done — ai_overview.pptx has 10 slides."],
        )
        assert result.success is True
        assert result.extras["files_created"] == ["ai_overview.pptx"]

    def test_a_recovered_run_is_a_success(self, monkeypatch, tmp_path):
        """First attempt fails, second writes the file. That is the loop
        working exactly as designed, not a failure."""
        result = self._run(
            monkeypatch, tmp_path,
            [{"success": False, "error": "SyntaxError", "stdout": "", "stderr": "",
              "files_created": []},
             {"success": True, "stdout": "", "stderr": "",
              "files_created": ["ai_overview.pptx"]}],
            [GENERATION_CODE, GENERATION_CODE, "Fixed the typo — the deck is ready."],
        )
        assert result.success is True
        assert result.extras["files_created"] == ["ai_overview.pptx"]

    def test_a_late_validation_failure_does_not_discard_the_deck(self, monkeypatch, tmp_path):
        """The deck was written in step 1; step 2's validation command blew
        up. The file genuinely exists, so calling the whole run a failure
        would be the opposite error."""
        result = self._run(
            monkeypatch, tmp_path,
            [{"success": True, "stdout": "", "stderr": "",
              "files_created": ["ai_overview.pptx"]},
             {"success": False, "error": "unzip: command not found",
              "stdout": "", "stderr": "", "files_created": []}],
            [GENERATION_CODE, "```python\nvalidate()\n```",
             "The deck is saved; I couldn't run the extra validation pass."],
        )
        assert result.success is True
        assert result.extras["files_created"] == ["ai_overview.pptx"]

    def test_a_purely_informational_answer_is_not_a_failure(self, monkeypatch, tmp_path):
        """No commands run, no files created, and that is correct — the user
        asked a question about decks rather than for one."""
        monkeypatch.setattr(brain, "think",
                            _scripted_think("PPTX files are ZIP archives of XML parts."))
        result = _pptx_skill(tmp_path).run(
            SkillContext(user_message="what is a pptx file?", session_id="s-info"))
        assert result.success is True
        assert result.extras["files_created"] == []


class TestArtifactsAreVisibleToTheCallingModel:
    """Even on a successful run, the orchestrating model needs to see what
    was actually produced — that is what lets it name the real filename
    instead of the one it hoped for."""

    def test_use_skill_reports_the_files_that_were_created(self, monkeypatch):
        import tools
        from skills import skill_router

        monkeypatch.setattr(skill_router, "route_skill", lambda **kw: {
            "success": True,
            "output_text": "Your deck is ready.",
            "error": None,
            "files_created": ["ai_overview.pptx"],
            "workspace_id": "s1-pptx",
        })
        reply = tools.execute_tool("use_skill", {"skill_name": "pptx", "query": "deck"})

        assert "Your deck is ready." in reply
        assert "ai_overview.pptx" in reply, (
            f"use_skill dropped the artifact list: {reply!r}")

    def test_use_skill_flags_a_success_that_produced_nothing(self, monkeypatch):
        """A run that ran commands, claimed success, and wrote no file. The
        result is technically a success, but the caller must not be allowed to
        assume a document exists."""
        import tools
        from skills import skill_router

        monkeypatch.setattr(skill_router, "route_skill", lambda **kw: {
            "success": True,
            "output_text": CONFIDENT_LIE,
            "error": None,
            "files_created": [],
            "workspace_id": "s1-pptx",
        })
        reply = tools.execute_tool("use_skill", {"skill_name": "pptx", "query": "deck"})

        assert "no files" in reply.lower(), (
            f"nothing warned the caller the deck does not exist: {reply!r}")

    def test_skills_that_never_report_artifacts_are_left_alone(self, monkeypatch):
        """Non-adapted skills don't carry `files_created` at all; they must
        not acquire a spurious "no files were created" warning."""
        import tools
        from skills import skill_router

        monkeypatch.setattr(skill_router, "route_skill", lambda **kw: {
            "success": True, "output_text": "Screenshot analysed.", "error": None,
        })
        reply = tools.execute_tool("use_skill", {"skill_name": "screenshot", "query": "x"})
        assert reply == "Screenshot analysed."


class TestOutputQualityContract:
    """The prompt section that stops the model shipping library defaults.

    `TestPythonPptxDefaults` in the pptx suite shows what "defaults" concretely
    means — no word wrap, autofit on, no font size, a 4:3 canvas. A model that
    accepts all of those produces a deck that opens and looks like nothing.
    This is the guidance that pushes back, so it needs pinning to the specific
    advice, not just the heading.
    """

    def test_the_pptx_contract_carries_the_quality_section(self):
        assert "OUTPUT QUALITY" in AdaptedClaudeSkill._execution_contract(False, "pptx")

    def test_it_names_palette_and_type_hierarchy(self):
        contract = AdaptedClaudeSkill._execution_contract(False, "pptx").lower()
        assert "palette" in contract, "no colour guidance — the model will use black on white"
        assert "hierarchy" in contract, "no type hierarchy guidance"
        assert "size" in contract and "weight" in contract, (
            "'hierarchy' alone is too abstract to act on; it has to say what varies")

    def test_it_names_library_defaults_as_the_actual_failure(self):
        """The insight that makes the guidance work: the templated look isn't
        carelessness, it's what you get by not deciding anything."""
        contract = AdaptedClaudeSkill._execution_contract(False, "pptx")
        assert "Library defaults" in contract
        assert "default font" in contract

    def test_it_rejects_the_it_opens_bar(self):
        contract = AdaptedClaudeSkill._execution_contract(False, "pptx")
        assert "floor, not the goal" in contract

    def test_it_asks_for_consistency_across_slides(self):
        """One good slide and nine defaults is the common half-done result."""
        contract = AdaptedClaudeSkill._execution_contract(False, "pptx").lower()
        assert "consistently" in contract
        assert "every page or slide" in contract

    def test_the_pdf_contract_carries_it_too(self):
        assert "OUTPUT QUALITY" in AdaptedClaudeSkill._execution_contract(False, "pdf")

    def test_it_reaches_the_assembled_prompt_not_just_the_helper(self, monkeypatch, tmp_path):
        """Contract-building and prompt-assembly are separate steps; a passing
        unit test on the helper proves nothing if _build_prompt drops it."""
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured.setdefault("prompt", prompt)
            return _reply("here's your deck")

        monkeypatch.setattr(brain, "think", fake_think)
        _pptx_skill(tmp_path).run(SkillContext(user_message="deck about AI"))

        assert "OUTPUT QUALITY" in captured["prompt"]
        assert "palette" in captured["prompt"]

    def test_a_non_document_skill_does_not_get_design_guidance(self, monkeypatch, tmp_path):
        """Prompt budget is finite; design advice in a code-generation skill
        crowds out its real instructions."""
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured.setdefault("prompt", prompt)
            return _reply("ok")

        monkeypatch.setattr(brain, "think", fake_think)
        _pptx_skill(tmp_path, name="webapp-testing").run(SkillContext(user_message="test it"))

        assert "OUTPUT QUALITY" not in captured["prompt"]
