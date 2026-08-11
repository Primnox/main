# backend/skills/pdf_skill.py
import re
import time
from skills.base_skill import BaseSkill, SkillContext, SkillResult
from logger import get_logger

log = get_logger("skill.pdf")

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _markdown_line_to_reportlab(line: str) -> str:
    """reportlab's Paragraph interprets its text as a restricted XML/HTML-like
    markup, not markdown — feeding it raw model output straight through has
    two real problems: (1) markdown **bold** shows up as literal asterisks
    instead of actual bold text (confirmed in a real generated PDF), and (2)
    unescaped `<`, `>`, `&` in ordinary prose ("cost < $1000", "AT&T") would
    be misread as XML tags/entities, risking corrupted or broken rendering.
    Escaping must happen BEFORE converting **bold** to <b> tags, or our own
    tags would get escaped too."""
    escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    bolded = _BOLD_RE.sub(r"<b>\1</b>", escaped)
    if bolded.startswith("- "):
        bolded = "• " + bolded[2:]
    return bolded


def _build_pdf_script(content: str, out_name: str) -> str:
    """Source for the sandboxed renderer. Mirrors _render_in_process's logic
    exactly (same markdown conversion, same empty-story guard) so a
    sandboxed and a fallback render produce the same document.

    content and out_name are embedded with repr() rather than string
    interpolation — the content is model output and could otherwise close
    the literal and inject arbitrary code into a script that, while
    sandboxed, still shouldn't be attacker-steerable.
    """
    return f'''
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

_BOLD_RE = re.compile(r"\\*\\*(.+?)\\*\\*")

def _md(line):
    escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    bolded = _BOLD_RE.sub(r"<b>\\1</b>", escaped)
    if bolded.startswith("- "):
        bolded = "\\u2022 " + bolded[2:]
    return bolded

content = {content!r}
out_name = {out_name!r}

doc = SimpleDocTemplate(out_name, pagesize=letter)
styles = getSampleStyleSheet()
story = []
for line in content.split("\\n"):
    stripped = line.strip()
    if stripped:
        if stripped.startswith("#"):
            story.append(Paragraph(_md(stripped.lstrip("#").strip()), styles["Heading1"]))
        else:
            story.append(Paragraph(_md(stripped), styles["BodyText"]))
        story.append(Spacer(1, 12))

if not story:
    raise SystemExit("generated content had no renderable lines.")

doc.build(story)
print("wrote", out_name)
'''


