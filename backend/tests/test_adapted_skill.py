"""Tests for adapted_skill.py — the adapter that lets Primnox load real
Anthropic Claude Skill packages (SKILL.md format). Covers parsing (valid,
malformed, missing required fields), the dynamic per-folder class factory,
and the bounded think()/run_* execution loop with both mocked so no real API
call or sandbox execution happens."""
from pathlib import Path

import pytest

import brain
import code_exec
import runtime_capabilities
from skills import adapted_skill
from skills.adapted_skill import (
    ParsedSkill, parse_skill_md, make_adapted_skill_class,
    _truncate_with_notice, AdaptedClaudeSkill,
)
from skills.base_skill import BaseSkill, SkillContext


@pytest.fixture(autouse=True)
def isolated_workspace(monkeypatch, tmp_path_factory):
    """execute() now stages the skill package into a real execution
    workspace before running anything. Unpatched that resolves to the user's
    actual Documents\\Primnox\\CodeExecution — so without this every test in
    the file would copy fixture skills into live user data."""
    root = tmp_path_factory.mktemp("workspaces")
    monkeypatch.setattr(code_exec, "workspace_path", lambda wid: root / wid)
    return root


def _caps(node=True, **libraries):
    libs = {"python-pptx": True, "reportlab": True, **libraries}
    return runtime_capabilities.Capabilities(
        sandbox=True, python=True, node=node, libraries=libs,
        node_modules={"pptxgenjs": node},
    )


@pytest.fixture(autouse=True)
def stub_capabilities(monkeypatch):
    """_execution_contract consults probed capabilities. Unstubbed that runs
    real code as the sandbox account — far too slow for a unit test, and it
    would make results depend on whether Node happens to work on the machine
    running them. Individual tests override this with their own _caps()."""
    monkeypatch.setattr(runtime_capabilities, "detect", lambda force=False: _caps())


def _ok(**overrides):
    """A successful code_exec result, in the shape execute() consumes."""
    return {"success": True, "stdout": "", "stderr": "", "files_created": [], **overrides}


def _recorder(sink, key=None):
    """A code_exec.run_* double that records the code it was handed and
    returns a well-formed success result. Written as a real function rather
    than `sink.append(code) or _ok()` because append/setdefault return values
    that would short-circuit the `or` and hand execute() a string."""
    def _run(code, session_id="", workspace_id="", **kwargs):
        if key is None:
            sink.append(code)
        else:
            sink[key] = code
        return _ok()
    return _run


def _prompt_capturer(captured, reply="ok"):
    def _think(prompt, *args, **kwargs):
        captured.setdefault("prompt", prompt)
        return _fake_think_response(reply)
    return _think


def _write_skill_md(dir_path, frontmatter_lines, body="Do the thing."):
    dir_path.mkdir(parents=True, exist_ok=True)
    content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n" + body
    (dir_path / "SKILL.md").write_text(content, encoding="utf-8")
    return dir_path / "SKILL.md"


