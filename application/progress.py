"""Progress events exposed by the application service."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BatchProgressEvent:
    """One read-only batch or pipeline progress snapshot."""

    event_type: str
    current_task: int
    total_tasks: int
    task_path: Path
    status: str
    archive_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    phase: str = ""
    current_archive: Path | None = None
