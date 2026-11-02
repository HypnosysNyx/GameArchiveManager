"""Resolve portable application and writable per-user runtime paths."""

import os
import sys
from pathlib import Path

from version import APP_NAME


def _xdg_directory(variable: str, fallback: str) -> Path:
    """XDG paths must be absolute; ignore empty or relative environment values."""
    value = os.environ.get(variable, "")
    base = Path(value) if value else None
    return (base if base is not None and base.is_absolute() else Path.home() / fallback) / APP_NAME


def application_directory() -> Path:
    """Return the source root or, when frozen, the executable directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def user_data_directory() -> Path:
    """Return a writable per-user directory without creating it."""
    if sys.platform.startswith("linux"):
        return _xdg_directory("XDG_DATA_HOME", ".local/share")
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = (
        Path(local_app_data).expanduser()
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return base / APP_NAME


def default_log_directory() -> Path:
    if sys.platform.startswith("linux"):
        return _xdg_directory("XDG_STATE_HOME", ".local/state") / "logs"
    return user_data_directory() / "logs"


def default_history_file() -> Path:
    return user_data_directory() / "history" / "task_history.json"


def default_config_path() -> Path:
    """Prefer portable config, then an optional per-user config file."""
    if sys.platform.startswith("linux"):
        # Source trees (including shared Windows trees) are updateable code,
        # never the Linux user's writable settings store.
        config = _xdg_directory("XDG_CONFIG_HOME", ".config") / "config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        return config
    portable = application_directory() / "config.json"
    if portable.is_file():
        return portable
    per_user = user_data_directory() / "config.json"
    if per_user.is_file():
        return per_user
    return portable
