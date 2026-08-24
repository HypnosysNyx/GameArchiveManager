"""Task Manager 使用的基础数据模型。"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import uuid4


class TaskStatus(str, Enum):
    """任务在处理流程中可能处于的状态。"""

    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    EXECUTING = "EXECUTING"
    SCANNING = "SCANNING"
    WAITING_CONFIRM = "WAITING_CONFIRM"
    EXTRACTING = "EXTRACTING"
    ORGANIZING = "ORGANIZING"
    COMPLETED = "COMPLETED"
    COMPLETED_NEEDS_SELECTION = "COMPLETED_NEEDS_SELECTION"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class TaskSettings:
    """保存用户为任务选择的处理策略。"""

    # Legacy aggregate view; authoritative per-platform defaults live in Settings.
    ignore_android_az: bool = False
    delete_archives: bool = False
    delete_empty_folders: bool = False


@dataclass
class Task:
    """表示一个以用户输入文件夹为单位的处理任务。"""

    task_path: Path
    task_id: str = field(default_factory=lambda: str(uuid4()))
    created_time: datetime = field(default_factory=lambda: datetime.now().astimezone())
    status: TaskStatus = TaskStatus.CREATED
    settings: TaskSettings = field(default_factory=TaskSettings)

    # Scanner 完成后再把扫描结果对象保存到这里。
    scan_result: object | None = None
    error_message: str = ""
    explicit_archive_path: Path | None = None
    process_all_inputs: bool = False

    def __post_init__(self) -> None:
        """允许调用者使用字符串或 Path 传入任务目录。"""
        self.task_path = Path(self.task_path)
        if self.explicit_archive_path is not None:
            self.explicit_archive_path = Path(self.explicit_archive_path)
