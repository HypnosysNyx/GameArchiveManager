"""Password Manager 使用的数据模型。"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class PasswordSource(str, Enum):
    """密码候选的来源。"""

    USER_INPUT = "USER_INPUT"
    FOLDER_NAME = "FOLDER_NAME"
    HISTORY = "HISTORY"
    TEXT_FILE = "TEXT_FILE"
    SESSION_MEMORY = "SESSION_MEMORY"


class PlatformHint(str, Enum):
    """密码候选来源可能所属的平台。"""

    UNKNOWN = "UNKNOWN"
    ANDROID = "ANDROID"
    PC = "PC"


@dataclass
class PasswordCandidate:
    """保存一个密码候选及其基础使用信息。"""

    password: str = field(repr=False)
    source: PasswordSource
    source_path: Path | None = None
    platform_hint: PlatformHint = PlatformHint.UNKNOWN
    success_count: int = 0
    last_used_time: datetime | None = None
    priority: int = 100
