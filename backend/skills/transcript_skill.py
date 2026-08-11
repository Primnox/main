# backend/skills/transcript_skill.py
from pathlib import Path
from skills.base_skill import BaseSkill, SkillContext, SkillResult
from logger import get_logger

log = get_logger("skill.transcript")


class TranscriptSkill(BaseSkill):
    name = "Transcript Analyst"
    description = (
        "Read a saved transcript or conversation file (.txt, .srt, .vtt) and return "
        "a summary, extracted action items, and key moments."
    )
    # Note: "txt" intentionally excluded — it's too broad and would catch notes,
    # requirements files, configs, etc. Trigger words are the correct dispatch path.
    supported_extensions = ["srt", "vtt"]
    trigger_words = [
        "summarize transcript", "read this transcript", "what did we say",
        "summarize this conversation", "what was said", "recap this"
    ]
    REQUIRES_PIP = []

    @property
    def input_schema(self) -> dict:
        schema = super().input_schema
        schema["properties"]["mode"] = {
            "type": "string",
            "enum": ["summary", "action_items", "full"],
            "description": "What to extract — summary only, action items only, or both"
        }
        return schema

    def execute(self, ctx: SkillContext) -> SkillResult:
        from brain import think

        if not ctx.file_path:
            return SkillResult(success=False, error="no transcript file provided.")

        log.info(f"Transcript Analyst: {ctx.file_path}")
        try:
            text = Path(ctx.file_path).read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                return SkillResult(success=False, error="transcript file is empty.")

            # Truncate to ~12k chars so brain stays within context
            truncated = text[:12000]
            user_intent = ctx.user_message or "full"

            # `mode` (see input_schema above) narrows which section(s) to
            # produce — was previously declared but never actually read here,
            # so a caller passing it had zero effect.
            mode = ctx.metadata.get("mode", "full")
            sections = {
                "summary": "1. **Summary** (3–5 sentences): what was discussed overall.\n",
                "action_items": "1. **Action Items**: bullet list of concrete tasks or follow-ups mentioned.\n",
                "full": (
                    "1. **Summary** (3–5 sentences): what was discussed overall.\n"
                    "2. **Action Items**: bullet list of concrete tasks or follow-ups mentioned.\n"
                    "3. **Key Moments**: 3 notable quotes or decisions, with brief context.\n"
                ),
            }
            instructions = sections.get(mode, sections["full"])

            prompt = (
                f"You are analyzing a transcript. Do the following:\n\n"
                f"{instructions}\n"
                f"User intent: {user_intent}\n\n"
                f"TRANSCRIPT:\n{truncated}"
            )

            resp = think(prompt)
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not content:
                return SkillResult(success=False, error="brain returned empty response.")

            return SkillResult(
                success=True,
                output_text=content,
                extras={"source_file": ctx.file_path, "chars_read": len(text)}
            )
        except Exception as e:
            log.error(f"Transcript Analyst failed: {e}", exc_info=True)
            return SkillResult(success=False, error=str(e))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        skill = TranscriptSkill()
        print(skill.run(SkillContext(file_path=sys.argv[1])))
