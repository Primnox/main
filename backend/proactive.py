# backend/proactive.py
from typing import Callable, Optional
import time
from system_prompts import PROACTIVE_PROMPT
from brain import think
from logger import get_logger

log = get_logger("proactive")

class ProactiveEngine:
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.last_comment_time = 0
        self.cooldown = 300 # 5 minutes default
        self.system_prompt = PROACTIVE_PROMPT

    def analyze_proactively(self, context_summary):
        """Uses LLM to decide if a proactive comment is needed."""
        now = time.time()
        if now - self.last_comment_time < self.cooldown:
            log.debug(f"Proactive cooldown active ({int(self.cooldown - (now - self.last_comment_time))}s left)")
            return None

        log.info("Evaluating screen context for proactive commentary...")
        prompt = f"Screen Context:\n{context_summary}\n\nShould you comment? If yes, provide the comment. If no, say 'silent'."
        
        try:
            response = think(prompt, system_override=self.system_prompt)
        except Exception as e:
            log.error(f"Proactive analysis failed: {e}")
            return None
        
        # Check if response is a dict (from offline/error) or string
        content = ""
        if isinstance(response, dict):
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "silent")
        else:
            content = response

        if "silent" in content.lower():
            log.debug("Proactive engine decided to remain silent.")
            return None

        log.info(f"Proactive comment generated: {content}")
        self.last_comment_time = now
        return content

if __name__ == "__main__":
    engine = ProactiveEngine()
    print("Proactive Engine ready.")
