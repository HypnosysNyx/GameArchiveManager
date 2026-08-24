"""GameArchiveManager 安全清理建议模块。"""

from cleanup.cleanup_manager import CleanupManager
from cleanup.models import CleanupCandidate

__all__ = ["CleanupCandidate", "CleanupManager"]
