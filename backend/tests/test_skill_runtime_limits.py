"""Runtime limits around a skill run: the step budget, log encoding, and the
disk quota that stops repeated generation filling the drive.

Everything here is about a skill that behaves badly by accident rather than
malice — a model that never says "done", a library that prints a ✓, a user
who generates fifty decks in an afternoon. All three produced real failures,
and all three are cheap to regress.

Mocked throughout: brain.think and code_exec's process-creation primitives.
Nothing writes outside tmp_path.
"""
import io
import json
import logging
import time
from pathlib import Path

import pytest

import brain
import code_exec
import logger as primnox_logger
import permission_manager
import runtime_capabilities
import sandbox_manager
from skills import adapted_skill
from skills.adapted_skill import ParsedSkill, make_adapted_skill_class
from skills.base_skill import SkillContext


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def stub_capabilities(monkeypatch):
    monkeypatch.setattr(
        runtime_capabilities, "detect",
        lambda force=False: runtime_capabilities.Capabilities(
            sandbox=True, python=True, node=False, libraries={}, node_modules={},
        ),
    )


@pytest.fixture(autouse=True)
def isolated_workspaces(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir(exist_ok=True)

    def _workspace_path(workspace_id):
        d = root / workspace_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(code_exec, "workspace_path", _workspace_path)
    return root


def _reply(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def _skill(folder: Path, body="Do the task.", name="Test Skill"):
    folder.mkdir(parents=True, exist_ok=True)
    return make_adapted_skill_class(
        folder, ParsedSkill(name=name, description="does a thing", body=body),
    )()


# ── 35. Step-budget exhaustion ────────────────────────────────────────────────

class TestStepLimitExhaustion:
    """A model that emits a code block every single turn burns all
    `_MAX_STEPS` and the loop stops mid-workflow — an unzipped deck that was
    never rezipped, a spreadsheet with no data in it.

    What the loop does today: sets `extras["step_limit_reached"] = True` and
    returns `success=True` ("best effort"). The flag is the ONLY signal that
    the run was truncated — see TestStepLimitIsReportedAsSuccess below, which
    documents why that's a problem in its own right.
    """

    def _never_finishes(self, monkeypatch):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _reply("```python\nprint(1)\n```"))
        ran = []
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: (
                ran.append(code),
                {"success": True, "stdout": "1", "stderr": "", "files_created": []},
            )[1],
        )
        return ran

    def test_the_loop_stops_at_exactly_max_steps(self, monkeypatch, tmp_path):
        ran = self._never_finishes(monkeypatch)
        _skill(tmp_path / "s").run(SkillContext(user_message="loop", session_id="s1"))
        assert len(ran) == adapted_skill._MAX_STEPS

    def test_exhaustion_sets_the_step_limit_flag(self, monkeypatch, tmp_path):
        self._never_finishes(monkeypatch)
        result = _skill(tmp_path / "s").run(SkillContext(user_message="loop", session_id="s1"))
        assert result.extras.get("step_limit_reached") is True

    def test_a_run_that_finishes_normally_does_not_set_the_flag(self, monkeypatch, tmp_path):
        replies = iter([_reply("```python\nprint(1)\n```"), _reply("all done")])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(replies))
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: {
                "success": True, "stdout": "1", "stderr": "", "files_created": [],
            },
        )
        result = _skill(tmp_path / "s").run(SkillContext(user_message="go", session_id="s1"))
        assert "step_limit_reached" not in result.extras

    def test_the_last_step_is_told_it_is_the_last(self, monkeypatch, tmp_path):
        # Without this the model spends its final turn starting something it
        # can never finish, instead of summarising what it has.
        prompts = []
        monkeypatch.setattr(
            brain, "think",
            lambda prompt, *a, **kw: (prompts.append(prompt),
                                      _reply("```python\nprint(1)\n```"))[1],
        )
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: {
                "success": True, "stdout": "", "stderr": "", "files_created": [],
            },
        )
        _skill(tmp_path / "s").run(SkillContext(user_message="loop", session_id="s1"))

        assert "last available command" in prompts[-1]

    def test_partial_artifacts_are_still_reported(self, monkeypatch, tmp_path):
        # A truncated run may have produced something usable; losing track of
        # it would leave an orphan file the user never hears about.
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _reply("```python\nprint(1)\n```"))
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: {
                "success": True, "stdout": "", "stderr": "", "files_created": ["draft.pptx"],
            },
        )
        result = _skill(tmp_path / "s").run(SkillContext(user_message="loop", session_id="s1"))

        assert result.extras["files_created"] == ["draft.pptx"]
        assert result.extras.get("step_limit_reached") is True

    def test_the_flag_survives_into_the_route_skill_dict(self, monkeypatch, tmp_path):
        # extras are splatted into route_skill()'s return value — this is the
        # only place a caller could ever notice truncation.
        from skills import skill_router

        monkeypatch.setattr(brain, "think", lambda *a, **kw: _reply("```python\nprint(1)\n```"))
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: {
                "success": True, "stdout": "", "stderr": "", "files_created": [],
            },
        )
        skill_cls = make_adapted_skill_class(
            _mkdir(tmp_path / "s"), ParsedSkill("Budget Skill", "d", "body"),
        )
        monkeypatch.setitem(skill_router.CLAUDE_SKILLS_REGISTRY, "budget_skill", skill_cls)

        result = skill_router.route_skill(user_message="loop", skill_name="Budget Skill",
                                          session_id="s1")

        assert result["step_limit_reached"] is True


