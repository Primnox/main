import ctypes
import time
import random
import math
from logger import get_logger

log = get_logger("automation")

# Windows API Constants
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

# Input structure for SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("iu", INPUT_UNION)
    ]

def send_input(flags, x=0, y=0):
    # Normalize coordinates for MOUSEEVENTF_ABSOLUTE
    # 0 to 65535 map to full virtual desktop
    # SM_CXVIRTUALSCREEN=78, SM_CYVIRTUALSCREEN=79
    width = ctypes.windll.user32.GetSystemMetrics(78)
    height = ctypes.windll.user32.GetSystemMetrics(79)
    
    nx = int(x * 65535 / (width - 1)) if width > 1 else 0
    ny = int(y * 65535 / (height - 1)) if height > 1 else 0

    extra = ctypes.c_ulong(0)
    mi = MOUSEINPUT(nx, ny, 0, flags | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, 0, ctypes.pointer(extra))
    iu = INPUT_UNION(mi)
    input_obj = INPUT(0, iu) # 0 = INPUT_MOUSE
    
    ctypes.windll.user32.SendInput(1, ctypes.pointer(input_obj), ctypes.sizeof(input_obj))

def bezier_curve(p0, p1, p2, p3, t):
    """Calculates a point on a cubic Bezier curve."""
    return (
        (1-t)**3 * p0 +
        3*(1-t)**2 * t * p1 +
        3*(1-t) * t**2 * p2 +
        t**3 * p3
    )

def move_mouse_humanized(target_x, target_y):
    """Moves mouse to target using a Bezier curve for humanization."""
    # Get current position
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    
    curr = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.pointer(curr))
    start_x, start_y = curr.x, curr.y
    
    log.info(f"Moving mouse from ({start_x}, {start_y}) to ({target_x}, {target_y})")

    # Generate control points for Bezier
    # Random offset for 'curvy' path
    dist = math.sqrt((target_x - start_x)**2 + (target_y - start_y)**2)
    offset_scale = dist * 0.2
    
    p1_x = start_x + (target_x - start_x) * 0.3 + random.uniform(-offset_scale, offset_scale)
    p1_y = start_y + (target_y - start_y) * 0.3 + random.uniform(-offset_scale, offset_scale)
    
    p2_x = start_x + (target_x - start_x) * 0.7 + random.uniform(-offset_scale, offset_scale)
    p2_y = start_y + (target_y - start_y) * 0.7 + random.uniform(-offset_scale, offset_scale)
    
    steps = max(10, int(dist / 10))
    for i in range(steps + 1):
        t = i / steps
        # Easing function for more natural speed (slow-fast-slow)
        t_eased = 3 * t**2 - 2 * t**3 
        
        x = bezier_curve(start_x, p1_x, p2_x, target_x, t_eased)
        y = bezier_curve(start_y, p1_y, p2_y, target_y, t_eased)
        
        send_input(MOUSEEVENTF_MOVE, x, y)
        time.sleep(random.uniform(0.001, 0.005))

def click(x, y, button="left"):
    """Humanized click."""
    move_mouse_humanized(x, y)
    time.sleep(random.uniform(0.05, 0.15))
    
    if button == "left":
        send_input(MOUSEEVENTF_LEFTDOWN, x, y)
        time.sleep(random.uniform(0.03, 0.1))
        send_input(MOUSEEVENTF_LEFTUP, x, y)
    else:
        send_input(MOUSEEVENTF_RIGHTDOWN, x, y)
        time.sleep(random.uniform(0.03, 0.1))
        send_input(MOUSEEVENTF_RIGHTUP, x, y)
        
    log.info(f"Clicked {button} at ({x}, {y})")

if __name__ == "__main__":
    # Test: Move to middle of screen
    w = ctypes.windll.user32.GetSystemMetrics(0)
    h = ctypes.windll.user32.GetSystemMetrics(1)
    move_mouse_humanized(w//2, h//2)
