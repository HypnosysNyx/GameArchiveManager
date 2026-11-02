"""Remember where the user left a window, and center it the first time."""

from __future__ import annotations

import json
import sys
from tkinter import TclError

from application.runtime_paths import user_data_directory


def _path():
    return user_data_directory() / "window_place.json"


def _load() -> dict:
    file = _path()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    file = _path()
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def _on_screen(x: int, y: int) -> bool:
    """True when the title-bar point still lies on a connected monitor."""
    try:
        import ctypes
        from ctypes import wintypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        return bool(ctypes.windll.user32.MonitorFromPoint(POINT(int(x) + 48, int(y) + 12), 0))
    except (AttributeError, OSError, ValueError):
        return 0 <= x and 0 <= y


def fully_visible_geometry(widget, geometry: str) -> str:
    """Clamp a window rectangle into its nearest monitor work area.

    Unlike checking only the title bar, this keeps the bottom actions visible
    when a remembered position meets a taller redesigned dialog.
    """
    import ctypes
    import re
    from ctypes import wintypes

    match = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", geometry)
    if match is None:
        return geometry
    width, height, x, y = (int(part) for part in match.groups())
    try:
        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wintypes.DWORD),
            ]

        user32 = ctypes.windll.user32
        # Do not set argtypes here: _on_screen uses an equivalent local POINT
        # structure, and a global argtypes binding would reject that instance.
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        user32.GetMonitorInfoW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(MONITORINFO)
        ]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        monitor = user32.MonitorFromPoint(POINT(x + 40, y + 12), 2)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise OSError("Unable to query nearest monitor")
        left, top = int(info.rcWork.left), int(info.rcWork.top)
        right, bottom = int(info.rcWork.right), int(info.rcWork.bottom)
    except (AttributeError, OSError, ValueError):
        # Safe fallback for unit tests and non-Windows hosts.
        left = top = 0
        right = int(widget.winfo_screenwidth())
        bottom = int(widget.winfo_screenheight())

    x = max(left, min(x, right - width))
    y = max(top, min(y, bottom - height))
    return f"{width}x{height}{x:+d}{y:+d}"


def remember(name: str, widget) -> None:
    """Store the window the user can see right now."""
    try:
        x, y = widget.winfo_x(), widget.winfo_y()
        width, height = widget.winfo_width(), widget.winfo_height()
        if sys.platform.startswith("linux"):
            try:
                maximized = bool(widget.tk.getboolean(widget.attributes("-zoomed")))
            except TclError:
                maximized = False
        else:
            maximized = widget.state() == "zoomed"
    except Exception:
        return
    if width < 80 or height < 80:
        return
    data = _load()
    data[name] = {
        "x": int(x),
        "y": int(y),
        "w": int(width),
        "h": int(height),
        "maximized": maximized,
    }
    _save(data)


def geometry_for(name: str, widget, width: int, height: int, anchor=None) -> str:
    """Use the saved top-left corner, otherwise center on the anchor or the screen."""
    saved = _load().get(name)
    try:
        saved_x = int(saved["x"])
        saved_y = int(saved["y"])
    except (KeyError, TypeError, ValueError):
        saved_x = saved_y = -1
    use_saved = isinstance(saved, dict) and _on_screen(saved_x, saved_y)
    if use_saved:
        x = saved_x
        y = saved_y
        width = max(width, min(int(saved.get("w", width)), max(width, widget.winfo_screenwidth() - 40)))
    elif anchor is not None:
        x = anchor.winfo_rootx() + max(0, (anchor.winfo_width() - width) // 2)
        y = anchor.winfo_rooty() + max(0, (anchor.winfo_height() - height) // 2)
    else:
        x = max(0, (widget.winfo_screenwidth() - width) // 2)
        y = max(0, (widget.winfo_screenheight() - height) // 2)
    return f"{int(width)}x{int(height)}+{int(x)}+{int(y)}"


def restore_maximized(name: str, widget) -> None:
    """Restore maximization only after a saved placement has been validated."""
    saved = _load().get(name)
    if not isinstance(saved, dict) or not saved.get("maximized"):
        return
    try:
        saved_x = int(saved["x"])
        saved_y = int(saved["y"])
    except (KeyError, TypeError, ValueError):
        return
    if _on_screen(saved_x, saved_y):
        try:
            if sys.platform.startswith("linux"):
                widget.attributes("-zoomed", True)
            else:
                widget.state("zoomed")
        except TclError:
            # Some Linux window managers do not support maximization.
            return
