# backend/skills/screenshot_skill.py
import time
from pathlib import Path
from skills.base_skill import BaseSkill, SkillContext, SkillResult
from logger import get_logger

log = get_logger("skill.screenshot")


class ScreenshotSkill(BaseSkill):
    name = "Screenshot"
    description = "Capture the screen and run vision analysis on it."
    supported_extensions = []
    trigger_words = ["take ss", "take screenshot", "screenshot this", "capture screen"]
    REQUIRES_PIP = ["PIL"]

    def execute(self, ctx: SkillContext) -> SkillResult:
        from PIL import ImageGrab
        from sensor_vision import describe_screen

        base_dir = Path.home() / "Documents" / "Primnox" / "Screenshots"
        base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        img_path = base_dir / f"ss_{timestamp}.png"

        log.info(f"Screenshot skill — saving to {img_path}")
        try:
            img = ImageGrab.grab()
            img.save(img_path)
            log.info("Screenshot captured.")

            vision_data = describe_screen()
            description = vision_data.get("description", "no visual description.")

            meta_path = base_dir / f"ss_{timestamp}_meta.txt"
            with open(meta_path, "w") as f:
                f.write(f"Description: {description}")

            return SkillResult(
                success=True,
                output_text=f"ss saved bro. i see: {description[:100]}...",
                output_path=str(img_path),
                extras={"meta_path": str(meta_path)}
            )
        except Exception as e:
            log.error(f"Screenshot skill failed: {e}", exc_info=True)
            return SkillResult(success=False, error=str(e))


if __name__ == "__main__":
    skill = ScreenshotSkill()
    print(skill.run(SkillContext()))
