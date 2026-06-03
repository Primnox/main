# backend/skills/code_skill.py
from brain import think
from skills.base_skill import BaseSkill
from logger import get_logger

log = get_logger("skill.code")

class CodeSkill(BaseSkill):
    name = "Code Analyst"
    supported_extensions = ["py", "js", "ts", "html", "css", "rs", "cpp", "c", "json"]
    trigger_words = ["explain this code", "review this code", "refactor this", "fix this code"]

    def execute(self, file_path, user_message=None):
        log.info(f"Executing Code Analyst skill for {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            
            prompt = user_message if user_message else "Review and explain this code."
            log.debug(f"Sending code analysis request to brain: {prompt}")
            
            resp = think(f"CODE:\n{code}\n\nTASK: {prompt}")
            
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "failed to analyze code.")
            log.info("Code analysis complete.")
            
            return {
                "success": True,
                "output_text": content,
                "skill_name": self.name
            }
        except Exception as e:
            log.error(f"Code Analyst skill failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        skill = CodeSkill()
        print(skill.execute(sys.argv[1]))