class PDFSkill(BaseSkill):
    name = "PDF Specialist"
    description = "Read, summarize, and generate PDF documents."
    supported_extensions = ["pdf"]
    trigger_words = [
        "summarize this pdf", "read this pdf", "what's in this pdf",
        "create pdf", "generate pdf", "make a pdf", "create a pdf", "make pdf"
    ]
    # Fallback for phrasing the exact trigger_words above miss (typos, extra
    # words) — see skill_router.get_skill_for_trigger / intent_utils.
    creation_artifact_words = ("pdf",)
    REQUIRES_PIP = ["pypdf", "reportlab"]

    @property
    def input_schema(self) -> dict:
        schema = super().input_schema
        schema["properties"]["intent"] = {
            "type": "string",
            "enum": ["read", "generate"],
            "description": "Whether to read an existing PDF or generate a new one"
        }
        return schema

    def execute(self, ctx: SkillContext) -> SkillResult:
        from pypdf import PdfReader
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from brain import think

        # `intent` (see input_schema above) lets a caller state read-vs-generate
        # explicitly — was previously declared but never actually read here, so
        # execute() always re-derived it from keyword-scanning user_message
        # regardless of what a caller passed. Prefer the explicit value when
        # given; fall back to the existing heuristic otherwise (every current
        # caller, which doesn't populate ctx.metadata, is unaffected).
        explicit_intent = ctx.metadata.get("intent")
        if explicit_intent == "generate":
            wants_generate = True
        elif explicit_intent == "read":
            wants_generate = False
        else:
            from skills.intent_utils import expresses_creation_intent
            wants_generate = expresses_creation_intent(ctx.user_message or "", ("pdf",))

        if wants_generate:
            return self._generate_pdf(ctx, think, SimpleDocTemplate, Paragraph, Spacer, getSampleStyleSheet, letter)

        if not ctx.file_path:
            return SkillResult(success=False, error="no pdf file provided for reading.")

        return self._read_pdf(ctx, PdfReader, think)

    def _read_pdf(self, ctx: SkillContext, PdfReader, think) -> SkillResult:
        log.info(f"PDF Specialist (Read): {ctx.file_path}")
        try:
            reader = PdfReader(ctx.file_path)
            text = ""
            for i, page in enumerate(reader.pages):
                log.debug(f"Extracting page {i+1}...")
                text += page.extract_text() + "\n"

            prompt = ctx.user_message or "Summarize this PDF."
            resp = think(f"PDF TEXT:\n{text[:10000]}\n\nTASK: {prompt}")
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "failed to read pdf.")
            return SkillResult(success=True, output_text=content)
        except Exception as e:
            log.error(f"PDF read failed: {e}", exc_info=True)
            return SkillResult(success=False, error=str(e))

    def _generate_pdf(self, ctx: SkillContext, think, SimpleDocTemplate, Paragraph, Spacer, getSampleStyleSheet, letter) -> SkillResult:
        log.info("PDF Specialist (Generate)")
        try:
            from sandbox_manager import sandbox_dir, enforce_quota
            pdf_path = sandbox_dir() / f"doc_{time.strftime('%Y%m%d_%H%M%S')}.pdf"

            # Without this, "create me a pdf for the debate" (referring to
            # something discussed earlier in the same chat) has no way to
            # know what "the debate" means — the skill previously ran with
            # zero conversation context regardless of what's in this session.
            history_block = ""
            if ctx.chat_history:
                lines = [f"{m.get('speaker', '?')}: {(m.get('text') or '')[:300]}" for m in ctx.chat_history[-10:]]
                history_block = (
                    "\n\nRECENT CONVERSATION (use this if the request refers to "
                    "something discussed earlier, e.g. 'the debate', 'that summary'):\n"
                    + "\n".join(lines)
                )

            gen_prompt = (
                f"TASK: Write the raw content for a PDF based on: '{ctx.user_message}'.{history_block}\n\n"
                "CRITICAL CONSTRAINTS: "
                "1. Output ONLY the document content. "
                "2. NO conversational filler. "
                "3. NO meta-talk about the process. "
                "4. Use '#' for section headers. "
                "5. Maintain your persona: lowercase only, no periods."
            )
            resp = think(gen_prompt)
            if "error" in resp:
                return SkillResult(success=False, error=f"brain failed: {resp['error']}")

            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if not content:
                return SkillResult(success=False, error="no content generated by brain.")

            def _render_in_process() -> tuple[bool, str | None]:
                doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
                styles = getSampleStyleSheet()
                story = []
                for line in content.split("\n"):
                    stripped = line.strip()
                    if stripped:
                        if stripped.startswith("#"):
                            heading_text = _markdown_line_to_reportlab(stripped.lstrip("#").strip())
                            story.append(Paragraph(heading_text, styles["Heading1"]))
                        else:
                            story.append(Paragraph(_markdown_line_to_reportlab(stripped), styles["BodyText"]))
                        story.append(Spacer(1, 12))

                # reportlab happily builds a blank PDF from an empty story
                # instead of raising — without this check, content that
                # collapsed to whitespace-only lines would report success for
                # a useless file.
                if not story:
                    return False, "generated content had no renderable lines."
                doc.build(story)
                if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                    return False, "pdf build finished but produced no file."
                return True, None

            # The reportlab calls are ours, but `content` is model output
            # derived from untrusted input — render it as the isolated
            # sandbox account when that's available, and in-process otherwise
            # so this keeps working on a machine where the sandbox was never
            # set up. See skills/sandboxed_render.py.
            from skills.sandboxed_render import render_document
            ok, err, used_sandbox = render_document(
                script=_build_pdf_script(content, pdf_path.name),
                produced_filename=pdf_path.name,
                final_path=pdf_path,
                in_process_fallback=_render_in_process,
                session_id=ctx.session_id or "",
                requires=("reportlab",),
            )
            if not ok:
                return SkillResult(success=False, error=err or "pdf generation failed.")

            enforce_quota()
            log.info(f"PDF generated{' (sandboxed)' if used_sandbox else ''}: {pdf_path}")
            return SkillResult(
                success=True,
                output_text=f"pdf generated successfully. saved to {pdf_path}",
                output_path=str(pdf_path),
                extras={"sandboxed": used_sandbox},
            )
        except Exception as e:
            log.error(f"PDF generate failed: {e}", exc_info=True)
            return SkillResult(success=False, error=str(e))


if __name__ == "__main__":
    import sys
    skill = PDFSkill()
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    ctx = SkillContext(
        file_path=arg if arg and arg.endswith(".pdf") else None,
        user_message=None if (arg and arg.endswith(".pdf")) else arg
    )
    print(skill.run(ctx))
