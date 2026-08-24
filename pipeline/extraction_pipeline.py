"""Bounded queue for recursive archive extraction."""

from collections import deque
from pathlib import Path

from config.settings import Settings
from pipeline.guard import PipelineGuard
from pipeline.models import ArchiveTaskItem, ArchiveTaskStatus, PipelineResult


class ExtractionPipeline:
    """Manage archive tasks without scanning or extracting files itself."""

    ACTIVE_STATUSES = {
        ArchiveTaskStatus.PROCESSING,
        ArchiveTaskStatus.EXTRACTING,
        ArchiveTaskStatus.SCANNING,
        ArchiveTaskStatus.VALIDATING,
    }

    def __init__(
        self,
        max_depth: int | None = None,
        max_tasks: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        active_settings = settings or Settings()
        max_depth = (
            active_settings.max_recursive_depth if max_depth is None else max_depth
        )
        max_tasks = (
            active_settings.max_archive_tasks if max_tasks is None else max_tasks
        )
        if max_depth < 0:
            raise ValueError("max_depth must not be negative")
        if max_tasks <= 0:
            raise ValueError("max_tasks must be greater than zero")

        self.max_depth = max_depth
        self.max_tasks = max_tasks
        self.guard = PipelineGuard(
            max_depth=max_depth,
            max_new_tasks=max_tasks,
            max_embedded_candidates=active_settings.max_embedded_candidates,
        )
        self._queue: deque[ArchiveTaskItem] = deque()
        self._known_paths: set[Path] = set()
        self._processing_paths: set[Path] = set()
        self.processed_paths: set[Path] = set()
        self.processed_archives: list[ArchiveTaskItem] = []
        self.failed_archives: list[ArchiveTaskItem] = []
        self.steps: list[str] = []
        self.max_depth_reached = False
        self.guard_errors = []

    def add_task(
        self,
        archive_path: str | Path,
        depth: int = 0,
        parent_archive: str | Path | None = None,
        *,
        is_initial: bool = False,
        is_embedded_archive: bool = False,
    ) -> ArchiveTaskItem | None:
        """Add one unique task when every configured guard permits it."""
        if depth < 0:
            raise ValueError("depth must not be negative")
        path = Path(archive_path).expanduser().resolve()
        parent = (
            Path(parent_archive).expanduser().resolve()
            if parent_archive is not None
            else None
        )
        if path in self._known_paths:
            self.steps.append(f"Skipped duplicate task: {path}")
            return None

        guard_error = self.guard.check(
            path,
            depth,
            is_initial=is_initial,
            is_embedded_archive=is_embedded_archive,
        )
        if guard_error is not None:
            if guard_error.error_type.value == "MAX_RECURSIVE_DEPTH":
                self.max_depth_reached = True
            self.guard_errors.append(guard_error)
            self.steps.append(
                f"PipelineGuard rejected task: {path} - {guard_error.message}"
            )
            return None

        if depth == self.max_depth:
            self.max_depth_reached = True
        item = ArchiveTaskItem(path, depth, parent)
        self._queue.append(item)
        self._known_paths.add(path)
        self.steps.append(f"Added task: {path}, depth: {depth}")
        return item

    def get_next_task(self) -> ArchiveTaskItem | None:
        """Return the next task in FIFO order and mark it active."""
        if not self._queue:
            return None
        item = self._queue.popleft()
        item.status = ArchiveTaskStatus.EXTRACTING
        self._processing_paths.add(item.archive_path)
        self.steps.append(f"Started task: {item.archive_path}")
        return item

    def set_task_status(
        self, item: ArchiveTaskItem, status: ArchiveTaskStatus
    ) -> None:
        """Update an active task to a user-visible processing stage."""
        if item.archive_path not in self._processing_paths:
            raise ValueError("only active tasks can change pipeline stage")
        if status not in {
            ArchiveTaskStatus.EXTRACTING,
            ArchiveTaskStatus.SCANNING,
            ArchiveTaskStatus.VALIDATING,
        }:
            raise ValueError("invalid active pipeline stage")
        item.status = status

    def mark_processed(self, item: ArchiveTaskItem) -> None:
        """Record a successfully processed active task."""
        if (
            item.status not in self.ACTIVE_STATUSES
            or item.archive_path not in self._processing_paths
        ):
            raise ValueError("only active tasks can be marked successful")
        item.status = ArchiveTaskStatus.COMPLETED
        self._processing_paths.discard(item.archive_path)
        self.processed_paths.add(item.archive_path)
        self.processed_archives.append(item)
        self.steps.append(f"Task completed: {item.archive_path}")

    def mark_failed(self, item: ArchiveTaskItem) -> None:
        """Record a failed active task."""
        if (
            item.status not in self.ACTIVE_STATUSES
            or item.archive_path not in self._processing_paths
        ):
            raise ValueError("only active tasks can be marked failed")
        item.status = ArchiveTaskStatus.FAILED
        self._processing_paths.discard(item.archive_path)
        self.processed_paths.add(item.archive_path)
        self.failed_archives.append(item)
        self.steps.append(f"Task failed: {item.archive_path}")

    def is_max_depth(self, depth: int) -> bool:
        return depth >= self.max_depth

    def is_max_task_count(self) -> bool:
        return self.guard.new_task_count >= self.max_tasks

    def get_result(self) -> PipelineResult:
        """Return a snapshot of the current queue and guard state."""
        return PipelineResult(
            success=(
                not self.failed_archives
                and not self._queue
                and not self._processing_paths
                and not self.guard_errors
            ),
            processed_archives=self.processed_archives.copy(),
            failed_archives=self.failed_archives.copy(),
            steps=self.steps.copy(),
            max_depth_reached=self.max_depth_reached,
            guard_errors=self.guard_errors.copy(),
        )