class TestParseSkillMd:
    def test_valid_minimal_frontmatter(self, tmp_path):
        skill_md = _write_skill_md(tmp_path, ["name: my skill", "description: does a thing"])
        parsed = parse_skill_md(skill_md)
        assert parsed.name == "my skill"
        assert parsed.description == "does a thing"
        assert parsed.body == "Do the thing."

    def test_extra_frontmatter_keys_are_ignored(self, tmp_path):
        skill_md = _write_skill_md(tmp_path, [
            "name: my skill", "description: does a thing",
            "license: MIT", "version: 1.2.3", "user-invocable: true",
        ])
        parsed = parse_skill_md(skill_md)
        assert parsed.name == "my skill"
        assert parsed.license == "MIT"
        assert parsed.version == "1.2.3"

    def test_missing_frontmatter_entirely_raises(self, tmp_path):
        (tmp_path / "SKILL.md").write_text("# Just a heading\nno frontmatter here.", encoding="utf-8")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_skill_md(tmp_path / "SKILL.md")

    def test_missing_closing_delimiter_raises(self, tmp_path):
        (tmp_path / "SKILL.md").write_text("---\nname: x\ndescription: y\nno closing delimiter", encoding="utf-8")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_skill_md(tmp_path / "SKILL.md")

    def test_missing_name_raises(self, tmp_path):
        skill_md = _write_skill_md(tmp_path, ["description: does a thing"])
        with pytest.raises(ValueError, match="name"):
            parse_skill_md(skill_md)

    def test_missing_description_raises(self, tmp_path):
        skill_md = _write_skill_md(tmp_path, ["name: my skill"])
        with pytest.raises(ValueError, match="description"):
            parse_skill_md(skill_md)

    def test_blank_name_raises(self, tmp_path):
        skill_md = _write_skill_md(tmp_path, ['name: ""', "description: does a thing"])
        with pytest.raises(ValueError, match="name"):
            parse_skill_md(skill_md)

    def test_malformed_yaml_raises_value_error_not_yaml_error(self, tmp_path):
        dir_path = tmp_path
        dir_path.mkdir(exist_ok=True)
        (dir_path / "SKILL.md").write_text(
            "---\nname: x\n  bad: [unterminated\n---\nbody", encoding="utf-8",
        )
        with pytest.raises(ValueError):
            parse_skill_md(dir_path / "SKILL.md")

    def test_nonexistent_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_skill_md(tmp_path / "does_not_exist" / "SKILL.md")

    def test_references_folder_is_read(self, tmp_path):
        skill_md = _write_skill_md(tmp_path, ["name: my skill", "description: does a thing"])
        (tmp_path / "references").mkdir()
        (tmp_path / "references" / "notes.md").write_text("some notes", encoding="utf-8")

        parsed = parse_skill_md(skill_md)

        assert [label for label, _ in parsed.reference_files] == [str(Path("references") / "notes.md")]

    def test_top_level_md_siblings_are_references_too(self, tmp_path):
        # The official `pdf` skill keeps reference.md/forms.md beside
        # SKILL.md and tells the model to read them — only scanning
        # references/ would point it at docs that aren't in the prompt.
        skill_md = _write_skill_md(tmp_path, ["name: my skill", "description: does a thing"])
        (tmp_path / "reference.md").write_text("the reference", encoding="utf-8")

        parsed = parse_skill_md(skill_md)

        labels = [label for label, _ in parsed.reference_files]
        assert "reference.md" in labels
        assert "SKILL.md" not in labels

    def test_markdown_in_arbitrary_subfolders_is_collected(self, tmp_path):
        # Real skills also use reference/ (singular), agents/, examples/,
        # themes/ — enumerating folder names would miss all of those.
        skill_md = _write_skill_md(tmp_path, ["name: my skill", "description: does a thing"])
        (tmp_path / "agents").mkdir()
        (tmp_path / "agents" / "grader.md").write_text("grade it", encoding="utf-8")

        parsed = parse_skill_md(skill_md)

        assert any("grader.md" in label for label, _ in parsed.reference_files)

    def test_scripts_folder_is_read(self, tmp_path):
        skill_md = _write_skill_md(tmp_path, ["name: my skill", "description: does a thing"])
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "helper.py").write_text("print('hi')", encoding="utf-8")

        parsed = parse_skill_md(skill_md)

        assert [label for label, _ in parsed.script_files] == [str(Path("scripts") / "helper.py")]

    def test_missing_references_and_scripts_folders_are_just_empty(self, tmp_path):
        skill_md = _write_skill_md(tmp_path, ["name: my skill", "description: does a thing"])
        parsed = parse_skill_md(skill_md)
        assert parsed.reference_files == []
        assert parsed.script_files == []


class TestTruncateWithNotice:
    def test_under_cap_unchanged(self):
        text = "short text"
        assert _truncate_with_notice(text, cap=100) == text

    def test_over_cap_truncated_with_notice(self):
        text = "x" * 150
        result = _truncate_with_notice(text, cap=100)
        assert result.startswith("x" * 100)
        assert "truncated, 50 more chars" in result


