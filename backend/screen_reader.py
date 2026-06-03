# backend/screen_reader.py
import uiautomation as auto
import pythoncom
from logger import get_logger

log = get_logger("uia")

def read_screen():
    log.debug("Starting UIA screen scan...")
    pythoncom.CoInitialize()
    try:
        active = auto.GetFocusedControl()
        if not active:
            # Fallback to foreground window
            try:
                import win32gui
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    active = auto.ControlFromHandle(hwnd)
            except Exception:
                pass
                
        if not active:
            log.warning("No active control found for UIA scan.")
            return {
                "window_title": "Unknown",
                "focused_text": "",
                "visible_texts": [],
                "errors": []
            }
            
        # Climb up to the window element to limit scope to the current window
        window_control = active
        try:
            while window_control and window_control.ControlType != auto.ControlType.WindowControl:
                parent = window_control.GetParentControl()
                if not parent or parent == auto.GetRootControl():
                    break
                window_control = parent
        except Exception:
            pass
            
        window_title = window_control.Name if window_control else "Unknown"
        
        # Safe GetValuePattern — can throw COMError
        focused_text = ""
        try:
            vp = active.GetValuePattern()
            if vp:
                focused_text = vp.Value or ""
        except Exception:
            pass
        
        visible_texts = []
        errors_found = []
        
        log.debug(f"Active Window for UIA scan: {window_title}")

        # Deeper walk for error detection
        def walk(ctrl, depth=0):
            if depth > 4 or len(visible_texts) >= 50: return # Limit depth and count
            try:
                children = ctrl.GetChildren()
            except Exception:
                return

            for c in children:
                try:
                    name = c.Name
                    if name:
                        name_stripped = name.strip()
                        if len(name_stripped) > 1:
                            visible_texts.append(name_stripped)
                            # Basic error detection
                            if any(err in name_stripped.lower() for err in ["error", "exception", "expected", "failed", "syntaxerror"]):
                                errors_found.append(name_stripped)
                    walk(c, depth + 1)
                except Exception:
                    continue

        walk(window_control)
        
        log.info(f"Screen scan complete. Found {len(visible_texts)} elements and {len(errors_found)} errors.")
        
        return {
            "window_title": window_title,
            "focused_text": focused_text,
            "visible_texts": list(set(visible_texts))[:50], # Limit and unique
            "errors": list(set(errors_found))
        }
    except Exception as e:
        log.error(f"UIA Scan failed: {e}")
        return {"error": str(e)}
    finally:
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    print(read_screen())
