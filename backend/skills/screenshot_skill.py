# backend/skills/screenshot_skill.py
from PIL import ImageGrab
from pathlib import Path
import time
from sensor_vision import describe_screen
from skills.base_skill import BaseSkill
from logger import get_logger

log = get_logger("skill.screenshot")

class ScreenshotSkill(BaseSkill):
    name = "Screenshot"
    supported_extensions = [] # Triggered by command
    trigger_words = ["take ss", "take screenshot", "screenshot this", "capture screen"]

    def execute(self, file_path=None, user_message=None):
        base_dir = Path.home() / "Documents" / "Primnox" / "Screenshots"
        base_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        img_path = base_dir / f"ss_{timestamp}.png"
        
        log.info(f"Executing Screenshot skill, saving to {img_path}")
        
        try:
            # Capture
            img = ImageGrab.grab()
            img.save(img_path)
            log.info("Screenshot captured and saved.")
            
            # Vision Analysis (Pure Groq Vision, no local OCR)
            log.debug("Requesting visual analysis for screenshot...")
            vision_data = describe_screen()
            description = vision_data.get("description", "No visual description.")
            
            # Save metadata
            meta_path = base_dir / f"ss_{timestamp}_meta.txt"
            with open(meta_path, "w") as f:
                f.write(f"Description: {description}")
            log.debug(f"Metadata saved to {meta_path}")
            
            return {
                "success": True,
                "output_text": f"ss saved bro. i see: {description[:100]}...",
                "output_path": str(img_path),
                "skill_name": self.name
            }
        except Exception as e:
            log.error(f"Screenshot skill failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

if __name__ == "__main__":
    skill = ScreenshotSkill()
    print(skill.execute())