class TestMakeAdaptedSkillClass:
    def _parsed(self, name="My Skill"):
        return ParsedSkill(name=name, description="does a thing", body="instructions")

    def test_returns_a_basesskill_subclass(self, tmp_path):
        skill_cls = make_adapted_skill_class(tmp_path, self._parsed())
        assert isinstance(skill_cls, type)
        assert issubclass(skill_cls, BaseSkill)

    def test_zero_arg_construction_matches_route_skill_call_pattern(self, tmp_path):
        skill_cls = make_adapted_skill_class(tmp_path, self._parsed())
        skill = skill_cls()
        assert skill.name == "My Skill"
        assert skill.description == "does a thing"

    def test_triggers_are_empty(self, tmp_path):
        skill_cls = make_adapted_skill_class(tmp_path, self._parsed())
        assert skill_cls.trigger_words == ()
        assert skill_cls.supported_extensions == ()

    def test_two_parsed_skills_produce_distinct_classes(self, tmp_path):
        cls_a = make_adapted_skill_class(tmp_path, self._parsed("Skill A"))
        cls_b = make_adapted_skill_class(tmp_path, self._parsed("Skill B"))
        assert cls_a is not cls_b
        assert cls_a().name == "Skill A"
        assert cls_b().name == "Skill B"


def _fake_think_response(content):
    return {"choices": [{"message": {"content": content}}]}


def _make_skill(tmp_path, body="Do the task.", references=None, scripts=None):
    """references/scripts are {filename: text} for convenience — written to
    real files under tmp_path, since ParsedSkill now carries paths and reads
    content lazily at prompt-build time (see adapted_skill's budgeting)."""
    ref_files, script_files = [], []
    for name, text in (references or {}).items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        ref_files.append((name, p))
    for name, text in (scripts or {}).items():
        p = tmp_path / "scripts" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        script_files.append((f"scripts/{name}", p))

    parsed = ParsedSkill(
        name="Test Skill", description="does a thing", body=body,
        reference_files=ref_files, script_files=script_files,
    )
    skill_cls = make_adapted_skill_class(tmp_path, parsed)
    return skill_cls()


