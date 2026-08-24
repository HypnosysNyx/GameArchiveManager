"""Resolve portable application and writable per-user runtime paths."""

import os
import sys
from pathlib import Path

from version import APP_NAME


def application_directory() -> Path:
    """Return the source root or, when frozen, the executable directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def user_data_directory() -> Path:
    """Return a writable per-user directory without creating it."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = (
        Path(local_app_data).expanduser()
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return base / APP_NAME


def default_log_directory() -> Path:
    return user_data_directory() / "logs"


def default_history_file() -> Path:
    return user_data_directory() / "history" / "task_history.json"


def default_config_path() -> Path:
    """Prefer portable config, then an optional per-user config file."""
    portable = application_directory() / "config.json"
    if portable.is_file():
        return portable
    per_user = user_data_directory() / "config.json"
    if per_user.is_file():
        return per_user
    return portable
