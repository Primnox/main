# backend/skills/code_skill.py
from skills.base_skill import BaseSkill, SkillContext, SkillResult
from logger import get_logger

log = get_logger("skill.code")


class CodeSkill(BaseSkill):
    name = "Code Analyst"
    description = "Explain, review, or refactor code files."
    supported_extensions = ["py", "js", "ts", "html", "css", "rs", "cpp", "c", "json"]
    trigger_words = [
        "explain this code", "review this code", "refactor this", "fix this code",
        "analyze my code", "what does this code do", "what does this do",
        "debug this", "debug my code", "code review", "check my code",
        "optimize this code", "optimize this", "refactor my code",
        "what does this function do", "explain this function",
    ]
    REQUIRES_PIP = []

    def execute(self, ctx: SkillContext) -> SkillResult:
        from brain import think

        if not ctx.file_path:
            return SkillResult(
                success=False,
                error="no file attached — drop a code file and try again, or ask me to review specific code directly."
            )

        log.info(f"Code Analyst: {ctx.file_path}")
        try:
            with open(ctx.file_path, "r", encoding="utf-8") as f:
                code = f.read()

            prompt = ctx.user_message or "Review and explain this code."
            resp = think(f"CODE:\n{code}\n\nTASK: {prompt}")
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "failed to analyze code.")
            log.info("Code analysis complete.")
            return SkillResult(success=True, output_text=content)
        except Exception as e:
            log.error(f"Code Analyst failed: {e}", exc_info=True)
            return SkillResult(success=False, error=str(e))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        skill = CodeSkill()
        print(skill.run(SkillContext(file_path=sys.argv[1])))
