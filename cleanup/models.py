"""安全清理模块使用的数据模型。"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class CleanupCandidate:
    """保存一个可供用户确认的目录清理建议。"""

    path: Path
    reason: str
    size: int
    created_time: datetime


@dataclass(frozen=True)
class ResidualInternalDirectory:
    """A run-owned internal directory intentionally retained for safety."""

    path: Path
    status: str = "ORPHANED_TEMP"
    reason: str = ""
    created_time: datetime | None = None
