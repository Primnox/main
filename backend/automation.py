# backend/automation.py
import time
import random
import math
from logger import get_logger

log = get_logger("automation")

try:
    import pyautogui
    pyautogui.FAILSAFE = False   # disable corner-failsafe for programmatic use
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    log.warning("pyautogui not available — mouse automation disabled.")


def bezier_curve(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """Evaluate a cubic Bézier curve at parameter t."""
    return (
        (1 - t) ** 3 * p0
        + 3 * (1 - t) ** 2 * t * p1
        + 3 * (1 - t) * t ** 2 * p2
        + t ** 3 * p3
    )


def move_mouse_humanized(target_x: int, target_y: int) -> None:
    """Move mouse to (target_x, target_y) along a randomised Bézier path."""
    if not HAS_PYAUTOGUI:
        log.warning("pyautogui unavailable — skipping mouse move.")
        return

    start_x, start_y = pyautogui.position()
    log.info(f"Moving mouse ({start_x}, {start_y}) → ({target_x}, {target_y})")

    dist = math.hypot(target_x - start_x, target_y - start_y)
    if dist < 1:
        return

    offset_scale = dist * 0.2
    p1_x = start_x + (target_x - start_x) * 0.3 + random.uniform(-offset_scale, offset_scale)
    p1_y = start_y + (target_y - start_y) * 0.3 + random.uniform(-offset_scale, offset_scale)
    p2_x = start_x + (target_x - start_x) * 0.7 + random.uniform(-offset_scale, offset_scale)
    p2_y = start_y + (target_y - start_y) * 0.7 + random.uniform(-offset_scale, offset_scale)

    steps = max(10, int(dist / 10))
    for i in range(steps + 1):
        t = i / steps
        t_eased = 3 * t ** 2 - 2 * t ** 3   # smooth-step easing
        x = bezier_curve(start_x, p1_x, p2_x, target_x, t_eased)
        y = bezier_curve(start_y, p1_y, p2_y, target_y, t_eased)
        pyautogui.moveTo(int(x), int(y), _pause=False)
        time.sleep(random.uniform(0.001, 0.005))


def click(x: int, y: int, button: str = "left") -> None:
    """Humanised click at (x, y)."""
    if not HAS_PYAUTOGUI:
        log.warning("pyautogui unavailable — skipping click.")
        return
    move_mouse_humanized(x, y)
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.click(x, y, button=button)
    log.info(f"Clicked {button} at ({x}, {y})")


if __name__ == "__main__":
    if HAS_PYAUTOGUI:
        w, h = pyautogui.size()
        move_mouse_humanized(w // 2, h // 2)
    else:
        print("pyautogui not installed.")