class TestAdaptedClaudeSkillExecute:
    def test_no_code_block_returns_content_directly(self, monkeypatch, tmp_path):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response("just a plain answer"))
        run_python_calls = []
        monkeypatch.setattr(code_exec, "run_python", lambda *a, **kw: run_python_calls.append(1))

        skill = _make_skill(tmp_path)
        result = skill.run(SkillContext(user_message="hello"))

        assert result.success is True
        assert result.output_text == "just a plain answer"
        assert run_python_calls == []

    def test_think_error_returns_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: {"error": "no api key"})

        skill = _make_skill(tmp_path)
        result = skill.run(SkillContext(user_message="hello"))

        assert result.success is False
        assert "no api key" in result.error

    def test_one_code_round_trip(self, monkeypatch, tmp_path):
        responses = iter([
            _fake_think_response("```python\nprint('hi')\n```"),
            _fake_think_response("done — it printed hi"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(responses))

        captured = {}

        def fake_run_python(code, session_id="", workspace_id="", **kw):
            captured["code"] = code
            captured["workspace_id"] = workspace_id
            return {"success": True, "stdout": "hi\n", "stderr": "", "files_created": []}

        monkeypatch.setattr(code_exec, "run_python", fake_run_python)

        skill = _make_skill(tmp_path)
        result = skill.run(SkillContext(user_message="print hi", session_id="s1"))

        assert captured["code"] == "print('hi')"
        assert result.success is True
        assert result.output_text == "done — it printed hi"

    def test_step_limit_reached_returns_best_effort_result(self, monkeypatch, tmp_path):
        # think() always returns a code block — simulates a model that never
        # "finishes." Must not loop forever or crash.
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response("```python\nprint(1)\n```"))
        run_python_calls = []

        def fake_run_python(code, session_id="", workspace_id="", **kw):
            run_python_calls.append(code)
            return {"success": True, "stdout": "1\n", "stderr": "", "files_created": []}

        monkeypatch.setattr(code_exec, "run_python", fake_run_python)

        skill = _make_skill(tmp_path)
        result = skill.run(SkillContext(user_message="loop forever"))

        assert len(run_python_calls) <= adapted_skill._MAX_STEPS
        assert result.success is True
        assert result.extras.get("step_limit_reached") is True

    def test_failed_code_execution_is_fed_back_as_an_error(self, monkeypatch, tmp_path):
        responses = iter([
            _fake_think_response("```python\nraise ValueError('boom')\n```"),
            _fake_think_response("sorry, that failed — here's what happened"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(responses))

        def fake_run_python(code, session_id="", workspace_id="", **kw):
            return {"success": False, "error": "boom", "stdout": "", "stderr": "ValueError: boom"}

        monkeypatch.setattr(code_exec, "run_python", fake_run_python)

        skill = _make_skill(tmp_path)
        result = skill.run(SkillContext(user_message="run broken code"))

        assert result.success is True
        assert "failed" in result.output_text or "sorry" in result.output_text

    def test_bash_block_is_dispatched_to_run_shell(self, monkeypatch, tmp_path):
        # The pptx/docx skills' unzip -> edit -> rezip -> validate pipelines
        # are written as bash. Running one as Python would fail and burn a step.
        responses = iter([
            _fake_think_response("```bash\npython skill/scripts/thumbnail.py deck.pptx\n```"),
            _fake_think_response("done"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(responses))
        calls = {}
        monkeypatch.setattr(code_exec, "run_shell", _recorder(calls, "shell"))
        monkeypatch.setattr(code_exec, "run_python", _recorder(calls, "python"))

        _make_skill(tmp_path).run(SkillContext(user_message="thumbnail it"))

        assert "thumbnail.py" in calls["shell"]
        assert "python" not in calls

    def test_javascript_block_is_dispatched_to_run_node(self, monkeypatch, tmp_path):
        # pptxgenjs / docx-js are the documented way these skills build output.
        responses = iter([
            _fake_think_response("```javascript\nrequire('pptxgenjs')\n```"),
            _fake_think_response("done"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(responses))
        calls = {}
        monkeypatch.setattr(code_exec, "run_node", _recorder(calls, "node"))

        _make_skill(tmp_path).run(SkillContext(user_message="build a deck"))

        assert "pptxgenjs" in calls["node"]

    def test_untagged_and_prose_fences_are_not_executed(self, monkeypatch, tmp_path):
        # SKILL.md bodies are full of illustrative ```xml / ```text snippets;
        # executing one as Python would both fail and waste a step.
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response(
            "here's the shape it should have:\n```xml\n<a:p/>\n```\nand plain:\n```\nfoo\n```"
        ))
        calls = []
        for name in ("run_python", "run_shell", "run_node"):
            monkeypatch.setattr(code_exec, name, _recorder(calls))

        result = _make_skill(tmp_path).run(SkillContext(user_message="explain"))

        assert calls == []
        assert result.success is True

    def test_the_first_runnable_block_wins_over_an_earlier_prose_fence(self, monkeypatch, tmp_path):
        responses = iter([
            _fake_think_response("target shape:\n```xml\n<x/>\n```\nnow run:\n```python\nprint(2)\n```"),
            _fake_think_response("done"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(responses))
        calls = []
        monkeypatch.setattr(code_exec, "run_python", _recorder(calls))

        _make_skill(tmp_path).run(SkillContext(user_message="go"))

        assert calls == ["print(2)"]

    def test_every_step_reuses_one_workspace(self, monkeypatch, tmp_path):
        # unzip -> edit -> rezip only works if step 2 can see step 1's files.
        responses = iter([
            _fake_think_response("```python\nprint(1)\n```"),
            _fake_think_response("```python\nprint(2)\n```"),
            _fake_think_response("done"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(responses))
        seen = []
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: seen.append(workspace_id) or _ok(),
        )

        _make_skill(tmp_path).run(SkillContext(user_message="two steps", session_id="s1"))

        assert len(seen) == 2
        assert seen[0] == seen[1]
        assert seen[0]

    def test_workspaces_are_scoped_per_skill_not_just_per_session(self, tmp_path):
        # A deck and a spreadsheet built in the same conversation must not
        # inherit each other's half-finished files.
        a = _make_skill(tmp_path)
        b = _make_skill(tmp_path)
        b.name = "Other Skill"
        ctx = SkillContext(user_message="x", session_id="s1")

        assert a._workspace_id(ctx) != b._workspace_id(ctx)

    def test_skill_files_are_staged_into_the_workspace(self, monkeypatch, tmp_path, isolated_workspace):
        # SKILL.md says "python scripts/thumbnail.py" — those scripts live in
        # the repo, which the sandbox account deliberately cannot read.
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response("ok"))

        skill = _make_skill(tmp_path, scripts={"thumbnail.py": "print('grid')"})
        skill.run(SkillContext(user_message="hi", session_id="s1"))

        staged = isolated_workspace / skill._workspace_id(SkillContext(session_id="s1")) / "skill"
        assert (staged / "scripts" / "thumbnail.py").read_text() == "print('grid')"

    def test_staged_scripts_are_described_as_runnable(self, monkeypatch, tmp_path):
        captured = {}
        monkeypatch.setattr(brain, "think", _prompt_capturer(captured))

        _make_skill(tmp_path, scripts={"thumbnail.py": "x"}).run(SkillContext(user_message="hi"))

        assert "ARE runnable" in captured["prompt"]
        assert "scripts/thumbnail.py" in captured["prompt"]

    def test_staging_failure_degrades_instead_of_crashing(self, monkeypatch, tmp_path):
        captured = {}
        monkeypatch.setattr(brain, "think", _prompt_capturer(captured))

        def boom(_wid):
            raise OSError("disk full")

        monkeypatch.setattr(code_exec, "workspace_path", boom)

        result = _make_skill(tmp_path, scripts={"thumbnail.py": "x"}).run(SkillContext(user_message="hi"))

        assert result.success is True
        assert "reference only" in captured["prompt"]

    def test_javascript_is_not_offered_when_node_is_unavailable(self, monkeypatch, tmp_path):
        captured = {}
        monkeypatch.setattr(runtime_capabilities, "detect", lambda force=False: _caps(node=False))
        monkeypatch.setattr(brain, "think", _prompt_capturer(captured))

        _make_skill(tmp_path).run(SkillContext(user_message="build a deck"))

        assert "```javascript" not in captured["prompt"]
        assert "Node.js" in captured["prompt"]

    def test_unavailable_libraries_are_named_in_the_prompt(self, monkeypatch, tmp_path):
        # The pptx skill body is largely pptxgenjs instructions, and
        # python-pptx is the documented fallback — if neither works here the
        # model has to know before it starts, not six steps in.
        captured = {}
        monkeypatch.setattr(
            runtime_capabilities, "detect",
            lambda force=False: _caps(node=False, **{"python-pptx": False}),
        )
        monkeypatch.setattr(brain, "think", _prompt_capturer(captured))

        _make_skill(tmp_path).run(SkillContext(user_message="build a deck"))

        assert "NOT AVAILABLE" in captured["prompt"]
        assert "python-pptx" in captured["prompt"]

    def test_a_node_block_is_refused_with_the_alternative_named(self, monkeypatch, tmp_path):
        # A skill body full of pptxgenjs examples is persuasive enough that
        # the model may try anyway; the refusal has to point somewhere useful.
        monkeypatch.setattr(runtime_capabilities, "detect", lambda force=False: _caps(node=False))
        responses = iter([
            _fake_think_response("```javascript\nrequire('pptxgenjs')\n```"),
            _fake_think_response("ok, using python-pptx instead"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(responses))
        ran = []
        monkeypatch.setattr(code_exec, "run_node", _recorder(ran))

        result = _make_skill(tmp_path).run(SkillContext(user_message="deck"))

        assert ran == []  # never reached the sandbox
        assert result.success is True

    def test_node_blocks_still_run_when_node_is_available(self, monkeypatch, tmp_path):
        # The JS path stays in the codebase — if the sandbox limitation is
        # ever fixed it must light up again with no code change.
        monkeypatch.setattr(runtime_capabilities, "detect", lambda force=False: _caps(node=True))
        responses = iter([
            _fake_think_response("```javascript\nrequire('pptxgenjs')\n```"),
            _fake_think_response("done"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(responses))
        ran = []
        monkeypatch.setattr(code_exec, "run_node", _recorder(ran))

        _make_skill(tmp_path).run(SkillContext(user_message="deck"))

        assert ran == ["require('pptxgenjs')"]

    def test_references_are_truncated_in_the_prompt(self, monkeypatch, tmp_path):
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response("ok")

        monkeypatch.setattr(brain, "think", fake_think)

        long_ref = "x" * (adapted_skill._REFERENCE_CHAR_CAP + 500)
        skill = _make_skill(tmp_path, references={"big.md": long_ref})
        skill.run(SkillContext(user_message="hello"))

        assert "truncated" in captured["prompt"]

    def test_short_references_are_not_truncated(self, monkeypatch, tmp_path):
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response("ok")

        monkeypatch.setattr(brain, "think", fake_think)

        skill = _make_skill(tmp_path, references={"small.md": "just a little context"})
        skill.run(SkillContext(user_message="hello"))

        assert "just a little context" in captured["prompt"]
        assert "truncated" not in captured["prompt"]

    def test_output_path_resolves_the_created_artifact(self, monkeypatch, tmp_path, isolated_workspace):
        # execute() used to only record the bare filename in
        # extras["files_created"] and never set output_path at all — callers
        # that want to actually open/attach the result (like pdf_skill.py's
        # output_path) had nothing to go on. It should resolve to the file's
        # real path inside this workspace's host-side directory.
        responses = iter([
            _fake_think_response("```python\nopen('report.pdf', 'w').close()\n```"),
            _fake_think_response("done — wrote report.pdf"),
        ])
        monkeypatch.setattr(brain, "think", lambda *a, **kw: next(responses))
        monkeypatch.setattr(
            code_exec, "run_python",
            lambda code, session_id="", workspace_id="", **kw: {
                "success": True, "stdout": "", "stderr": "", "files_created": ["report.pdf"],
            },
        )

        skill = _make_skill(tmp_path)
        ctx = SkillContext(user_message="make a pdf", session_id="s1")
        result = skill.run(ctx)

        expected = isolated_workspace / skill._workspace_id(ctx) / "report.pdf"
        assert result.output_path == str(expected)

    def test_output_path_is_none_when_nothing_was_created(self, monkeypatch, tmp_path):
        monkeypatch.setattr(brain, "think", lambda *a, **kw: _fake_think_response("just an answer"))

        result = _make_skill(tmp_path).run(SkillContext(user_message="hello"))

        assert result.output_path is None

    def test_chat_history_is_included_in_the_prompt(self, monkeypatch, tmp_path):
        captured = {}

        def fake_think(prompt, *a, **kw):
            captured["prompt"] = prompt
            return _fake_think_response("ok")

        monkeypatch.setattr(brain, "think", fake_think)

        skill = _make_skill(tmp_path)
        history = [{"speaker": "User", "text": "let's talk about the quarterly report"}]
        skill.run(SkillContext(user_message="summarize it", chat_history=history))

        assert "quarterly report" in captured["prompt"]


class TestDocumentQualityGuidance:
    """Document skills get an OUTPUT QUALITY section appended to the
    execution contract. Without it the model optimizes for "the file opens"
    and ships library defaults — default font, default black-on-white,
    default title slide — which is exactly the templated look that made
    generated PDFs and decks feel generic.

    Capability skills (webapp-testing, mcp-builder, …) must NOT get it:
    they produce code and test runs, not documents, so design guidance is
    pure prompt noise that crowds out their real instructions.
    """

    def test_document_skills_get_the_quality_section(self):
        for name in ("pdf", "pptx", "docx", "xlsx"):
            contract = AdaptedClaudeSkill._execution_contract(False, name)
            assert "OUTPUT QUALITY" in contract, f"{name} lost its quality guidance"

    def test_quality_section_names_the_actual_failure_mode(self):
        contract = AdaptedClaudeSkill._execution_contract(False, "pptx")
        # The point isn't "make it pretty" — it's that accepting the
        # library's defaults is what produces the templated result.
        assert "default" in contract.lower()
        assert "palette" in contract.lower()

    def test_non_document_skills_do_not_get_it(self):
        for name in ("webapp-testing", "mcp-builder", "skill-creator", "frontend-design"):
            contract = AdaptedClaudeSkill._execution_contract(False, name)
            assert "OUTPUT QUALITY" not in contract, f"{name} should not carry document design guidance"

    def test_skill_name_matching_is_case_insensitive(self):
        assert "OUTPUT QUALITY" in AdaptedClaudeSkill._execution_contract(False, "  PDF ")

    def test_missing_skill_name_degrades_to_no_quality_section(self):
        # Defaulted arg — a caller that forgets to pass a name should get a
        # usable contract, not a crash.
        assert "OUTPUT QUALITY" not in AdaptedClaudeSkill._execution_contract(False)

    def test_runtime_mechanics_survive_alongside_the_quality_section(self):
        contract = AdaptedClaudeSkill._execution_contract(False, "pdf")
        assert "HOW TO ACT ON THIS" in contract
        assert "No network access" in contract
