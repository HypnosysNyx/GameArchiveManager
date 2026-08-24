"""Track internal directories created by the currently executing task."""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator


_ACTIVE_TRACKER: ContextVar["TaskRunDirectoryTracker | None"] = ContextVar(
    "game_archive_active_directory_tracker", default=None
)


class TaskRunDirectoryTracker:
    """Record only directories explicitly created by participating modules."""

    def __init__(self, task_root: str | Path) -> None:
        self.task_root = Path(task_root).expanduser().resolve()
        self._created: list[Path] = []
        self._known: set[Path] = set()

    def register(self, directory: str | Path) -> None:
        path = Path(directory).expanduser().resolve()
        if path == self.task_root or self.task_root not in path.parents:
            return
        if path in self._known:
            return
        self._known.add(path)
        self._created.append(path)

    def top_level_directories(self) -> list[Path]:
        existing = [path for path in self._created if path.is_dir()]
        return [
            path
            for path in existing
            if not any(other != path and other in path.parents for other in existing)
        ]

    def owned_directories(self) -> list[Path]:
        """Return a snapshot of directories explicitly created by this run."""
        return self._created.copy()

    def owns(self, directory: str | Path) -> bool:
        """Check exact ownership without inferring it from a directory name."""
        return Path(directory).expanduser().resolve() in self._known


@contextmanager
def activate_directory_tracker(
    tracker: TaskRunDirectoryTracker,
) -> Iterator[TaskRunDirectoryTracker]:
    token = _ACTIVE_TRACKER.set(tracker)
    try:
        yield tracker
    finally:
        _ACTIVE_TRACKER.reset(token)


def register_created_directory(directory: str | Path) -> None:
    tracker = _ACTIVE_TRACKER.get()
    if tracker is not None:
        tracker.register(directory)