class TestStepLimitIsReportedAsSuccess:
    """FINDING (asserted, not fixed): a run that exhausted its step budget
    still returns `success=True`.

    core.py's skill dispatch does
    `reply = skill_result.get("output_text") or skill_result.get("error")` and
    then broadcasts `skill_complete` with `success=skill_result["success"]`.
    Neither reads `step_limit_reached`. So a deck abandoned halfway through
    its unzip/edit/rezip pipeline is presented to the user as a completed
    skill run, with whatever the model's tenth message happened to say as the
    summary.

    The first test pins today's behaviour; the second states the contract the
    brief asked for and is marked xfail, so it flips to a pass — loudly — the
    day the loop stops claiming success for a truncated run.
    """

    def _exhausted(self, monkeypatch, tmp_path):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _reply("```python\nprint(1)\n```"))
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: {
                "success": True, "stdout": "", "stderr": "", "files_created": [],
            },
        )
        return _skill(tmp_path / "s").run(SkillContext(user_message="loop", session_id="s1"))

    def test_today_an_exhausted_run_still_claims_success(self, monkeypatch, tmp_path):
        result = self._exhausted(monkeypatch, tmp_path)
        assert result.success is True
        assert result.error is None
        assert result.extras["step_limit_reached"] is True

    @pytest.mark.xfail(
        strict=True,
        reason="FINDING: exhausting _MAX_STEPS returns success=True with no error, "
               "so core.py reports a truncated skill run as a completed one.",
    )
    def test_an_exhausted_run_should_not_report_success(self, monkeypatch, tmp_path):
        result = self._exhausted(monkeypatch, tmp_path)
        assert result.success is False or result.error


def _mkdir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── 36. Non-ASCII skill output must not break logging ─────────────────────────

