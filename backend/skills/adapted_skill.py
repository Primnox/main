# backend/skills/adapted_skill.py
"""Adapter that lets Primnox load and run real Anthropic Claude Skill
packages (the SKILL.md format behind docx/pdf/pptx/xlsx and similar) — not
just Primnox's own hand-written *_skill.py classes.

A Claude Skill is a folder (SKILL.md + optional scripts/, references/,
assets/) whose SKILL.md is YAML frontmatter (name + description required)
plus a markdown body of natural-language instructions. Real Claude Skills
aren't deterministic code — they're instructions the model follows using its
own tools, over potentially many turns. Primnox has no reusable agentic
tool-calling loop (see brain.py's _think_stream_inner — inlined, streaming-
coupled, Groq/OpenAI only), so this module builds a small, purpose-built,
bounded loop instead: read instructions -> think() -> optionally run one
code block via the sandboxed code_exec.run_python -> think() again -> done.

Not named *_skill.py on purpose — this is infrastructure, not a skill
itself, and skill_router.discover_skills()'s glob should never pick it up.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from skills.base_skill import BaseSkill, SkillContext, SkillResult
from logger import get_logger

log = get_logger("skill.adapted")

_REFERENCE_CHAR_CAP = 10000  # matches pdf_skill.py's existing per-file truncation convention

# The real workflows these skills describe are 6-10 steps, not 2. The pptx
# skill's template path alone is: thumbnail the template -> unzip the deck ->
# duplicate slides -> edit slide XML -> clean orphans -> rezip -> validate.
# A 2-step cap didn't shorten that workflow, it just guaranteed it was
# abandoned half-done, leaving a corrupt .pptx behind.
_MAX_STEPS = 10

_CODE_BLOCK_RE = re.compile(r"```([A-Za-z0-9_+-]*)\n(.*?)```", re.DOTALL)

# Skills write their command blocks in whatever the underlying tool speaks:
# `bash` for the unzip/zip/validate pipelines, `javascript` for pptxgenjs and
# docx-js, `python` for the bundled scripts. Anything unrecognised is treated
# as prose, not silently executed as Python.
_LANG_ALIASES = {
    "python": "python", "py": "python", "python3": "python",
    "bash": "shell", "sh": "shell", "shell": "shell", "cmd": "shell",
    "bat": "shell", "batch": "shell", "console": "shell", "powershell": "shell",
    "javascript": "node", "js": "node", "node": "node", "mjs": "node",
}

# Where the skill's own files land inside the execution workspace. Chosen to
# match how SKILL.md talks about them ("paths are relative to this skill's
# directory") once the model is told to cd/prefix with this.
_STAGED_SKILL_SUBDIR = "skill"

# Real skills are far bigger than a hand-written fixture suggests: the
# official docx/pptx/xlsx skills each bundle ~1.1 MB across 50+ script files
# (mostly OOXML schemas). Reading all of that at discovery and pasting it
# into one prompt is not viable, so file CONTENT is read lazily at execute()
# time, prioritised (reference docs before scripts) and cut off at a total
# budget. Script *paths* are always listed — cheap, and enough for the model
# to know what the package ships.
_MAX_PROMPT_CHARS = 60000          # ~15k tokens — hard ceiling for the whole assembled prompt
_MAX_BODY_CHARS = 40000            # SKILL.md's own instructions get first claim on that
_SCRIPT_CONTENT_MAX_BYTES = 8000   # skip individual files bigger than this
_SKIP_SCRIPT_SUFFIXES = {".xml", ".xsd", ".json", ".bin", ".png", ".jpg", ".zip"}


@dataclass
class ParsedSkill:
    name: str
    description: str
    body: str
    reference_files: list = field(default_factory=list)  # (label, Path)
    script_files: list = field(default_factory=list)      # (label, Path)
    version: str | None = None
    license: str | None = None


def _truncate_with_notice(text: str, cap: int = _REFERENCE_CHAR_CAP) -> str:
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n...[truncated, {len(text) - cap} more chars]"


def _collect_reference_files(folder: Path) -> list:
    """Every .md in the package except SKILL.md itself, most-relevant first.

    Real skills don't agree on a layout, so matching only `references/`
    misses most of them: the official `pdf` skill keeps reference.md and
    forms.md as top-level siblings (its SKILL.md literally says "see
    REFERENCE.md"), while others use reference/ (singular), agents/,
    examples/, themes/, or per-language subtrees. Collecting all of them and
    letting the caller's budget decide what fits is more robust than
    enumerating folder names — and it means a doc the skill tells the model
    to read is actually present.

    Ordering matters because the budget cuts off the tail: top-level docs
    first (usually the entry points), then references/, then the rest.
    """
    top_level, refs_dir, rest = [], [], []
    for f in sorted(folder.rglob("*.md")):
        if f.name.upper() == "SKILL.MD":
            continue
        label = str(f.relative_to(folder))
        if f.parent == folder:
            top_level.append((label, f))
        elif f.parent.name == "references":
            refs_dir.append((label, f))
        else:
            rest.append((label, f))
    return top_level + refs_dir + rest


def _collect_script_files(folder: Path) -> list:
    scripts_dir = folder / "scripts"
    if not scripts_dir.is_dir():
        return []
    return [
        (str(f.relative_to(folder)), f)
        for f in sorted(scripts_dir.rglob("*"))
        if f.is_file()
    ]


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None  # binary/unreadable asset — not usable as prompt context anyway


def parse_skill_md(skill_md_path: Path) -> ParsedSkill:
    """Parses one SKILL.md file (YAML frontmatter + markdown body) plus its
    sibling references/ and scripts/ folders. Raises ValueError on a missing
    or malformed frontmatter block, or a missing/blank name or description —
    callers (discovery) are responsible for catching and logging, matching
    _extract_skill_meta's "skip and warn, never crash discovery" convention."""
    raw = skill_md_path.read_text(encoding="utf-8")

    if not raw.startswith("---"):
        raise ValueError(f"{skill_md_path}: missing YAML frontmatter (must start with '---')")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{skill_md_path}: malformed frontmatter block (need opening and closing '---')")
    _, frontmatter_raw, body = parts

    try:
        frontmatter = yaml.safe_load(frontmatter_raw) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{skill_md_path}: invalid YAML in frontmatter: {e}")

    if not isinstance(frontmatter, dict):
        raise ValueError(f"{skill_md_path}: frontmatter did not parse to a mapping")

    name = (frontmatter.get("name") or "").strip()
    description = (frontmatter.get("description") or "").strip()
    if not name:
        raise ValueError(f"{skill_md_path}: frontmatter missing required 'name'")
    if not description:
        raise ValueError(f"{skill_md_path}: frontmatter missing required 'description'")

    folder = skill_md_path.parent
    return ParsedSkill(
        name=name,
        description=description,
        body=body.strip(),
        reference_files=_collect_reference_files(folder),
        script_files=_collect_script_files(folder),
        version=frontmatter.get("version"),
        license=frontmatter.get("license"),
    )


def _safe_ident(name: str) -> str:
    return re.sub(r"\W+", "_", name).strip("_") or "unnamed"


class AdaptedClaudeSkill(BaseSkill):
    """Shared execute() logic for every SKILL.md-backed skill. Subclassed
    per-folder via make_adapted_skill_class() below, which stamps class-level
    _parsed/_skill_folder onto each subclass — route_skill() instantiates
    with skill_cls(), zero constructor args, so per-instance data has to live
    on the class."""
    _parsed: ParsedSkill = None
    _skill_folder: Path = None

    def execute(self, ctx: SkillContext) -> SkillResult:
        # One approval covers the whole run — see permission_manager's `scope`
        # docstring for why per-step prompting was actively harmful.
        from permission_manager import open_scope, release_scope

        scope = open_scope()
        try:
            return self._execute(ctx, scope)
        finally:
            release_scope(scope)

    def _execute(self, ctx: SkillContext, approval_scope: str) -> SkillResult:
        from brain import think

        workspace_id = self._workspace_id(ctx)
        try:
            staged = self._stage_skill_files(workspace_id)
        except OSError as e:
            # Not fatal: without the staged files the model loses the bundled
            # scripts, but SKILL.md's instructions alone still produce useful
            # output for the create-from-scratch path.
            log.warning(f"Could not stage skill files for {self.name}: {e}")
            staged = False

        prompt = self._build_prompt(ctx, staged=staged)
        step_limit_reached = True
        artifacts: list[str] = []
        commands_run = 0
        last_failure: str | None = None

        ctx.emit("skill_phase", skill=self.name, phase=f"loaded the {self.name} skill",
                 status="done", total=_MAX_STEPS)
        ctx.emit("skill_phase", skill=self.name, phase="working out what to do",
                 status="running", total=_MAX_STEPS)

        resp = think(prompt)
        if "error" in resp:
            ctx.emit("skill_phase", skill=self.name, phase="working out what to do",
                     status="failed", detail=str(resp["error"])[:120], total=_MAX_STEPS)
            return SkillResult(success=False, error=f"brain failed: {resp['error']}")
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

        for step in range(_MAX_STEPS):
            block = self._extract_code_block(content)
            if block is None:
                step_limit_reached = False
                break

            language, code = block
            # The model's own narration above the block is already written
            # in plain language — better than any label derived from the
            # code, and free.
            phase = self._phase_label(content, language)
            ctx.emit("skill_phase", skill=self.name, phase=phase, status="running",
                     command=_display_command(language, code),
                     step=step + 1, total=_MAX_STEPS)

            exec_result = self._execute_block(language, code, ctx, workspace_id,
                                              approval_scope=approval_scope)
            created = [n for n in exec_result.get("files_created", []) if n not in artifacts]
            artifacts.extend(created)
            commands_run += 1
            last_failure = None if exec_result.get("success") else (
                exec_result.get("error") or exec_result.get("stderr") or "unknown error")

            ctx.emit(
                "skill_phase", skill=self.name, phase=phase,
                status="done" if exec_result.get("success") else "failed",
                detail=_result_detail(exec_result, created),
                step=step + 1, total=_MAX_STEPS,
            )

            follow_up = self._build_followup_prompt(exec_result, steps_left=_MAX_STEPS - step - 1)
            resp = think(follow_up)
            if "error" in resp:
                return SkillResult(success=False, error=f"brain failed: {resp['error']}")
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

        extras = {"workspace_id": workspace_id, "files_created": artifacts}
        if step_limit_reached:
            extras["step_limit_reached"] = True

        # extras["files_created"] only carries the bare filename the sandboxed
        # code reported — callers that want to actually open/attach the
        # result (e.g. the chat UI's download link) need a real filesystem
        # path, same as pdf_skill.py's output_path. Resolve the most recently
        # created artifact against this workspace's host-side directory.
        output_path = None
        if artifacts:
            import code_exec
            output_path = str(code_exec.workspace_path(workspace_id) / artifacts[-1])

        # A run that ended on a failed command having produced nothing did not
        # do the job — whatever the model's closing message says.
        #
        # The model is told the command failed (see _build_followup_prompt) and
        # may still sign off with "Done! your deck is ready", because that is
        # what a summarising turn tends to look like. Relaying that verbatim is
        # the worst outcome the skill can produce: the user is told a file
        # exists, goes looking, and finds nothing. Primnox knows what the model
        # doesn't — that no artifact was ever written — so the honest signal
        # has to come from here rather than from the prompt.
        #
        # Deliberately narrow. If ANY file was produced, the run stands: a deck
        # written in step 3 is still a deck when step 5's optional validation
        # pass fails. And a run that executed nothing at all is left alone,
        # because answering a question about PPTX without touching the sandbox
        # is a perfectly good outcome.
        if commands_run and last_failure and not artifacts:
            log.warning(f"{self.name}: run ended on a failed command with no "
                        f"files produced — reporting failure ({last_failure[:120]})")
            return SkillResult(
                success=False,
                output_text=content,
                extras=extras,
                error=(
                    f"The {self.name} run did not produce a file. The last command "
                    f"failed ({last_failure.strip()[:300]}) and no files were created, "
                    "so any claim that the document is ready is wrong — tell the user "
                    "it failed and why. The skill's own closing summary was: "
                    f"{(content or '').strip()[:400]}"
                ),
            )

        return SkillResult(success=True, output_text=content, output_path=output_path, extras=extras)

    @staticmethod
    def _phase_label(content: str, language: str) -> str:
        """A human-readable label for the step about to run.

        Uses the model's own narration above the code block — it already
        explains the step in plain language ("now I'll build the slide
        master"), which is exactly what the activity panel wants and beats
        anything inferable from the code itself. Falls back to the language
        when the model emitted a bare block with no lead-in.
        """
        prose = _CODE_BLOCK_RE.split(content)[0] if content else ""
        for line in prose.splitlines():
            line = line.strip().lstrip("#*-• ").strip()
            # Skip markdown headings-turned-empty and stray punctuation.
            if len(line) < 4:
                continue
            sentence = re.split(r"(?<=[.!?])\s", line)[0].strip().rstrip(":.")
            if sentence:
                return sentence[:80]
        return f"running {language}"

    def _workspace_id(self, ctx: SkillContext) -> str:
        """One reused directory per (chat session, skill). Scoped to the skill
        as well as the session so a deck being built in the same conversation
        as a spreadsheet doesn't inherit the other's half-finished files."""
        base = ctx.session_id or "default"
        return f"{base}-{_safe_ident(self.name)}"

    def _stage_skill_files(self, workspace_id: str) -> bool:
        """Copies the skill package into the workspace so its own scripts are
        actually runnable.

        SKILL.md's instructions are written against the skill's directory
        ("python scripts/thumbnail.py deck.pptx"). Those scripts live in the
        Primnox repo under the user's profile, which the sandbox account
        deliberately cannot read — so without copying them in, every such
        instruction fails with a file-not-found the model can't diagnose.
        Copying is also what keeps the boundary honest: the sandbox gets a
        disposable duplicate, never a handle to the repo.
        """
        import shutil
        import code_exec

        if not self._skill_folder or not Path(self._skill_folder).is_dir():
            return False
        dest = code_exec.workspace_path(workspace_id) / _STAGED_SKILL_SUBDIR
        if dest.is_dir() and any(dest.iterdir()):
            return True  # already staged earlier in this session
        shutil.copytree(self._skill_folder, dest, dirs_exist_ok=True)
        return True

    @staticmethod
    def _execute_block(language: str, code: str, ctx: SkillContext, workspace_id: str,
                       approval_scope: str = "") -> dict:
        import code_exec
        import runtime_capabilities

        if language == "node" and not runtime_capabilities.detect().node:
            # Belt and braces: the prompt already says Node is unavailable,
            # but a skill body full of pptxgenjs examples is persuasive. Fail
            # with the alternative named, so the next step is a working one
            # rather than a retry of the same impossible thing.
            return {
                "success": False,
                "error": (
                    "Node.js cannot run in this sandbox, so pptxgenjs and docx-js "
                    "are unavailable. Use the Python equivalent instead "
                    "(python-pptx, python-docx, openpyxl) in a ```python block."
                ),
                "stdout": "", "stderr": "", "files_created": [],
            }

        runner = {
            "python": code_exec.run_python,
            "shell": code_exec.run_shell,
            "node": code_exec.run_node,
        }[language]
        return runner(code, session_id=ctx.session_id or "", workspace_id=workspace_id,
                      approval_scope=approval_scope)

    def _build_prompt(self, ctx: SkillContext, staged: bool = False) -> str:
        # Body first and largest — it's the skill's actual instructions.
        # Bounded anyway because real skills vary wildly: claude-api's body
        # alone is ~71k chars, which would push a single invocation past 28k
        # tokens before any reference doc is added.
        body = _truncate_with_notice(self._parsed.body, _MAX_BODY_CHARS)
        parts = [body]
        budget = max(0, _MAX_PROMPT_CHARS - len(body))

        # Reference docs first — they're the skill's actual instructions, so
        # they get the budget ahead of script source.
        for label, path in self._parsed.reference_files:
            if budget <= 0:
                break
            text = _read_text(path)
            if text is None:
                continue
            chunk = _truncate_with_notice(text, min(_REFERENCE_CHAR_CAP, budget))
            budget -= len(chunk)
            parts.append(f"\n\n[REFERENCE: {label}]\n{chunk}")

        if self._parsed.script_files:
            listing = "\n".join(f"  {label}" for label, _ in self._parsed.script_files)
            if staged:
                header = (
                    "\n\n[BUNDLED SCRIPTS — these ship with the skill and ARE runnable. "
                    f"They are staged in your working directory under `{_STAGED_SKILL_SUBDIR}/`, "
                    f"so SKILL.md's `scripts/foo.py` is `{_STAGED_SKILL_SUBDIR}/scripts/foo.py` "
                    "for you. Prefer running them over reimplementing their behavior.]\n"
                )
            else:
                header = (
                    "\n\n[BUNDLED SCRIPTS — these ship with the skill but could NOT be "
                    "staged into your working directory, so they are reference only. "
                    "Write equivalent code yourself if you need their behavior.]\n"
                )
            parts.append(header + listing)
            for label, path in self._parsed.script_files:
                if budget <= 0:
                    break
                if path.suffix.lower() in _SKIP_SCRIPT_SUFFIXES:
                    continue
                try:
                    if path.stat().st_size > _SCRIPT_CONTENT_MAX_BYTES:
                        continue
                except OSError:
                    continue
                text = _read_text(path)
                if text is None:
                    continue
                chunk = _truncate_with_notice(text, min(_SCRIPT_CONTENT_MAX_BYTES, budget))
                budget -= len(chunk)
                parts.append(f"\n\n[SCRIPT SOURCE: {label}]\n{chunk}")

        if ctx.chat_history:
            lines = [f"{m.get('speaker', '?')}: {(m.get('text') or '')[:300]}" for m in ctx.chat_history[-10:]]
            parts.append("\n\nRECENT CONVERSATION (use this if the request refers to "
                          "something discussed earlier):\n" + "\n".join(lines))

        parts.append(f"\n\nUSER REQUEST: {ctx.user_message or ''}")
        parts.append(self._execution_contract(staged, self.name))
        return "".join(parts)

    @staticmethod
    def _execution_contract(staged: bool, skill_name: str = "") -> str:
        """The runtime half of the prompt.

        Built from probed capabilities rather than written as a fixed list,
        because a skill body confidently instructs the model to use tools
        that may or may not work here — the official pptx skill is largely
        about pptxgenjs, which needs Node. Stating what's actually available
        up front is what stops the model discovering it halfway through
        generating a document.

        Document skills also get a quality section. Without it the model
        optimizes for "the file opens" and ships library defaults, which is
        exactly what reads as templated — the complaint that prompted this.
        """
        import runtime_capabilities

        caps = runtime_capabilities.detect()
        staged_line = (
            f"- The skill's own files are staged at `{_STAGED_SKILL_SUBDIR}/` in that directory.\n"
            if staged else ""
        )

        languages = ["- ```python — Python 3.\n"
                     "- ```bash — runs via cmd.exe on Windows, so use Windows-compatible commands.\n"]
        if caps.node:
            languages.append(
                "- ```javascript — Node.js. `pptxgenjs` and `docx` are preinstalled "
                "and resolvable with a plain `require(...)`; do NOT run `npm install`, "
                "it would fail with no network.\n"
            )

        unavailable = [name for name, ok in sorted(caps.libraries.items()) if not ok]
        if not caps.node:
            unavailable.append("Node.js / pptxgenjs / docx-js")
        constraint = ""
        if unavailable:
            constraint = (
                "\nNOT AVAILABLE in this environment, whatever the instructions above "
                f"say to use: {', '.join(unavailable)}. Do not attempt them — pick an "
                "approach built only on what is available, and say so plainly in your "
                "final summary if that means a simpler result than the skill describes.\n"
            )

        available = [name for name, ok in sorted(caps.libraries.items()) if ok]
        available_line = (
            f"\nAvailable Python libraries: {', '.join(available)}.\n" if available else ""
        )

        quality = ""
        if skill_name.strip().lower() in _CLAUDE_SKILL_EXTENSIONS:
            quality = (
                "\nOUTPUT QUALITY — a person is going to open this file and look at it. "
                "'It opens without erroring' is the floor, not the goal.\n"
                "- Library defaults ARE the templated look: default font, default "
                "black-on-white, default bullet spacing, default title slide. Decide "
                "these yourself instead of accepting them.\n"
                "- Commit to one palette (background, text, one accent) and one type "
                "hierarchy (clearly different size/weight for title vs heading vs body), "
                "then apply both consistently across every page or slide.\n"
                "- Give the content real structure: a title that states something, "
                "sections that group related material, and whitespace doing the "
                "separating. Don't reformat the user's request into a wall of bullets.\n"
                "- Let the subject set the tone — a pitch deck, a lab report and a "
                "birthday invite should not come out looking identical.\n"
            )

        return (
            "\n\n---\nHOW TO ACT ON THIS\n\n"
            "You are working in a sandboxed directory that PERSISTS between your "
            "steps — files you write in one step are still there in the next, so "
            "multi-stage workflows (unzip, edit, rezip, validate) work as written.\n"
            f"{staged_line}"
            "- Generated documents must be written into that working directory "
            "(use relative paths, never an absolute one).\n"
            "- No network access. Anything not preinstalled is unavailable.\n"
            f"{available_line}{constraint}{quality}"
            "\nTo run something, emit exactly ONE fenced code block per reply, tagged "
            "with its language, and nothing else after it:\n"
            + "".join(languages) +
            f"\nYou get at most {_MAX_STEPS} commands total, so don't waste them on "
            "exploration you don't need. Work one step at a time and wait for each "
            "result before deciding the next — do not assume a command succeeded. "
            "When the task is done, reply with a summary and no code block. For a "
            "purely informational request, just answer directly without running "
            "anything."
        )

    def _build_followup_prompt(self, exec_result: dict, steps_left: int) -> str:
        budget = (
            f"You have {steps_left} more command(s) available. "
            if steps_left > 0
            else "This was your last available command — finish and summarize now, no more code blocks. "
        )
        if not exec_result.get("success", False):
            detail = exec_result.get("error") or exec_result.get("stderr") or "unknown error"
            return (
                f"That command failed: {detail}\n\n"
                f"{budget}Fix the problem and emit one corrected fenced block, "
                "or explain the result to the user directly if it can't be fixed."
            )
        return (
            f"The command ran successfully.\n"
            f"stdout:\n{exec_result.get('stdout', '')}\n"
            f"stderr:\n{exec_result.get('stderr', '')}\n"
            f"files created this step: {', '.join(exec_result.get('files_created', [])) or 'none'}\n\n"
            f"{budget}Continue to the next step if the task isn't finished — the working "
            "directory is unchanged and still holds everything you've written. "
            "Otherwise summarize the result for the user and emit no further code block."
        )

    @staticmethod
    def _extract_code_block(text: str) -> tuple[str, str] | None:
        """First fenced block whose tag maps to a runnable language, as
        (language, code).

        An untagged or prose-tagged fence (```text, ```xml showing what some
        OOXML should look like) is explicitly not executed — SKILL.md bodies
        are full of illustrative snippets, and running one as Python would
        both fail and burn a step.
        """
        for match in _CODE_BLOCK_RE.finditer(text):
            language = _LANG_ALIASES.get(match.group(1).strip().lower())
            if language:
                return language, match.group(2).strip()
        return None


def _display_command(language: str, code: str) -> str:
    """A one-line, secret-free rendering of what's about to run.

    Redaction happens HERE rather than in the frontend so a credential
    never crosses the websocket at all — see redaction.py. The sandbox
    still executes the original `code` untouched.
    """
    from redaction import redact_command

    first = next((ln.strip() for ln in code.splitlines() if ln.strip()), "")
    shown = first if len(first) <= 120 else first[:117] + "…"
    prefix = {"python": "python", "node": "node", "javascript": "node"}.get(language, language)
    return redact_command(f"{prefix} · {shown}")


def _result_detail(exec_result: dict, created: list) -> str:
    """Short outcome line for a finished step — what changed, not how."""
    if not exec_result.get("success"):
        from redaction import redact_text
        err = (exec_result.get("stderr") or exec_result.get("error") or "failed").strip()
        return redact_text(err.splitlines()[-1] if err else "failed")[:120]
    if created:
        return f"wrote {', '.join(created[:3])}" + ("…" if len(created) > 3 else "")
    return "ok"


# File types each document skill owns, taken from its own SKILL.md
# description. Only these four claim extensions — the rest (skill-creator,
# webapp-testing, …) are capability skills with no file type to attach.
_CLAUDE_SKILL_EXTENSIONS = {
    "pdf": ("pdf",),
    "pptx": ("pptx", "potx"),
    "docx": ("docx", "dotx"),
    "xlsx": ("xlsx", "xlsm", "xltx", "csv", "tsv"),
}


def make_adapted_skill_class(folder: Path, parsed: ParsedSkill) -> type:
    """One dynamically-created BaseSkill subclass per discovered SKILL.md
    folder. Class-level attributes carry everything execute() needs, since
    route_skill() instantiates via skill_cls() with no constructor args.

    trigger_words stays empty on purpose: these are routed by
    semantic_router.classify() against `description` (Anthropic writes those
    descriptions explicitly for model-based triggering), not by Primnox's
    substring matching. supported_extensions is populated for the document
    skills so an attached .pdf/.docx/.xlsx/.pptx still routes here — that
    lookup is exact, not guesswork, so it needs no model call.
    """
    return type(
        f"ClaudeSkill_{_safe_ident(parsed.name)}",
        (AdaptedClaudeSkill,),
        {
            "name": parsed.name,
            "description": parsed.description,
            "supported_extensions": _CLAUDE_SKILL_EXTENSIONS.get(parsed.name.strip().lower(), ()),
            "trigger_words": (),
            "REQUIRES_PIP": (),
            "_parsed": parsed,
            "_skill_folder": folder,
        },
    )
