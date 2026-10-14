"""Remember where the user left a window, and center it the first time."""

from __future__ import annotations

import json

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


def remember(name: str, widget) -> None:
    """Store the window the user can see right now."""
    try:
        x, y = widget.winfo_x(), widget.winfo_y()
        width, height = widget.winfo_width(), widget.winfo_height()
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
        widget.state("zoomed")
