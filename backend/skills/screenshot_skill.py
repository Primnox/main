# backend/skills/screenshot_skill.py
import time
from skills.base_skill import BaseSkill, SkillContext, SkillResult
from logger import get_logger

log = get_logger("skill.screenshot")


class ScreenshotSkill(BaseSkill):
    name = "Screenshot"
    description = "Capture the screen and run vision analysis on it."
    supported_extensions = []
    trigger_words = ["take ss", "take screenshot", "screenshot this", "capture screen"]
    REQUIRES_PIP = [("PIL", "Pillow")]

    def execute(self, ctx: SkillContext) -> SkillResult:
        from PIL import ImageGrab
        from sensor_vision import describe_screen
        from sandbox_manager import sandbox_dir, enforce_quota

        base_dir = sandbox_dir()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        img_path = base_dir / f"ss_{timestamp}.png"

        log.info(f"Screenshot skill — saving to {img_path}")
        try:
            img = ImageGrab.grab()
            img.save(img_path)
            log.info("Screenshot captured.")

            vision_data = describe_screen()
            # `.get("description", <default>)` never fired its default: on a
            # failure the key was present but EMPTY, so this rendered as
            # "ss saved bro. i see: ..." — a confident claim to have looked,
            # followed by nothing. Treat blank as absent, and say which it is.
            description = (vision_data.get("description") or "").strip()
            vision_error = vision_data.get("error")

            meta_path = base_dir / f"ss_{timestamp}_meta.txt"
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write(f"Description: {description or vision_error or 'unavailable'}")

            enforce_quota()

            if not description:
                return SkillResult(
                    success=True,  # the screenshot itself did save
                    output_text=(
                        f"ss saved — but i couldn't read it: "
                        f"{vision_error or 'no description came back'}"
                    ),
                    output_path=str(img_path),
                    extras={"meta_path": str(meta_path), "vision_failed": True},
                )

            # Only ellipsise when something was actually cut off; the "..." used
            # to be unconditional, so a complete description looked truncated.
            summary = description if len(description) <= 200 else description[:200].rstrip() + "…"
            return SkillResult(
                success=True,
                output_text=f"ss saved bro. i see: {summary}",
                output_path=str(img_path),
                extras={"meta_path": str(meta_path)}
            )
        except Exception as e:
            log.error(f"Screenshot skill failed: {e}", exc_info=True)
            return SkillResult(success=False, error=str(e))


if __name__ == "__main__":
    skill = ScreenshotSkill()
    print(skill.run(SkillContext()))
