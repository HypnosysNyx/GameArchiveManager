"""Password Recovery Engine 使用的数据模型。"""

from dataclasses import dataclass
from pathlib import Path

from password.models import PasswordCandidate


@dataclass
class PasswordAttemptPlan:
    """保存一个压缩包的密码尝试顺序和进度。"""

    archive_path: Path
    password_candidates: list[PasswordCandidate]
    current_index: int
    max_attempts: int