class TestUnicodeSkillOutputDoesNotBreakLogging:
    """Regression guard for a real failure: pptxgenjs prints "✓ file created"
    to stdout, that text was echoed into the follow-up prompt, and the prompt
    was logged. Windows' console defaults to a legacy codepage, so
    StreamHandler.emit() raised UnicodeEncodeError — and logging's own
    handleError fallback, printing to the same broken stream, raised
    identically and was NOT caught. The exception propagated out of the log
    call and was reported as the SKILL failing, after a completely successful
    sandboxed run.

    Fixed in logger.py by reconfiguring the console stream to replace
    unencodable characters. These assert the property, not the fix, so an
    alternative implementation still passes.
    """

    NASTY = "✓ Done — “smart quotes”, an em‑dash, 🎉 and ünïcödé"

    def test_logging_nasty_output_does_not_raise(self):
        log = primnox_logger.get_logger("skills.unicode_regression")
        log.info(f"Thinking about: {self.NASTY}")  # must not raise

    def test_the_console_handler_never_encodes_strictly(self):
        console = next(
            h for h in primnox_logger._shared_handlers()
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        )
        errors = getattr(console.stream, "errors", None)
        assert errors != "strict", (
            "the console stream would raise UnicodeEncodeError on a ✓ again"
        )

    def test_a_strict_cp1252_stream_is_what_used_to_break(self):
        # Documents the mechanism so the guard above is legible: the same
        # record is fine under errors="replace" and fatal under "strict".
        record = logging.LogRecord("t", logging.INFO, __file__, 1, self.NASTY, None, None)

        strict = logging.StreamHandler(
            io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
        )
        with pytest.raises(UnicodeEncodeError):
            strict.stream.write(strict.format(record) + "\n")

        replacing = logging.StreamHandler(
            io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="replace")
        )
        replacing.emit(record)  # must not raise

    def test_the_json_formatter_survives_the_same_text(self):
        record = logging.LogRecord("t", logging.INFO, __file__, 1, self.NASTY, None, None)
        parsed = json.loads(primnox_logger.JsonFormatter().format(record))
        assert parsed["msg"] == self.NASTY

    def test_a_skill_whose_sandbox_output_is_unicode_still_succeeds(
        self, monkeypatch, tmp_path
    ):
        # The end-to-end shape of the original bug: successful sandbox run,
        # ✓ in stdout, echoed into the follow-up prompt, logged on the way.
        replies = iter([
            _reply("```python\nbuild_deck()\n```"),
            _reply(f"{self.NASTY} — the deck is ready"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(replies))
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: {
                "success": True, "stdout": self.NASTY, "stderr": "",
                "files_created": ["deck.pptx"],
            },
        )

        result = _skill(tmp_path / "s").run(
            SkillContext(user_message="build a deck", session_id="s1")
        )

        assert result.success is True
        assert result.error is None
        assert "🎉" in result.output_text

    def test_unicode_in_a_progress_payload_does_not_break_the_run(
        self, monkeypatch, tmp_path
    ):
        # The activity panel gets the model's own narration, which is exactly
        # where an em-dash or an emoji shows up.
        events = []
        replies = iter([
            _reply(f"{self.NASTY}\n```python\nprint('x')\n```"),
            _reply("done"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(replies))
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: {
                "success": True, "stdout": "", "stderr": "", "files_created": [],
            },
        )

        result = _skill(tmp_path / "s").run(
            SkillContext(user_message="go", session_id="s1",
                         progress=lambda t, p: events.append((t, p)))
        )

        assert result.success is True
        assert any("✓" in str(p) for _, p in events)

    def test_unicode_reaches_the_in_memory_log_buffer_intact(self):
        log = primnox_logger.get_logger("skills.unicode_regression")
        marker = f"BUFFERPROBE {self.NASTY}"
        log.info(marker)
        assert any(marker in e.get("msg", "") for e in primnox_logger.get_log_buffer(limit=50))


# ── 38. Disk quota across repeated generation ─────────────────────────────────

class TestRepeatedGenerationRespectsTheQuota:
    """Skills write real files, and nothing else reclaims them. `_run()` calls
    `enforce_quota` after every execution with `protect=(runtime_dir(),
    session_dir)` — so the total stays bounded, the oldest output goes first,
    and neither the shared node_modules nor the workspace of the run that is
    happening right now can be evicted out from under itself."""

    @pytest.fixture
    def code_exec_root(self, monkeypatch, tmp_path):
        root = tmp_path / "CodeExecution"
        root.mkdir()
        monkeypatch.setattr(sandbox_manager, "code_exec_dir", lambda: root)
        return root

    def _write(self, path: Path, size: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        time.sleep(0.02)  # distinct mtimes so "oldest" is well-defined
        return path

    def test_repeated_generation_stays_under_the_cap(self, code_exec_root):
        for i in range(10):
            self._write(code_exec_root / f"run{i}" / "deck.pptx", 100)

        sandbox_manager.enforce_quota(quota_bytes=350, base=code_exec_root)

        assert sandbox_manager.get_usage_bytes(code_exec_root) <= 350

    def test_the_oldest_generated_file_is_evicted_first(self, code_exec_root):
        oldest = self._write(code_exec_root / "run0" / "deck.pptx", 100)
        middle = self._write(code_exec_root / "run1" / "deck.pptx", 100)
        newest = self._write(code_exec_root / "run2" / "deck.pptx", 100)

        evicted = sandbox_manager.enforce_quota(quota_bytes=200, base=code_exec_root)

        assert evicted == 1
        assert not oldest.exists()
        assert middle.exists() and newest.exists()

    def test_the_active_workspace_is_never_evicted_mid_run(self, code_exec_root):
        # A multi-step skill's workspace is full of files older than the
        # throwaway session dirs around it — first in line for oldest-first
        # eviction, and deleting it would destroy a half-built deck between
        # two steps of the same skill.
        active = code_exec_root / "ws_session-a"
        self._write(active / "unzipped" / "slide1.xml", 400)
        self._write(code_exec_root / "later" / "junk.bin", 100)

        sandbox_manager.enforce_quota(quota_bytes=100, base=code_exec_root,
                                      protect=(active,))

        assert (active / "unzipped" / "slide1.xml").exists()

    def test_the_shared_runtime_is_never_evicted(self, code_exec_root):
        runtime = code_exec_root / "_runtime"
        dep = self._write(runtime / "node_modules" / "pptxgenjs" / "index.js", 400)
        self._write(code_exec_root / "run0" / "deck.pptx", 100)

        sandbox_manager.enforce_quota(quota_bytes=100, base=code_exec_root,
                                      protect=(runtime,))

        assert dep.exists()

    def test_the_code_exec_quota_is_the_one_actually_applied(self, monkeypatch, tmp_path):
        # _run() passes CODE_EXEC_QUOTA_BYTES and code_exec_dir(), not
        # sandbox_manager's 1 GB default over the generated-documents folder.
        # Getting that wrong would either never evict or evict the wrong tree.
        seen = {}
        monkeypatch.setattr(
            sandbox_manager, "enforce_quota",
            lambda quota_bytes=None, base=None, protect=(): seen.update(
                quota=quota_bytes, base=base, protect=protect) or 0,
        )
        monkeypatch.setattr(sandbox_manager, "prune_stale_workspaces", lambda *a, **kw: 0)
        monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: True)
        monkeypatch.setattr(code_exec, "_active_backend", lambda: "appcontainer")
        monkeypatch.setattr(
            code_exec, "_build_appcontainer_command", lambda lang, code, d: "noop",
        )
        monkeypatch.setattr(
            code_exec, "_create_appcontainer_process",
            lambda cmd, cwd, timeout: {
                "success": True, "stdout": "", "stderr": "", "return_code": 0,
                "timed_out": False, "duration_ms": 1.0,
            },
        )
        root = tmp_path / "CodeExecution"
        root.mkdir()
        monkeypatch.setattr(sandbox_manager, "code_exec_dir", lambda: root)

        code_exec.run_python("print(1)", session_id="s1", workspace_id="s1-Deck")

        assert seen["quota"] == code_exec.CODE_EXEC_QUOTA_BYTES
        assert seen["base"] == root
        # The workspace this very run used must be in the protect set.
        assert any("s1-Deck" in str(p) for p in seen["protect"])

    def test_stale_workspaces_are_pruned_by_age_not_by_the_quota_sweeper(self, code_exec_root):
        import os

        stale = code_exec_root / "ws_abandoned"
        f = self._write(stale / "leftover.txt", 10)
        old = time.time() - (48 * 3600)
        os.utime(f, (old, old))
        os.utime(stale, (old, old))

        assert sandbox_manager.prune_stale_workspaces(max_age_hours=24) == 1
        assert not stale.exists()

    def test_quota_enforcement_never_reaches_outside_its_base(self, code_exec_root, tmp_path):
        outside = tmp_path / "user_documents"
        outside.mkdir()
        precious = outside / "resume.docx"
        precious.write_bytes(b"x" * 5000)

        self._write(code_exec_root / "run0" / "deck.pptx", 100)
        sandbox_manager.enforce_quota(quota_bytes=0, base=code_exec_root)

        assert precious.exists()
